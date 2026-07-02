"""Epic 018 S3 — live smoke test each enabled adapter at real Shenandoah coords (AC-3.1).

These are the *record* side of the cassette gate: they call the real APIs and assert a
correct stamped `VerifiedFact` with its origin fields, so the recorded cassettes stay
honest to the live schema. They never run in `make check` — the whole module is
skipped unless `ADVENTURE_LIVE_SMOKE=1`, and each keyed adapter self-skips when its
credential is absent (source-or-silence: a missing key is an absent probe, not a
failure). Run manually where egress is open:

    ADVENTURE_LIVE_SMOKE=1 NWS_USER_AGENT="you@example.com" \
        AIRNOW_API_KEY=... FIRMS_MAP_KEY=... RIDB_API_KEY=... \
        pytest -m live_smoke -q

`make check` deselects this via `-m "not neo4j"` only if we also mark it; to be safe the
module-level skip guarantees it is inert without the opt-in env var regardless of `-m`.
"""

from __future__ import annotations

import os

import pytest

from orchestration.adapters.airnow import AirNowAdapter
from orchestration.adapters.base import Point, VerifiedFact
from orchestration.adapters.firms import FirmsAdapter
from orchestration.adapters.nws import NwsAdapter
from orchestration.adapters.ridb import RidbAdapter
from orchestration.adapters.usgs_water import UsgsWaterAdapter

pytestmark = pytest.mark.live_smoke

if os.environ.get("ADVENTURE_LIVE_SMOKE") != "1":
    pytest.skip("live smoke disabled (set ADVENTURE_LIVE_SMOKE=1 to run)", allow_module_level=True)

# Big Meadows, Shenandoah NP — a point with real weather, a nearby USGS gauge, and
# RIDB facilities.
_POINT = Point(38.5219, -78.4356)


def test_nws_live() -> None:
    ua = os.environ.get("NWS_USER_AGENT")
    if not ua:
        pytest.skip("NWS_USER_AGENT unset")
    fact = NwsAdapter(ua).probe(_POINT)
    assert isinstance(fact, VerifiedFact)
    assert fact.source.startswith("NWS") and fact.fetched_at is not None
    assert fact.value.get("short_forecast")
    assert fact.value.get("forecast_office")  # origin-at-boundary present live


def test_usgs_live() -> None:
    fact = UsgsWaterAdapter().probe(_POINT)  # keyless
    assert isinstance(fact, VerifiedFact)
    assert fact.source.startswith("USGS") and fact.fetched_at is not None
    assert fact.value.get("site_id")  # nearest-gauge origin id present live
    assert fact.disclosures  # nearest-gauge-distance disclosure travels with the fact


def test_airnow_live() -> None:
    key = os.environ.get("AIRNOW_API_KEY")
    if not key:
        pytest.skip("AIRNOW_API_KEY unset")
    fact = AirNowAdapter(key).probe(_POINT)
    # AirNow can legitimately have no observation at a point — silence is a valid answer.
    if fact is None:
        pytest.skip("AirNow returned no observation at the point")
    assert isinstance(fact, VerifiedFact)
    assert fact.source == "EPA AirNow" and fact.value.get("aqi") is not None


def test_firms_live() -> None:
    key = os.environ.get("FIRMS_MAP_KEY")
    if not key:
        pytest.skip("FIRMS_MAP_KEY unset")
    fact = FirmsAdapter(key).probe(_POINT)
    assert isinstance(fact, VerifiedFact)  # zero detections is still a stamped fact
    assert fact.source == "NASA FIRMS"
    assert fact.value.get("hotspot_count") is not None
    assert isinstance(fact.value.get("satellites"), list)  # origin column present/empty


def test_ridb_live() -> None:
    key = os.environ.get("RIDB_API_KEY")
    if not key:
        pytest.skip("RIDB_API_KEY unset")
    fact = RidbAdapter(key).probe(_POINT)
    if fact is None:
        pytest.skip("RIDB returned no facilities near the point")
    assert isinstance(fact, VerifiedFact)
    assert fact.source == "Recreation.gov RIDB" and fact.value.get("count") is not None
