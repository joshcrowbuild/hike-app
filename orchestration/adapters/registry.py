"""Live-adapter registry — config-driven, kind-keyed, primary→fallback (Epic 013).

The single place that knows which live sources exist. Mirrors
`orchestration/providers/registry.py` (resolve-by-name, loud on unknown) and
`ingestion/watch/registry.py` (config list, silent self-drop on absent credential).
`probes_for` groups adapters by `ConditionKind`, ordered by their position in
`ADVENTURE_LIVE_ADAPTERS` (position sets primary vs. fallback within a kind), and
gates each by `LiveCapabilities.supports_region`. The Verifier resolves probes from
this — no literal adapter imports, no `partial`, no `if settings.<x>_key` ladder.

A per-source TTL cache (M3) wraps `probe()` so a repeat within the source's TTL skips
the underlying call (the §29 cost lever). The cache is in-process only — a live
reading is never persisted as a graph node (rule #3).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime

from orchestration.adapters.airnow import AirNowAdapter
from orchestration.adapters.base import (
    ConditionKind,
    LiveAdapter,
    LiveCapabilities,
    Point,
    VerifiedFact,
)
from orchestration.adapters.echo import EchoAdapter
from orchestration.adapters.firms import FirmsAdapter
from orchestration.adapters.nws import NwsAdapter
from orchestration.adapters.ridb import RidbAdapter
from orchestration.adapters.usgs_water import UsgsWaterAdapter
from orchestration.adapters.valhalla import ValhallaAdapter
from orchestration.config import Settings

# name -> adapter class. Adding a live source = one entry here + the adapter file +
# one config-list entry. Each class's `from_config` pulls its own credential.
ADAPTER_FACTORIES: dict[str, type[LiveAdapter]] = {
    "nws": NwsAdapter,
    "airnow": AirNowAdapter,
    "firms": FirmsAdapter,
    "usgs_water": UsgsWaterAdapter,
    "ridb": RidbAdapter,
    "valhalla": ValhallaAdapter,
    "echo": EchoAdapter,  # proof-of-swap stand-in (Epic 013 S6)
}


def enabled_adapters(settings: Settings) -> list[LiveAdapter]:
    """Instantiate the adapters named in ADVENTURE_LIVE_ADAPTERS, dropping any whose
    `from_config` returns None (credential absent). Unknown name → ValueError (fail
    loudly at the boundary, mirroring providers/registry + watch/registry)."""
    out: list[LiveAdapter] = []
    for name in settings.live_adapters:
        factory = ADAPTER_FACTORIES.get(name)
        if factory is None:
            known = ", ".join(sorted(ADAPTER_FACTORIES)) or "(none)"
            raise ValueError(
                f"Unknown live adapter {name!r} in ADVENTURE_LIVE_ADAPTERS. Known: {known}"
            )
        adapter = factory.from_config(settings)
        if adapter is not None:  # silent self-drop on absent credential (SS-10)
            out.append(adapter)
    return out


def _supports_region(caps: LiveCapabilities, region: str) -> bool:
    """A source is selected for a region only if it has authority there. An empty (or
    '*') supports_region means region-agnostic — e.g. drive_time (Epic 013 AC-4.1)."""
    regions = caps.supports_region
    return not regions or "*" in regions or region in regions


def probes_for(region: str, settings: Settings) -> dict[ConditionKind, list[LiveAdapter]]:
    """Adapters grouped by `kind`, ordered by their position in ADVENTURE_LIVE_ADAPTERS
    (primary→fallback within a kind), and gated by `supports_region`. Replaces
    `verifier.build_probes`'s hand-written dict entirely (Epic 013 AC-2.3 / AC-4.1)."""
    grouped: dict[ConditionKind, list[LiveAdapter]] = {}
    for adapter in enabled_adapters(settings):
        if not _supports_region(adapter.capabilities(), region):
            continue  # silent, lossless region exclusion (rule #6 — AC-4.3)
        grouped.setdefault(adapter.kind, []).append(adapter)
    return grouped


# Hard cap on the process-wide cache so the long-running server can't grow it without
# bound; oldest-inserted entries are evicted first once the cap is hit (FIFO).
MAX_CACHE_ENTRIES = 4096


class TTLCache:
    """Per-source TTL cache (M3) wrapping `probe()`, keyed by (name, rounded point,
    when). A repeat within the adapter's `ttl_seconds` returns the cached fact without
    a second underlying call. In-process only — never a graph node (rule #3). Expired
    entries are evicted on read and the store is size-capped, so the shared singleton
    cannot grow unbounded in a long-running server."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._store: dict[tuple, tuple[VerifiedFact, float]] = {}
        self._clock = clock

    @staticmethod
    def _key(adapter: LiveAdapter, point: Point, when: datetime | None) -> tuple:
        return (adapter.name, round(point.lat, 3), round(point.lon, 3), when)

    def peek(
        self, adapter: LiveAdapter, point: Point, when: datetime | None = None
    ) -> VerifiedFact | None:
        """Return a still-fresh cached fact without probing — lets the Verifier skip a
        liveness `health()` call on a cache hit. None if absent or expired (an expired
        entry is evicted on read)."""
        key = self._key(adapter, point, when)
        hit = self._store.get(key)
        if hit is None:
            return None
        if hit[1] <= self._clock():
            self._store.pop(key, None)  # evict on expired read
            return None
        return hit[0]

    def probe(
        self, adapter: LiveAdapter, point: Point, when: datetime | None = None
    ) -> VerifiedFact | None:
        key = self._key(adapter, point, when)
        now = self._clock()
        hit = self._store.get(key)
        if hit is not None:
            if hit[1] > now:
                return hit[0]
            self._store.pop(key, None)  # expired → drop before re-probing
        fact = adapter.probe(point, when)
        if fact is not None:
            if len(self._store) >= MAX_CACHE_ENTRIES:
                self._store.pop(next(iter(self._store)), None)  # FIFO evict oldest
            self._store[key] = (fact, now + adapter.ttl_seconds)
        return fact


_DEFAULT_CACHE = TTLCache()


def default_cache() -> TTLCache:
    """The process-wide live-probe cache (persists across requests so the per-source
    TTL is a real cost lever, not a per-request no-op)."""
    return _DEFAULT_CACHE
