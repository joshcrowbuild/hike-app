"""Epic 043 S1 — managed-auth JWT verification against a cached JWKS.

Fully hermetic: an EC P-256 (ES256) and an RSA (RS256) keypair are generated in
fixtures, tokens are signed locally, and the JWKS "endpoint" is a callable spy —
NO live Supabase, no network. The live project signs with ES256, so ES256 is the
primary fixture; RS256 proves the pinned algorithm allow-set also accepts a
rotation onto RSA keys with no code change.
"""

from __future__ import annotations

import time
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from api.auth import AuthError, JWTVerifier, build_verifier, jwks_url_from_env

_JWKS_URL = "https://example.test/auth/v1/.well-known/jwks.json"
_AUD = "authenticated"


class _KeyPair:
    """A signing key + its public JWK, for one alg."""

    def __init__(self, alg: str, kid: str) -> None:
        self.alg = alg
        self.kid = kid
        if alg == "ES256":
            self._priv = ec.generate_private_key(ec.SECP256R1())
        elif alg == "RS256":
            self._priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        else:  # pragma: no cover - only the two algs are used
            raise ValueError(alg)

    def public_jwk(self) -> dict[str, Any]:
        pub = jwt.algorithms.get_default_algorithms()[self.alg].to_jwk(
            self._priv.public_key(), as_dict=True
        )
        pub["kid"] = self.kid
        pub["alg"] = self.alg
        pub["use"] = "sig"
        return pub

    def sign(
        self,
        *,
        sub: str = "11111111-2222-3333-4444-555555555555",
        aud: str | None = _AUD,
        exp_delta: int = 3600,
        extra: dict[str, Any] | None = None,
        kid: str | None = None,
    ) -> str:
        claims: dict[str, Any] = {"sub": sub, "exp": int(time.time()) + exp_delta}
        if aud is not None:
            claims["aud"] = aud
        if extra:
            claims.update(extra)
        return jwt.encode(claims, self._priv, algorithm=self.alg, headers={"kid": kid or self.kid})


@pytest.fixture
def ec_key() -> _KeyPair:
    return _KeyPair("ES256", "ec-kid-1")


@pytest.fixture
def rsa_key() -> _KeyPair:
    return _KeyPair("RS256", "rsa-kid-1")


def _verifier_over(*keys: _KeyPair) -> tuple[JWTVerifier, list[int]]:
    """A verifier whose JWKS 'fetch' serves `keys` and counts how many times it
    was called — so a test can assert the cache never refetches per request."""
    calls = [0]

    def http_get(_url: str) -> dict[str, Any]:
        calls[0] += 1
        return {"keys": [k.public_jwk() for k in keys]}

    return JWTVerifier(_JWKS_URL, audience=_AUD, http_get=http_get), calls


# ── AC-1.1 — valid token → sub is the identity; sub is the ONLY claim trusted ──


def test_s1_ac1_es256_valid_token_returns_sub(ec_key: _KeyPair) -> None:
    verifier, _ = _verifier_over(ec_key)
    token = ec_key.sign(sub="abc-sub-uuid")
    assert verifier.verify(token) == "abc-sub-uuid"


def test_s1_ac1_rs256_valid_token_returns_sub(rsa_key: _KeyPair) -> None:
    """Rotation onto RSA still verifies with no code change (pinned allow-set)."""
    verifier, _ = _verifier_over(rsa_key)
    token = rsa_key.sign(sub="rsa-sub-uuid")
    assert verifier.verify(token) == "rsa-sub-uuid"


def test_s1_ac1_mixed_keyset_both_algs_verify(ec_key: _KeyPair, rsa_key: _KeyPair) -> None:
    verifier, _ = _verifier_over(ec_key, rsa_key)
    assert verifier.verify(ec_key.sign(sub="ec")) == "ec"
    assert verifier.verify(rsa_key.sign(sub="rsa")) == "rsa"


def test_s1_ac1_identity_is_sub_not_other_claims(ec_key: _KeyPair) -> None:
    verifier, _ = _verifier_over(ec_key)
    # A spoofed viewer_id/email claim must be ignored — only sub is identity.
    token = ec_key.sign(sub="real-sub", extra={"viewer_id": "mem:admin", "email": "x@y.z"})
    assert verifier.verify(token) == "real-sub"


# ── AC-1.2 — missing/expired/garbage/no-sub → fail closed (AuthError) ──


def test_s1_ac2_expired_token_rejected(ec_key: _KeyPair) -> None:
    verifier, _ = _verifier_over(ec_key)
    with pytest.raises(AuthError):
        verifier.verify(ec_key.sign(exp_delta=-10))


def test_s1_ac2_garbage_token_rejected(ec_key: _KeyPair) -> None:
    verifier, _ = _verifier_over(ec_key)
    with pytest.raises(AuthError):
        verifier.verify("not.a.jwt")


def test_s1_ac2_token_without_sub_rejected(ec_key: _KeyPair) -> None:
    verifier, _ = _verifier_over(ec_key)
    with pytest.raises(AuthError):
        verifier.verify(ec_key.sign(sub="", extra=None))


