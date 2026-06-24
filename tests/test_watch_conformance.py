"""Epic 004 S5 — shared adapter conformance suite + drop-in guarantee.

A parametrized contract test that EVERY device adapter must satisfy (driven by its
mocked client — no live calls). Adding a new adapter = add it to `_adapters()` and
it is automatically held to the contract. The StubAdapter below proves AC-5.2: a
brand-new vendor flows through the unchanged poller with zero downstream edits.
"""

from __future__ import annotations

import io
import zipfile
from types import SimpleNamespace

import httpx
import pytest

import ingestion.watch as watch_pkg
from ingestion.watch.base import (
    ActivityRef,
    AdapterHealth,
    Capabilities,
    DeviceAdapter,
    RawActivity,
)
from ingestion.watch.coros import CorosAdapter
from ingestion.watch.garmin import GarminAdapter
from scripts.watch_sync import run_sync

# ── Mock-client builders (no live device) ─────────────────────────────────────


class _FakeGarth:
    def connectapi(self, path, params=None):
        if "activities" in path:
            return [
                {"activityId": 7, "activityName": "Hike", "activityType": {"typeKey": "hiking"}}
            ]
        if "bodyBattery" in path:
            return [{"charged": 75}]  # positive readiness path
        return {}

    def download(self, path):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("7.fit", b"FITBYTES")
        return buf.getvalue()


def _coros_client():
    def handler(request):
        url = str(request.url)
        if "oauth2/accesstoken" in url:
            return httpx.Response(200, json={"access_token": "tok"})
        if "activities" in url:
            return httpx.Response(
                200, json={"data": [{"labelId": "z9", "name": "Hike", "sportType": "hiking"}]}
            )
        if "activity/download" in url:
            return httpx.Response(200, content=b"FITBYTES")
        if "recovery" in url:
            return httpx.Response(200, json={"recovery": 70})
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


class StubAdapter(DeviceAdapter):
    """A minimal new vendor — ONE file, proving the drop-in guarantee (AC-5.2).
    No readiness API → fetch_readiness returns None (degrade-and-disclose)."""

    name = "stub"

    def capabilities(self):
        return Capabilities(has_fit=True, has_readiness=False, has_activity_title=False)

    def list_activities(self, since, *, sport="hiking", limit=20):
        return [ActivityRef(id="stub:1", source="stub")]

    def download_fit(self, ref):
        return b"STUBFIT"

    def fetch_readiness(self, *, at=None):
        return None  # has_readiness=False

    def health(self):
        return AdapterHealth.OK


def _adapters() -> list[DeviceAdapter]:
    """Every adapter under test, each wired with its mock client."""
    return [
        GarminAdapter("e@x.c", "pw", client=_FakeGarth()),
        CorosAdapter("cid", "sec", client=_coros_client()),
        StubAdapter(),
    ]


# ── AC-5.1 — the contract every adapter must satisfy ──────────────────────────


@pytest.mark.parametrize("adapter", _adapters(), ids=lambda a: a.name)
def test_s5_ac1_namespaced_ids(adapter):
    refs = adapter.list_activities(None)
    assert refs, f"{adapter.name} returned no activities"
    assert all(r.id.startswith(f"{adapter.name}:") for r in refs)


@pytest.mark.parametrize("adapter", _adapters(), ids=lambda a: a.name)
def test_s5_ac1_download_returns_bytes(adapter):
    ref = adapter.list_activities(None)[0]
    fit = adapter.download_fit(ref)
    assert isinstance(fit, bytes) and len(fit) > 0


@pytest.mark.parametrize("adapter", _adapters(), ids=lambda a: a.name)
def test_s5_ac1_capabilities_shape(adapter):
    caps = adapter.capabilities()
    assert isinstance(caps, Capabilities)
    assert isinstance(caps.has_fit, bool)
    assert isinstance(caps.has_readiness, bool)
    assert isinstance(caps.has_activity_title, bool)


@pytest.mark.parametrize("adapter", _adapters(), ids=lambda a: a.name)
def test_s5_ac1_health_valid_state(adapter):
    assert adapter.health() in set(AdapterHealth)


@pytest.mark.parametrize("adapter", _adapters(), ids=lambda a: a.name)
def test_s5_ac1_readiness_none_when_unsupported(adapter):
    if not adapter.capabilities().has_readiness:
        assert adapter.fetch_readiness() is None


@pytest.mark.parametrize("adapter", _adapters(), ids=lambda a: a.name)
def test_s5_ac1_readiness_signal_when_supported(adapter):
    # Positive path: an adapter declaring readiness must return a usable signal.
    if adapter.capabilities().has_readiness:
        sig = adapter.fetch_readiness()
        assert sig is not None
        assert isinstance(sig.value, float)
        assert sig.kind and sig.source


@pytest.mark.parametrize("adapter", _adapters(), ids=lambda a: a.name)
def test_s5_ac1_list_activities_with_datetime_since(adapter):
    # Exercise the since!=None branch of every adapter (caught the str-since crash).
    from datetime import datetime, timezone

    refs = adapter.list_activities(datetime(2020, 1, 1, tzinfo=timezone.utc))
    assert all(r.id.startswith(f"{adapter.name}:") for r in refs)


@pytest.mark.parametrize("adapter", _adapters(), ids=lambda a: a.name)
def test_s5_ac1_fetch_new_activities_yields_raw(adapter):
    raws = adapter.fetch_new_activities(None)
    assert raws and all(isinstance(r, RawActivity) for r in raws)
    assert all(r.id.startswith(f"{adapter.name}:") for r in raws)


# ── AC-5.2 — drop-in: new adapter flows through the UNCHANGED poller ──────────


def test_s5_ac2_stub_adapter_flows_through_unchanged_poller():
    """Adding StubAdapter required: one class above, zero edits to parse/Episode/
    belief/poller. This test passing IS the assertion."""
    created = []

    def parse(fit_bytes):
        return SimpleNamespace(watch_activity_id="file:x")

    def match(summary, session):
        return None

    def create(summary, cid, owner, session, *, belief_queue=None):
        created.append(summary.watch_activity_id)
        return "ep:x"

    report = run_sync(
        [StubAdapter()],
        "josh",
        since=None,
        parse=parse,
        match=match,
        create=create,
        session=object(),
        belief_queue=object(),
    )
    assert created == ["stub:1"]  # namespaced, flowed through with no downstream change
    assert report.total_episodes == 1


# ── AC-5.3 — checklist referenced from the package docstring ───────────────────


def test_s5_ac3_package_docstring_references_checklist():
    assert watch_pkg.__doc__ is not None
    assert "device-integration-seam.md §6" in watch_pkg.__doc__
