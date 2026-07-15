"""Epic 043 — managed auth at the edge (Supabase JWT replaces the shared secret).

`_resolve_viewer` returns the AUTHORITATIVE viewer_id: a verified Bearer token's
`sub` (never the client-claimed `viewer_id`), anonymous when no credentials are
present, or — only when the retired dev-secret path is hard-gated ON — the
client's viewer_id behind the shared secret. Anonymous browsing is preserved by
construction; a forged/expired token or a non-anonymous viewer with no token
fails closed (403).

Fully hermetic: an EC P-256 (ES256) keypair signs tokens locally and the JWKS
"endpoint" is an injected callable — no live Supabase, no network.
"""

from __future__ import annotations

import time
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
from fastapi.testclient import TestClient

import api.app as app_mod
from api.app import app
from api.auth import JWTVerifier
from orchestration.config import Settings

_PLAN_BODY = {"query": "trails near me", "lat": 38.5, "lon": -78.4}
_AUD = "authenticated"


# ── Hermetic ES256 signing (matches the live Supabase project's alg) ──


class _Signer:
    def __init__(self, kid: str = "test-kid") -> None:
        self.kid = kid
        self._priv = ec.generate_private_key(ec.SECP256R1())

    def jwk(self) -> dict[str, Any]:
        pub = jwt.algorithms.get_default_algorithms()["ES256"].to_jwk(
            self._priv.public_key(), as_dict=True
        )
        pub.update({"kid": self.kid, "alg": "ES256", "use": "sig"})
        return pub

    def token(self, sub: str, *, exp_delta: int = 3600) -> str:
        return jwt.encode(
            {"sub": sub, "aud": _AUD, "exp": int(time.time()) + exp_delta},
            self._priv,
            algorithm="ES256",
            headers={"kid": self.kid},
        )


def _install_verifier(signer: _Signer) -> None:
    app_mod._jwt_verifier = JWTVerifier(
        "https://example.test/jwks", audience=_AUD, http_get=lambda _u: {"keys": [signer.jwk()]}
    )


def _clear_verifier() -> None:
    app_mod._jwt_verifier = None


# ── S1 (logic) — _resolve_viewer's verified-identity / fail-closed rules ──


def test_s1_resolve_viewer_token_sub_is_authoritative() -> None:
    signer = _Signer()
    _install_verifier(signer)
    app_mod._settings = Settings.from_env({})
    # A token's sub wins even when the client claims a different viewer_id.
    vid = app_mod._resolve_viewer("mem:someone-else", f"Bearer {signer.token('sub-josh')}", None)
    assert vid == "sub-josh"
    _clear_verifier()


def test_s1_resolve_viewer_forged_token_fails_closed() -> None:
    signer = _Signer()
    _install_verifier(signer)
    app_mod._settings = Settings.from_env({})
    impostor = _Signer(kid=signer.kid)  # same kid, different key
    with pytest.raises(HTTPException) as e:
        app_mod._resolve_viewer("anonymous", f"Bearer {impostor.token('x')}", None)
    assert e.value.status_code == 403  # a forged token never downgrades to anonymous
    _clear_verifier()


def test_s1_resolve_viewer_expired_token_fails_closed() -> None:
    signer = _Signer()
    _install_verifier(signer)
    app_mod._settings = Settings.from_env({})
    with pytest.raises(HTTPException) as e:
        app_mod._resolve_viewer("anonymous", f"Bearer {signer.token('x', exp_delta=-5)}", None)
    assert e.value.status_code == 403
    _clear_verifier()


def test_s1_resolve_viewer_token_but_no_verifier_fails_closed() -> None:
    """A token presented when managed auth isn't wired must fail closed, not fall
    through to a weaker path (production keeps anonymous-only with zero env)."""
    _clear_verifier()
    app_mod._settings = Settings.from_env({})
    with pytest.raises(HTTPException) as e:
        app_mod._resolve_viewer("anonymous", "Bearer whatever", None)
    assert e.value.status_code == 403


def test_s1_bearer_header_parsing() -> None:
    assert app_mod._bearer_token("Bearer abc") == "abc"
    assert app_mod._bearer_token("bearer abc") == "abc"  # case-insensitive scheme
    assert app_mod._bearer_token("Basic abc") is None
    assert app_mod._bearer_token("Bearer ") is None
    assert app_mod._bearer_token("abc") is None
    assert app_mod._bearer_token(None) is None


# ── S2 — anonymous browsing preserved by construction ──
#
# The full anonymous-/plan-returns-200 DoD regression lives in test_api_endpoints.py
# (test_s2_ac1_anonymous_plan_200_zero_credentials), which stubs the engine so a real
# 200 is produced. These tests focus on the auth DECISION: an anonymous request is
# never an auth rejection, a non-anonymous viewer with no token/secret 403s.


