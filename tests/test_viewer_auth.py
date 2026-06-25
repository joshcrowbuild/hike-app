"""Epic 014 S3 — viewer_id is honored only from an authenticated caller.

Until the Stage-8 auth system exists, the open anonymous world is the only
unauthenticated path; any other identity must present the configured shared dev
secret, and a deploy with no secret configured fails closed. Covers both the
guard logic and the two endpoints that take a viewer_id (`/plan`,
`/episode/{id}/outcome`).
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import api.app as app_mod
from api.app import app
from orchestration.config import Settings

_PLAN_BODY = {"query": "trails near me", "lat": 38.5, "lon": -78.4}


# ── AC-3.3 (logic) — the guard's fail-closed / accept rules ──


def test_s3_ac3_authorize_viewer_logic() -> None:
    app_mod._settings = Settings.from_env({})  # no dev secret configured
    # anonymous always passes, with or without a header
    app_mod._authorize_viewer("anonymous", None)
    app_mod._authorize_viewer("anonymous", "whatever")
    # non-anonymous with no configured secret → fail closed regardless of header
    with pytest.raises(HTTPException) as e1:
        app_mod._authorize_viewer("mem:josh", "anything")
    assert e1.value.status_code == 403

    app_mod._settings = Settings.from_env({"ADVENTURE_DEV_VIEWER_SECRET": "s3cret"})
    app_mod._authorize_viewer("mem:josh", "s3cret")  # correct secret → passes
    with pytest.raises(HTTPException):
        app_mod._authorize_viewer("mem:josh", "wrong")  # wrong secret → 403
    with pytest.raises(HTTPException):
        app_mod._authorize_viewer("mem:josh", None)  # missing header → 403
    # A non-ASCII header must yield a clean 403, not a TypeError/500 (bytes compare).
    with pytest.raises(HTTPException):
        app_mod._authorize_viewer("mem:josh", "wrőng")


# ── AC-3.1 — /plan rejects a forged (unauthenticated) viewer_id ──


def test_s3_ac1_plan_rejects_forged_viewer_id() -> None:
    with TestClient(app) as client:
        app_mod._settings = Settings.from_env({})  # no secret → fail closed
        r = client.post("/plan", json={**_PLAN_BODY, "viewer_id": "mem:josh"})
        assert r.status_code == 403


# ── AC-3.2 — anonymous succeeds unauthenticated (not an auth rejection) ──


def test_s3_ac2_anonymous_plan_passes_guard() -> None:
    with TestClient(app) as client:
        app_mod._settings = Settings.from_env({})
        r = client.post("/plan", json={**_PLAN_BODY, "viewer_id": "anonymous"})
        assert r.status_code not in (401, 403)  # open path; no auth wall


# ── AC-3.3 — dev secret accepts; absent header / unset secret fail closed ──


def test_s3_ac3_dev_secret_accepts_and_fails_closed() -> None:
    with TestClient(app) as client:
        app_mod._settings = Settings.from_env({"ADVENTURE_DEV_VIEWER_SECRET": "s3cret"})
        ok = client.post(
            "/plan",
            json={**_PLAN_BODY, "viewer_id": "mem:josh"},
            headers={"X-Dev-Viewer-Secret": "s3cret"},
        )
        assert ok.status_code != 403  # correct secret passes the guard
        missing = client.post("/plan", json={**_PLAN_BODY, "viewer_id": "mem:josh"})
        assert missing.status_code == 403  # no header → rejected


def test_s3_ac3_fail_closed_when_secret_unset() -> None:
    with TestClient(app) as client:
        app_mod._settings = Settings.from_env({})  # secret absent from config
        r = client.post(
            "/plan",
            json={**_PLAN_BODY, "viewer_id": "mem:josh"},
            headers={"X-Dev-Viewer-Secret": "anything"},
        )
        assert r.status_code == 403  # fail closed regardless of any header


# ── AC-3.4 — the same guard covers /episode/{id}/outcome ──


def test_s3_ac4_outcome_rejects_forged_viewer_id() -> None:
    with TestClient(app) as client:
        app_mod._settings = Settings.from_env({})
        forged = client.post(
            "/episode/ep-1/outcome", params={"viewer_id": "mem:josh"}, json={"overall": 3}
        )
        assert forged.status_code == 403
        anon = client.post("/episode/ep-1/outcome", json={"overall": 3})
        assert anon.status_code not in (401, 403)  # anonymous default passes the guard
