"""Epic 004 S2 — Garmin adapter, driven entirely by a mocked client (no live call)."""

from __future__ import annotations

import io
import zipfile

from ingestion.watch.base import ActivityRef, AdapterHealth
from ingestion.watch.garmin import GarminAdapter


class _FakeGarthError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


class _FakeGarth:
    def __init__(self, *, activities=None, fit_zip=b"", body_battery=None, auth_error=False):
        self._activities = activities or []
        self._fit_zip = fit_zip
        self._body_battery = body_battery
        self._auth_error = auth_error
        self.last_params = None  # capture what list_activities sent (AC-2.1)

    def connectapi(self, path, params=None):
        if self._auth_error:
            raise _FakeGarthError(401)
        if "activities" in path:
            self.last_params = params
            return self._activities
        if "bodyBattery" in path:
            return self._body_battery
        return {}

    def download(self, path):
        if self._auth_error:
            raise _FakeGarthError(401)
        return self._fit_zip


def _make_fit_zip(fit_bytes: bytes = b"FITCONTENT") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("12345.fit", fit_bytes)
    return buf.getvalue()


def _activity(aid=12345, name="Old Rag Loop"):
    return {
        "activityId": aid,
        "activityName": name,
        "startTimeGMT": "2026-06-20 13:00:00",
        "activityType": {"typeKey": "hiking"},
    }


# ── AC-2.1 — namespaced, hiking, newest-first refs ────────────────────────────


def test_s2_ac1_list_activities_namespaced():
    client = _FakeGarth(activities=[_activity(111), _activity(222)])
    a = GarminAdapter("e@x.c", "pw", client=client)
    refs = a.list_activities(None)
    assert [r.id for r in refs] == ["garmin:111", "garmin:222"]
    assert all(r.source == "garmin" for r in refs)
    assert refs[0].title == "Old Rag Loop"


# ── AC-2.2 — download returns raw FIT bytes from the ZIP ───────────────────────


def test_s2_ac2_download_fit_unzips():
    client = _FakeGarth(fit_zip=_make_fit_zip(b"REALFITBYTES"))
    a = GarminAdapter("e@x.c", "pw", client=client)
    fit = a.download_fit(ActivityRef(id="garmin:12345", source="garmin"))
    assert fit == b"REALFITBYTES"


# ── AC-2.3 — capabilities ──────────────────────────────────────────────────────


def test_s2_ac3_capabilities():
    a = GarminAdapter("e@x.c", "pw", client=_FakeGarth())
    caps = a.capabilities()
    assert caps.has_fit is True
    assert caps.has_readiness is True
    assert caps.has_activity_title is True


def test_s2_readiness_returns_body_battery():
    client = _FakeGarth(body_battery=[{"charged": 80}])
    a = GarminAdapter("e@x.c", "pw", client=client)
    sig = a.fetch_readiness()
    assert sig is not None
    assert sig.kind == "body_battery"
    assert sig.value == 80.0


# ── AC-2.4 — 401 → needs_reauth, no crash ──────────────────────────────────────


def test_s2_ac4_auth_error_yields_needs_reauth():
    # health() probes with a cheap call; an injected client that raises 401 on use
    # must map to needs_reauth (not a crash) — simulating session expiry.
    a = GarminAdapter("e@x.c", "pw", client=_FakeGarth(auth_error=True))
    assert a.health() is AdapterHealth.NEEDS_REAUTH


def test_s2_ac4_healthy_client_reports_ok():
    a = GarminAdapter("e@x.c", "pw", client=_FakeGarth(activities=[_activity()]))
    assert a.health() is AdapterHealth.OK


def test_s2_ac4_is_auth_error_helper():
    from ingestion.watch.garmin import _is_auth_error

    assert _is_auth_error(_FakeGarthError(401)) is True
    assert _is_auth_error(RuntimeError("401 Unauthorized")) is True
    assert _is_auth_error(RuntimeError("connection reset")) is False


# ── AC-2.5 — no live Garmin call (entire suite uses the fake) ──────────────────


def test_s2_ac5_no_live_call_construction_lazy():
    # Constructing with no client and no secrets must not raise or call out.
    a = GarminAdapter(None, None)
    assert a.name == "garmin"
    assert a.capabilities().has_fit is True


# ── AC-2.1 — filtered to hiking; AC-2.4 — credentials required ────────────────


def test_s2_ac1_requests_hiking_sport():
    client = _FakeGarth(activities=[_activity()])
    a = GarminAdapter("e@x.c", "pw", client=client)
    a.list_activities(None, sport="hiking", limit=20)
    assert client.last_params["activityType"] == "hiking"
    assert client.last_params["limit"] == 20


def test_s2_ac4_missing_secrets_raises_on_use():
    # No injected client + no secrets → fail loudly on first real use (not construction).
    import pytest

    a = GarminAdapter(None, None)
    with pytest.raises(ValueError, match="GARMIN_EMAIL"):
        a.list_activities(None)


def test_s2_ac2_since_filters_older_activities():
    from datetime import datetime, timezone

    old = {
        "activityId": 1,
        "activityName": "Old",
        "startTimeGMT": "2020-01-01 10:00:00",
        "activityType": {"typeKey": "hiking"},
    }
    new = {
        "activityId": 2,
        "activityName": "New",
        "startTimeGMT": "2026-06-22 10:00:00",
        "activityType": {"typeKey": "hiking"},
    }
    a = GarminAdapter("e@x.c", "pw", client=_FakeGarth(activities=[old, new]))
    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    refs = a.list_activities(since)
    assert [r.id for r in refs] == ["garmin:2"]  # older one bounded out (AC-4.2)
