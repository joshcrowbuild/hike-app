"""Epic 004 S1 — device-seam base contract + canonical types.

test_s{story}_{ac}_{description}. No network; a minimal concrete adapter exercises
the contract and the default fetch_new_activities.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ingestion.watch.base import (
    ActivityRef,
    AdapterHealth,
    Capabilities,
    DeviceAdapter,
    RawActivity,
    ReadinessSignal,
)


class _FakeAdapter(DeviceAdapter):
    name = "fake"

    def __init__(self, *, has_fit=True, refs=None, fit=b"FIT", fail_download_for=None):
        self._has_fit = has_fit
        self._refs = refs or []
        self._fit = fit
        self._fail = fail_download_for or set()

    def capabilities(self):
        return Capabilities(has_fit=self._has_fit, has_readiness=False, has_activity_title=True)

    def list_activities(self, since, *, sport="hiking", limit=20):
        return list(self._refs)

    def download_fit(self, ref):
        if ref.id in self._fail:
            raise RuntimeError("download boom")
        return self._fit

    def fetch_readiness(self, *, at=None):
        return None

    def health(self):
        return AdapterHealth.OK


def _ref(rid: str) -> ActivityRef:
    return ActivityRef(id=rid, source="fake", title="t", start_time=None, sport="hiking")


# ── AC-1.1 — contract shape ───────────────────────────────────────────────────


def test_s1_ac1_contract_methods_exist():
    a = _FakeAdapter()
    assert a.name == "fake"
    assert isinstance(a.capabilities(), Capabilities)
    assert a.list_activities(None) == []
    assert a.fetch_readiness() is None
    assert a.health() is AdapterHealth.OK
    # default method present and callable
    assert hasattr(a, "fetch_new_activities")


def test_s1_ac1_fetch_new_activities_default_builds_raw():
    refs = [_ref("fake:1"), _ref("fake:2")]
    a = _FakeAdapter(refs=refs, fit=b"FITDATA")
    raws = a.fetch_new_activities(None)
    assert len(raws) == 2
    assert all(isinstance(r, RawActivity) for r in raws)
    assert raws[0].fit_bytes == b"FITDATA"


def test_s1_ac1_fetch_new_activities_skips_failed_download():
    refs = [_ref("fake:1"), _ref("fake:2")]
    a = _FakeAdapter(refs=refs, fail_download_for={"fake:1"})
    raws = a.fetch_new_activities(None)
    # one download failed → skipped, the other survives (degrade, not fatal)
    assert len(raws) == 1
    assert raws[0].id == "fake:2"


def test_s1_ac1_no_fit_capability_yields_nothing():
    a = _FakeAdapter(has_fit=False, refs=[_ref("fake:1")])
    assert a.fetch_new_activities(None) == []


# ── AC-1.2 — namespaced ids ───────────────────────────────────────────────────


def test_s1_ac2_raw_activity_id_is_namespaced():
    raw = RawActivity(ref=_ref("garmin:999"), fit_bytes=b"x")
    assert raw.id == "garmin:999"
    assert raw.id.split(":", 1)[0] == "garmin"


def test_s1_ac2_non_namespaced_id_rejected():
    # Structural enforcement: a colon-less id would cross-vendor-collide → reject.
    import pytest

    for bad in ["12345", ":12345", ""]:
        with pytest.raises(ValueError, match="namespaced"):
            ActivityRef(id=bad, source="x")


# ── canonical types ───────────────────────────────────────────────────────────


def test_readiness_signal_fields():
    sig = ReadinessSignal(
        value=72.0, kind="body_battery", source="garmin", fetched_at=datetime.now(timezone.utc)
    )
    assert sig.value == 72.0
    assert sig.kind == "body_battery"


def test_adapter_health_states():
    assert {h.value for h in AdapterHealth} == {"ok", "needs_reauth", "rate_limited", "down"}
