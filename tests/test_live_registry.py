"""Epic 013 S2/S4/S5 — the kind-keyed live-adapter registry + TTL cache.

Config-driven selection (drop credential-absent, loud on unknown), kind grouping
ordered primary→fallback, per-region gating, and the per-source TTL cache. No
network — adapters are selected/instantiated, not probed, except the cache test
which drives a call-counting fake.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from orchestration.adapters import registry
from orchestration.adapters.base import (
    AdapterHealth,
    ConditionKind,
    LiveAdapter,
    LiveCapabilities,
    Point,
    VerifiedFact,
)
from orchestration.adapters.nws import NwsAdapter
from orchestration.config import Settings


class _FakeWeather(LiveAdapter):
    """A second weather source so primary→fallback ordering is testable."""

    name = "fakeweather"
    kind = ConditionKind.weather

    def capabilities(self) -> LiveCapabilities:
        return LiveCapabilities(True, False, True, supports_region=frozenset({"US"}))

    def probe(self, point: Point, when: datetime | None = None) -> VerifiedFact | None:
        return None

    def health(self) -> AdapterHealth:
        return AdapterHealth.OK

    @classmethod
    def from_config(cls, settings: Settings) -> "LiveAdapter | None":
        return cls()


# ── AC-2.1 — instantiate from config; drop credential-absent adapters ──


def test_s2_ac1_drops_credential_absent_adapters() -> None:
    s = Settings.from_env(
        {"ADVENTURE_LIVE_ADAPTERS": "nws,airnow", "NWS_USER_AGENT": "ua"}  # no AIRNOW_API_KEY
    )
    names = [a.name for a in registry.enabled_adapters(s)]
    assert names == ["nws"]  # airnow self-dropped (None from from_config)


# ── AC-2.2 — unknown adapter name fails loudly, naming offender + known set ──


def test_s2_ac2_unknown_adapter_raises() -> None:
    s = Settings.from_env({"ADVENTURE_LIVE_ADAPTERS": "nws,bogus", "NWS_USER_AGENT": "ua"})
    with pytest.raises(ValueError) as exc:
        registry.enabled_adapters(s)
    msg = str(exc.value)
    assert "bogus" in msg and "nws" in msg  # offender + the known set


# ── AC-2.3 — grouped by kind, ordered by config position (primary→fallback) ──


def test_s2_ac3_grouped_by_kind_ordered_by_position(monkeypatch: Any) -> None:
    monkeypatch.setitem(registry.ADAPTER_FACTORIES, "fakeweather", _FakeWeather)
    s = Settings.from_env(
        {"ADVENTURE_LIVE_ADAPTERS": "nws,fakeweather,usgs_water", "NWS_USER_AGENT": "ua"}
    )
    grouped = registry.probes_for("US", s)
    assert [a.name for a in grouped[ConditionKind.weather]] == ["nws", "fakeweather"]
    assert [a.name for a in grouped[ConditionKind.water]] == ["usgs_water"]
    assert isinstance(grouped[ConditionKind.weather][0], NwsAdapter)


# ── AC-4.1 / AC-4.2 / AC-4.3 — per-region capability gating ──


def test_s4_ac2_region_gating_excludes_us_only_feed() -> None:
    # Pair the US-only FIRMS with region-agnostic Valhalla to show exclusion is lossless.
    s = Settings.from_env(
        {
            "ADVENTURE_LIVE_ADAPTERS": "firms,valhalla",
            "FIRMS_MAP_KEY": "k",
            "VALHALLA_BASE_URL": "http://valhalla:8002",
        }
    )
    us = registry.probes_for("US", s)
    assert ConditionKind.fire in us  # FIRMS supports US
    non_us = registry.probes_for("CA", s)
    assert ConditionKind.fire not in non_us  # FIRMS excluded outside the US
    # Exclusion is lossless — the region-agnostic drive_time kind is unaffected.
    assert ConditionKind.drive_time in non_us


def test_s4_ac1_empty_region_set_is_region_agnostic() -> None:
    # Valhalla declares supports_region=frozenset() → selected in any region.
    s = Settings.from_env(
        {"ADVENTURE_LIVE_ADAPTERS": "valhalla", "VALHALLA_BASE_URL": "http://valhalla:8002"}
    )
    assert ConditionKind.drive_time in registry.probes_for("CA", s)
    assert ConditionKind.drive_time in registry.probes_for("US", s)


# ── AC-5.4 / AC-5.5 / AC-5.6 — per-source TTL cache ──


class _CountingAdapter(LiveAdapter):
    name = "counting"
    kind = ConditionKind.weather
    ttl_seconds = 600

    def __init__(self) -> None:
        self.calls = 0

    def capabilities(self) -> LiveCapabilities:
        return LiveCapabilities(True, False, True)

    def probe(self, point: Point, when: datetime | None = None) -> VerifiedFact | None:
        self.calls += 1
        return VerifiedFact(value={"n": self.calls}, source="counting", fetched_at=_NOW)

    def health(self) -> AdapterHealth:
        return AdapterHealth.OK

    @classmethod
    def from_config(cls, settings: Settings) -> "LiveAdapter | None":
        return cls()


_NOW = datetime(2026, 6, 24, tzinfo=timezone.utc)


def test_s5_ac4_ttl_cache_hits_within_ttl() -> None:
    clock = [1000.0]
    cache = registry.TTLCache(clock=lambda: clock[0])
    adapter = _CountingAdapter()
    p = Point(38.5, -78.4)

    first = cache.probe(adapter, p)
    second = cache.probe(adapter, p)  # within TTL → cached, no second underlying call
    assert adapter.calls == 1
    assert first is second


def test_s5_ac5_ttl_cache_expires_after_source_ttl() -> None:
    clock = [1000.0]
    cache = registry.TTLCache(clock=lambda: clock[0])
    adapter = _CountingAdapter()  # ttl_seconds = 600
    p = Point(38.5, -78.4)

    cache.probe(adapter, p)
    clock[0] += 601  # past the source TTL → fresh probe
    cache.probe(adapter, p)
    assert adapter.calls == 2


def test_s5_ac6_cache_is_in_process_no_graph_write() -> None:
    # The cache stores plain tuples in a dict — no graph client, no Cypher (rule #3).
    cache = registry.TTLCache(clock=lambda: 0.0)
    adapter = _CountingAdapter()
    cache.probe(adapter, Point(1.0, 2.0))
    assert all(isinstance(v, tuple) for v in cache._store.values())
