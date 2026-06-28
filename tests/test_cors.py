"""CORS edge tests (deploy contract).

The hosted API is default-deny: only the origins in ADVENTURE_CORS_ALLOW_ORIGINS
(e.g. the Vercel frontend) may call it from a browser. These exercise the real
`api.app._install_cors` wiring through Starlette against a throwaway app, so a
regression in how Settings feeds the middleware is caught here — not in the browser,
and without depending on what the env happens to be at import time.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.app import _install_cors
from orchestration.config import Settings

_VERCEL = "https://hike-app.vercel.app"


def _app_with_origins(env: dict[str, str]) -> FastAPI:
    app = FastAPI()

    @app.get("/ping")
    def _ping() -> dict[str, bool]:
        return {"ok": True}

    _install_cors(app, Settings.from_env(env))
    return app


def test_configured_origin_is_allowed() -> None:
    client = TestClient(_app_with_origins({"ADVENTURE_CORS_ALLOW_ORIGINS": _VERCEL}))
    r = client.get("/ping", headers={"Origin": _VERCEL})
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == _VERCEL


def test_preflight_allows_custom_auth_header() -> None:
    # The frontend sends X-Dev-Viewer-Secret (Epic 014); its preflight must pass.
    client = TestClient(_app_with_origins({"ADVENTURE_CORS_ALLOW_ORIGINS": _VERCEL}))
    r = client.options(
        "/ping",
        headers={
            "Origin": _VERCEL,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-dev-viewer-secret",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == _VERCEL
    assert "x-dev-viewer-secret" in r.headers["access-control-allow-headers"].lower()


def test_default_deny_blocks_unlisted_origin() -> None:
    # No ADVENTURE_CORS_ALLOW_ORIGINS → empty allow-list → no CORS header echoed.
    client = TestClient(_app_with_origins({}))
    r = client.get("/ping", headers={"Origin": _VERCEL})
    assert r.status_code == 200  # the request still runs server-side...
    assert "access-control-allow-origin" not in r.headers  # ...but the browser blocks it


def test_unlisted_origin_blocked_even_when_an_origin_is_allowed() -> None:
    client = TestClient(_app_with_origins({"ADVENTURE_CORS_ALLOW_ORIGINS": _VERCEL}))
    r = client.get("/ping", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers
