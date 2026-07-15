"""Managed-auth edge verification — Epic 043 (Supabase sign-in).

Verifies a `Authorization: Bearer <JWT>` against the project's public JWKS
(asymmetric keys) and returns the stable UUID `sub` as the `viewer_id`. This is
the ONLY thing the managed-auth integration does: authorization stays entirely
in `ScopedSession`/`owner_scope` (the auth brief's explicit non-goal — no
Supabase RLS). The diff lives at the edge; the grant layer is untouched.

Design (auth brief · Epic 043 S1):
  * PyJWT against a **cached** JWKS — no per-request network fetch (AC-1.3).
  * An unknown `kid` (key rotation) triggers **exactly one** refetch, then
    fails closed if the key is still unknown (AC-1.3).
  * `sub` is the ONLY claim trusted for identity (AC-1.1). Signature, expiry,
    and audience are enforced; a missing/expired/garbage token raises
    `InvalidTokenError` so the edge fails closed with a 403 (AC-1.2).
  * Fail-closed by construction: with no JWKS URL configured, `verify_bearer`
    refuses every token — production keeps working anonymous-only with zero new
    env, and a misconfigured deploy never silently trusts a forged identity.

`jwt`/`httpx` are lazy-imported inside the methods so importing this module (and
`api.app`) costs nothing on a slice without the api extra installed.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

# The default JWKS path Supabase serves per project (auth brief). We derive the
# full URL from SUPABASE_URL when ADVENTURE_SUPABASE_JWKS_URL is not set.
_SUPABASE_JWKS_PATH = "/auth/v1/.well-known/jwks.json"

# Supabase mints access tokens with this audience by default. Verified so a token
# minted for a different audience (e.g. a service token) can't pose as a user.
_DEFAULT_AUDIENCE = "authenticated"

# The asymmetric algorithms we accept — PINNED here, never read from the token's
# own (attacker-controlled) `alg` header, so a downgrade/confusion attack can't
# force a weaker scheme. The live Supabase project signs with ES256 (EC P-256);
# RS256 is kept in the set so a project or a rotation onto RSA keys still verifies
# with no code change. No symmetric alg (HS*) is ever admitted — that would let a
# forged token signed with a public key value pass (the classic JWT confusion).
_ALLOWED_ALGORITHMS = ["ES256", "RS256"]

# Timeout (seconds) for the JWKS HTTP fetch. The cache is keyed by kid — a known
# key is served forever with no network call, and a fetch happens only on an
# unknown-kid miss (rotation), so this bounds each rare refetch, not a hot path.
_JWKS_HTTP_TIMEOUT_S = 5.0


class AuthError(Exception):
    """Token verification failed — the edge maps this to a fail-closed 403.

    Deliberately NOT an HTTPException: this module stays framework-agnostic and
    testable without FastAPI; `api.app` translates it to the 403.
    """


class JWTVerifier:
    """Verifies Supabase access tokens against a cached public JWKS.

    Thread-safe: the API serves `/plan` from a threadpool, so the key cache and
    its refetch are guarded by a lock. One verifier is built at startup and
    reused for the process lifetime (keys are cached across requests).
    """

    def __init__(
        self,
        jwks_url: str,
        *,
        audience: str | None = _DEFAULT_AUDIENCE,
        issuer: str | None = None,
        http_get: Any | None = None,
    ) -> None:
        """`jwks_url` is the project's public JWKS endpoint. `http_get` is an
        injection seam for hermetic tests — a callable `(url) -> dict` returning
        the parsed JWKS JSON; production uses httpx. `audience`/`issuer` are
        verified when set (defence in depth beyond the signature)."""
        self._jwks_url = jwks_url
        self._audience = audience
        self._issuer = issuer
        self._http_get = http_get
        self._lock = threading.Lock()
        # kid -> PyJWK. Empty until the first verify triggers a fetch.
        self._keys: dict[str, Any] = {}

    def _fetch_jwks(self) -> dict[str, Any]:
        """Fetch and parse the JWKS JSON. Raises on any transport/parse failure
        so the caller fails closed rather than trusting a stale/empty key set."""
        if self._http_get is not None:
            return self._http_get(self._jwks_url)
        import httpx  # lazy — only the serve path needs it

        resp = httpx.get(self._jwks_url, timeout=_JWKS_HTTP_TIMEOUT_S)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return data

    def _refresh_keys(self) -> None:
        """Replace the key cache from a fresh JWKS fetch (holds the lock)."""
        import jwt  # lazy — PyJWT (and its cryptography backend) only on serve

        raw = self._fetch_jwks()
        keys: dict[str, Any] = {}
        for jwk in raw.get("keys", []):
            kid = jwk.get("kid")
            if not kid:
                continue
            try:
                keys[kid] = jwt.PyJWK.from_dict(jwk)
            except Exception:
                # A single malformed key must not poison the whole set — skip it
                # and keep the usable keys (source-or-silence at the boundary).
                logger.warning("skipping unparseable JWKS key kid=%s", kid)
        self._keys = keys

    def _key_for_kid(self, kid: str) -> Any:
        """Return the signing key for `kid`, refetching the JWKS **exactly once**
        on a miss (key rotation — AC-1.3). Still unknown after one refetch → raise
        (fail closed). Serves a cached key with no network call on a hit.

        A JWKS fetch that itself fails (network down, non-200, bad JSON) is turned
        into an `AuthError` so the edge fails **closed** with a 403 rather than
        surfacing a raw 500 — a token can never be admitted when the key set can't
        be verified against."""
        with self._lock:
            key = self._keys.get(kid)
            if key is not None:
                return key
            # Unknown kid: one refetch (rotation), then fail closed if still absent.
            try:
                self._refresh_keys()
            except Exception as exc:
                raise AuthError("JWKS fetch failed; cannot verify token") from exc
            key = self._keys.get(kid)
            if key is None:
                raise AuthError("no JWKS key matches the token's kid")
            return key

    def verify(self, token: str) -> str:
        """Verify a bearer token and return its `sub` (the `viewer_id`).

        Raises `AuthError` on any failure — bad signature, expiry, missing/blank
        `sub`, unknown key, or an unreadable header — so the edge always fails
        closed with a 403. `sub` is the ONLY claim mapped to identity (AC-1.1)."""
        import jwt  # lazy

        try:
            header = jwt.get_unverified_header(token)
        except Exception as exc:
            raise AuthError("token header is unreadable") from exc
        kid = header.get("kid")
        if not kid:
            raise AuthError("token header carries no kid")

        signing_key = self._key_for_kid(kid)
        try:
            claims = jwt.decode(
                token,
                signing_key.key,
                # Pinned allow-set (ES256/RS256), NEVER the token's own alg header —
                # so a downgrade/confusion attack can't force a weaker scheme.
                algorithms=_ALLOWED_ALGORITHMS,
                audience=self._audience,
                issuer=self._issuer,
                # Enforce expiry + signature; require `sub` to be present so an
                # identity-less token can never resolve to a viewer.
                options={"require": ["exp", "sub"], "verify_aud": self._audience is not None},
            )
        except Exception as exc:  # PyJWT's InvalidTokenError family — fail closed
            raise AuthError("token verification failed") from exc

        sub = claims.get("sub")
        if not isinstance(sub, str) or not sub:
            raise AuthError("token has no usable sub claim")
        return sub


def jwks_url_from_env(env: dict[str, str]) -> str | None:
    """Resolve the JWKS URL from config (auth brief integration shape).

    Precedence: an explicit `ADVENTURE_SUPABASE_JWKS_URL` wins; otherwise derive
    `{SUPABASE_URL}/auth/v1/.well-known/jwks.json`. Returns None when neither is
    set — the fail-closed default: no managed auth is wired, so non-anonymous
    requests are refused and anonymous browsing works with zero new env."""
    explicit = env.get("ADVENTURE_SUPABASE_JWKS_URL")
    if explicit:
        return explicit
    base = env.get("SUPABASE_URL")
    if base:
        return base.rstrip("/") + _SUPABASE_JWKS_PATH
    return None


def build_verifier(env: dict[str, str]) -> JWTVerifier | None:
    """Build a `JWTVerifier` from env, or None when no JWKS URL is configured
    (the fail-closed anonymous-only default). Optional issuer verification uses
    `SUPABASE_URL`'s auth base when present."""
    url = jwks_url_from_env(env)
    if not url:
        return None
    base = env.get("SUPABASE_URL")
    issuer = base.rstrip("/") + "/auth/v1" if base else None
    return JWTVerifier(url, issuer=issuer)
