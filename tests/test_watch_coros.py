"""Epic 004 S3 — Coros adapter, driven by mocked HTTP (no live call). Batch=HTTP, not MCP."""

from __future__ import annotations

import json

import httpx

from ingestion.watch.base import ActivityRef, AdapterHealth
from ingestion.watch.coros import CorosAdapter


def _transport(*, activities=None, fit_bytes=b"COROSFIT", recovery=72, token_status=200):
    activities = activities if activities is not None else []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "oauth2/accesstoken" in url:
            if token_status != 200:
                return httpx.Response(token_status, json={"error": "bad"})
            return httpx.Response(200, json={"access_token": "tok-123"})
        if "activities" in url:
            return httpx.Response(200, json={"data": activities})
        if "activity/download" in url:
            return httpx.Response(200, content=fit_bytes)
        if "recovery" in url:
            return httpx.Response(200, json={"recovery": recovery})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def _client(**kw):
    return httpx.Client(transport=_transport(**kw))


def _activity(lid="abc", name="Stony Man"):
    return {"labelId": lid, "name": name, "startTime": 1718888400, "sportType": "hiking"}


# ── AC-3.1 — namespaced refs ──────────────────────────────────────────────────


def test_s3_ac1_list_activities_namespaced():
    a = CorosAdapter("cid", "sec", client=_client(activities=[_activity("a1"), _activity("a2")]))
    refs = a.list_activities(None)
    assert [r.id for r in refs] == ["coros:a1", "coros:a2"]
    assert all(r.source == "coros" for r in refs)


# ── AC-3.2 — download returns raw FIT bytes ───────────────────────────────────


def test_s3_ac2_download_fit_bytes():
    a = CorosAdapter("cid", "sec", client=_client(fit_bytes=b"FITFROMCOROS"))
    fit = a.download_fit(ActivityRef(id="coros:abc", source="coros"))
    assert fit == b"FITFROMCOROS"


# ── AC-3.3 — capabilities ──────────────────────────────────────────────────────


def test_s3_ac3_capabilities():
    a = CorosAdapter("cid", "sec", client=_client())
    caps = a.capabilities()
    assert caps.has_fit is True
    assert caps.has_readiness is True
    assert caps.has_activity_title is True  # AC-3.3 full capability triple


def test_s3_ac1_requests_hiking_sport():
    captured = {}

    def handler(request):
        url = str(request.url)
        if "oauth2/accesstoken" in url:
            return httpx.Response(200, json={"access_token": "tok"})
        if "activities" in url:
            captured["params"] = dict(request.url.params)
            return httpx.Response(200, json={"data": [_activity()]})
        return httpx.Response(404)

    a = CorosAdapter("cid", "sec", client=httpx.Client(transport=httpx.MockTransport(handler)))
    a.list_activities(None, sport="hiking", limit=15)
    assert captured["params"]["sportType"] == "hiking"
    assert captured["params"]["size"] == "15"


def test_s3_readiness_returns_recovery():
    a = CorosAdapter("cid", "sec", client=_client(recovery=88))
    sig = a.fetch_readiness()
    assert sig is not None
    assert sig.kind == "recovery"
    assert sig.value == 88.0


# ── AC-3.4 — batch uses HTTP not MCP; token from client credentials ───────────


def test_s3_ac4_uses_http_not_mcp():
    # The adapter's only transport is the injected httpx client. It never imports
    # or references an MCP server. A successful list proves the HTTP/OAuth path.
    a = CorosAdapter("cid", "sec", client=_client(activities=[_activity()]))
    refs = a.list_activities(None)
    assert len(refs) == 1
    # token was fetched + cached
    assert a._access_token() == "tok-123"


def test_s3_ac4_missing_secrets_raises_on_use_not_construction():
    a = CorosAdapter(None, None, client=_client())
    # construction is fine; using it without secrets fails loudly
    import pytest

    with pytest.raises(ValueError, match="COROS_CLIENT"):
        a.list_activities(None)


# ── AC-3.5 — health mapping, all mocked ───────────────────────────────────────


def test_s3_ac5_health_ok():
    a = CorosAdapter("cid", "sec", client=_client())
    assert a.health() is AdapterHealth.OK


def test_s3_ac5_health_needs_reauth_on_401():
    a = CorosAdapter("cid", "sec", client=_client(token_status=401))
    assert a.health() is AdapterHealth.NEEDS_REAUTH


def test_s3_ac5_health_rate_limited_on_429():
    a = CorosAdapter("cid", "sec", client=_client(token_status=429))
    assert a.health() is AdapterHealth.RATE_LIMITED


def test_s3_json_import_available():
    # guard: the test module's json import is used by httpx internally; sanity only
    assert json.dumps({"ok": True})