def test_s1_ac2_wrong_audience_rejected(ec_key: _KeyPair) -> None:
    verifier, _ = _verifier_over(ec_key)
    with pytest.raises(AuthError):
        verifier.verify(ec_key.sign(aud="some-other-service"))


def test_s1_ac2_token_signed_by_foreign_key_rejected(ec_key: _KeyPair) -> None:
    """A token whose kid IS served but whose signature is from a DIFFERENT private
    key must fail (the verifier trusts the JWKS public key, not the token)."""
    verifier, _ = _verifier_over(ec_key)
    impostor = _KeyPair("ES256", ec_key.kid)  # same kid, different key material
    with pytest.raises(AuthError):
        verifier.verify(impostor.sign())


def test_s1_ac2_hs256_confusion_rejected(ec_key: _KeyPair) -> None:
    """An HS256 token forged with the public key as the HMAC secret must never
    verify — only asymmetric algs are in the pinned allow-set (alg-confusion)."""
    verifier, _ = _verifier_over(ec_key)
    pub_pem = "public"  # any secret; the point is HS* is refused before verification
    forged = jwt.encode(
        {"sub": "attacker", "exp": int(time.time()) + 60, "aud": _AUD},
        pub_pem,
        algorithm="HS256",
        headers={"kid": ec_key.kid},
    )
    with pytest.raises(AuthError):
        verifier.verify(forged)


# ── AC-1.3 — JWKS cached (no per-request fetch); unknown kid → one refetch → closed ──


def test_s1_ac3_jwks_cached_no_per_request_fetch(ec_key: _KeyPair) -> None:
    verifier, calls = _verifier_over(ec_key)
    token = ec_key.sign()
    verifier.verify(token)
    verifier.verify(token)
    verifier.verify(token)
    assert calls[0] == 1  # fetched once, then served from cache


def test_s1_ac3_unknown_kid_triggers_exactly_one_refetch_then_serves(ec_key: _KeyPair) -> None:
    """Key rotation: a kid unknown to the cache refetches ONCE; if the refetched
    set now contains it, verification proceeds."""
    served = {"keys": [ec_key]}  # start with only the ec key
    calls = [0]

    rotated = _KeyPair("ES256", "rotated-kid")

    def http_get(_url: str) -> dict[str, Any]:
        calls[0] += 1
        return {"keys": [k.public_jwk() for k in served["keys"]]}

    verifier = JWTVerifier(_JWKS_URL, audience=_AUD, http_get=http_get)
    # Prime the cache with the original key.
    verifier.verify(ec_key.sign())
    assert calls[0] == 1
    # Now a token under a rotated kid arrives; make the endpoint start serving it.
    served["keys"] = [ec_key, rotated]
    assert verifier.verify(rotated.sign()) is not None
    assert calls[0] == 2  # exactly one refetch on the miss


def test_s1_ac3_unknown_kid_still_unknown_after_refetch_fails_closed(ec_key: _KeyPair) -> None:
    """A kid absent even after the single refetch must fail closed, and must not
    refetch again on the same call (exactly one refetch — no thundering herd)."""
    calls = [0]

    def http_get(_url: str) -> dict[str, Any]:
        calls[0] += 1
        return {"keys": [ec_key.public_jwk()]}  # never contains the impostor kid

    verifier = JWTVerifier(_JWKS_URL, audience=_AUD, http_get=http_get)
    foreign = _KeyPair("ES256", "never-served-kid")
    with pytest.raises(AuthError):
        verifier.verify(foreign.sign())
    assert calls[0] == 1  # one refetch, then closed (cache was empty → the miss fetch)


def test_s1_ac3_token_without_kid_rejected(ec_key: _KeyPair) -> None:
    verifier, _ = _verifier_over(ec_key)
    # Sign with an empty kid header — no key can be selected → fail closed.
    token = jwt.encode(
        {"sub": "x", "exp": int(time.time()) + 60, "aud": _AUD},
        ec_key._priv,
        algorithm="ES256",
    )
    with pytest.raises(AuthError):
        verifier.verify(token)


# ── config resolution (fail-closed default) ──


def test_jwks_url_explicit_wins() -> None:
    assert jwks_url_from_env({"ADVENTURE_SUPABASE_JWKS_URL": "https://x/y"}) == "https://x/y"


def test_jwks_url_derived_from_supabase_url() -> None:
    url = jwks_url_from_env({"SUPABASE_URL": "https://proj.supabase.co"})
    assert url == "https://proj.supabase.co/auth/v1/.well-known/jwks.json"


def test_jwks_url_none_when_unset_fail_closed() -> None:
    assert jwks_url_from_env({}) is None


def test_build_verifier_none_when_unconfigured() -> None:
    assert build_verifier({}) is None


def test_build_verifier_sets_issuer_from_supabase_url() -> None:
    v = build_verifier({"SUPABASE_URL": "https://proj.supabase.co"})
    assert v is not None
    assert v._issuer == "https://proj.supabase.co/auth/v1"