def test_s2_anonymous_plan_not_an_auth_rejection() -> None:
    _clear_verifier()
    with TestClient(app) as client:
        app_mod._settings = Settings.from_env({})
        r = client.post("/plan", json={**_PLAN_BODY, "viewer_id": "anonymous"})
    assert r.status_code not in (401, 403)


def test_s2_anonymous_search_not_an_auth_rejection() -> None:
    _clear_verifier()
    with TestClient(app) as client:
        app_mod._settings = Settings.from_env({})
        r = client.post("/search", json={"query": "Old Rag"})
    assert r.status_code not in (401, 403)


def test_s2_anonymous_trail_detail_not_an_auth_rejection() -> None:
    _clear_verifier()
    with TestClient(app) as client:
        app_mod._settings = Settings.from_env({})
        # 404 (unknown trail) or 200 — the point is it is NOT an auth rejection.
        r = client.get("/trail/ct:does-not-exist")
    assert r.status_code not in (401, 403)


def test_s2_ac2_no_global_auth_wall_forged_viewer_id_rejected() -> None:
    """Auth is per-route, only where the private overlay is touched: an anonymous
    request is open, a non-anonymous viewer_id with no token/secret 403s."""
    _clear_verifier()
    with TestClient(app) as client:
        app_mod._settings = Settings.from_env({})  # no secret, no managed auth
        r = client.post("/plan", json={**_PLAN_BODY, "viewer_id": "mem:josh"})
    assert r.status_code == 403


def test_s2_plan_with_valid_token_passes_the_guard() -> None:
    """A valid token clears the guard (a downstream 500 from the un-stubbed engine
    is fine here — the point is it is NOT a 401/403)."""
    signer = _Signer()
    with TestClient(app) as client:
        app_mod._settings = Settings.from_env({})
        # Install AFTER lifespan startup: the TestClient's lifespan rebuilds the
        # verifier from env (None here), so a pre-context install would be clobbered.
        _install_verifier(signer)
        r = client.post(
            "/plan",
            json={**_PLAN_BODY, "viewer_id": "anonymous"},
            headers={"Authorization": f"Bearer {signer.token('sub-uuid-1')}"},
        )
    assert r.status_code not in (401, 403)
    _clear_verifier()


# ── S3 — the retired dev-secret is hard-gated OFF by default ──


def test_s3_dev_secret_ignored_when_gate_off() -> None:
    """With the secret configured but ADVENTURE_ALLOW_DEV_VIEWER_SECRET unset, the
    dev-secret path is dead: a non-anonymous viewer_id + correct secret still 403s.
    Production sets neither the gate nor the secret, so this is belt-and-suspenders."""
    _clear_verifier()
    with TestClient(app) as client:
        app_mod._settings = Settings.from_env({"ADVENTURE_DEV_VIEWER_SECRET": "s3cret"})
        r = client.post(
            "/plan",
            json={**_PLAN_BODY, "viewer_id": "mem:josh"},
            headers={"X-Dev-Viewer-Secret": "s3cret"},
        )
    assert r.status_code == 403


def test_s3_dev_secret_gate_on_accepts_and_fails_closed() -> None:
    """The hard-gated local-dev escape hatch: with the gate explicitly on, the
    correct secret clears the guard; a wrong/absent secret still 403s. (The gate-on
    accept is exercised end-to-end with a stubbed engine in test_api_endpoints.py.)"""
    _clear_verifier()
    app_mod._settings = Settings.from_env(
        {"ADVENTURE_DEV_VIEWER_SECRET": "s3cret", "ADVENTURE_ALLOW_DEV_VIEWER_SECRET": "1"}
    )
    assert app_mod._resolve_viewer("mem:josh", None, "s3cret") == "mem:josh"
    with pytest.raises(HTTPException) as wrong:
        app_mod._resolve_viewer("mem:josh", None, "nope")
    assert wrong.value.status_code == 403
    with pytest.raises(HTTPException) as missing:
        app_mod._resolve_viewer("mem:josh", None, None)
    assert missing.value.status_code == 403


def test_s3_dev_secret_non_ascii_header_is_clean_403_not_500() -> None:
    _clear_verifier()
    app_mod._settings = Settings.from_env(
        {"ADVENTURE_DEV_VIEWER_SECRET": "s3cret", "ADVENTURE_ALLOW_DEV_VIEWER_SECRET": "1"}
    )
    with pytest.raises(HTTPException) as e:
        app_mod._resolve_viewer("mem:josh", None, "wrőng")
    assert e.value.status_code == 403
