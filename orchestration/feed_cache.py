"""Anonymous ranked-plan cache at the engine layer (Epic 039 S2).

Caches the *ranked, verified* plan (`CachedPlan`) below presentation, never the
rendered `Feed`/`FeedResponse`. This is the whole point: `present.py`'s `_age()`
bakes a relative freshness string ("just now" / "12m ago") into `FeedLine.text` at
render time, and the wire response carries that baked string verbatim with no
absolute timestamp of its own (only `CardWarningResponse.observed_at` has one). A
cache of the rendered response would re-serve a t0 line as "just now" up to a TTL
later — strictly worse than the per-source live-probe `TTLCache` it sits above
(`orchestration/adapters/registry.py`), which already re-renders age on every run.
Caching `CachedPlan` and re-running `feed_card()` per serve (`engine._render_feed`)
keeps the displayed age honest at any TTL (Rule #1).

In-process only, size-capped, TTL'd — a live reading is never a graph node (Rule #3).
Models directly on `adapters.registry.TTLCache`: a `threading.Lock` guards the store
and stats, expired entries are evicted on read, and the store is FIFO-capped so a
long-running server can't grow it without bound.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orchestration.engine import PlannedTrail, SetAsideTrail

# (query, rounded lat, rounded lon, k) — see `engine._anon_key` for the rounding
# rationale (matches the probe TTLCache's own point resolution).
FeedCacheKey = tuple[str, float, float, int]

# Whole ranked plans are heavier than single live facts → a smaller cap than the
# probe TTLCache's MAX_CACHE_ENTRIES (4096); FIFO-evicted, same discipline.
DEFAULT_MAX_ENTRIES = 512


@dataclass(frozen=True)
class CachedPlan:
    """The viewer-independent, ranked output of `engine._compute_plan` — safe to
    share across anonymous visitors by construction (no viewer field exists on
    `PlannedTrail`/`SetAsideTrail`, and the anonymous path's `combined_profile`
    reduces to query-derived text only). Each fact carries its own absolute
    `fetched_at`; nothing here is pre-rendered into display copy."""

    planned: tuple["PlannedTrail", ...]
    notices: tuple[str, ...]
    set_aside: tuple["SetAsideTrail", ...]


@dataclass
class FeedCacheStats:
    """Cumulative hit/miss counters (mirrors `adapters.registry.ProbeStats`)."""

    hits: int = 0
    misses: int = 0

    def snapshot(self) -> "FeedCacheStats":
        """A detached copy so a before/after delta isn't mutated mid-flight."""
        return FeedCacheStats(hits=self.hits, misses=self.misses)


@dataclass
class _Gate:
    """Per-key single-flight gate: one lock, plus a waiter count so the gate is
    deleted only once nobody still holds a reference to it."""

    lock: threading.Lock = field(default_factory=threading.Lock)
    waiters: int = 0


class FeedCache:
    """TTL + FIFO-capped cache of `CachedPlan`, keyed by `FeedCacheKey`.

    FastAPI's sync routes run in a threadpool, so concurrent `/plan` requests can
    read/write this one process-wide instance at once; `_lock` guards every read/
    write of `_store`/`_gates`/`stats`. `get_or_compute`'s single-flight path runs
    the caller-supplied `compute` OUTSIDE `_lock` — it's the slow part (an intent
    parse + a full Scout/Verifier/Curator pass) — so distinct keys never serialize
    behind one slow compute, exactly the discipline `TTLCache.probe` uses for the
    underlying adapter call.
    """

    def __init__(
        self,
        *,
        ttl_s: float,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl_s = ttl_s
        # An operator misconfig (0/negative via env) degrades to a 1-entry cache
        # rather than crashing every anonymous /plan: put()'s FIFO evict pops from
        # an EMPTY store when the cap is 0 (StopIteration → 500). TTL=0 is the
        # documented kill switch; the size knob never is.
        self._max_entries = max(1, max_entries)
        self._clock = clock
        self._lock = threading.Lock()
        self._store: dict[FeedCacheKey, tuple[CachedPlan, float]] = {}
        self._gates: dict[FeedCacheKey, _Gate] = {}
        self.stats = FeedCacheStats()

    def get(self, key: FeedCacheKey) -> CachedPlan | None:
        with self._lock:
            hit = self._store.get(key)
            if hit is None:
                self.stats.misses += 1
                return None
            plan, expires_at = hit
            if expires_at <= self._clock():
                self._store.pop(key, None)  # evict on expired read
                self.stats.misses += 1
                return None
            self.stats.hits += 1
            return plan

    def peek(self, key: FeedCacheKey) -> bool:
        """True when `key` holds an unexpired entry — WITHOUT touching the hit/miss
        stats or evicting. The feed warmer's skip-if-warm probe (Epic 039 B5): a
        background cadence check must not inflate the hit rate real viewers'
        requests report, and a non-serving path shouldn't do the store's eviction
        work either — expiry stays `get`'s business."""
        with self._lock:
            hit = self._store.get(key)
            return hit is not None and self._clock() < hit[1]

    def put(self, key: FeedCacheKey, plan: CachedPlan) -> None:
        with self._lock:
            if key not in self._store and len(self._store) >= self._max_entries:
                self._store.pop(next(iter(self._store)), None)  # FIFO evict oldest
            self._store[key] = (plan, self._clock() + self._ttl_s)

    def get_or_compute(self, key: FeedCacheKey, compute: Callable[[], CachedPlan]) -> CachedPlan:
        """Single-flight miss path (grafted from Proposal 0). A fast-path `get()`
        handles the common hit; on a miss, get-or-create a per-key gate under the
        main lock, then re-check `get()` under the gate lock — another thread may
        have filled it while this one waited (a "hit-after-wait"). Only then does
        this thread run `compute()` and `put()` the result. Every path — hit,
        hit-after-wait, compute success, compute exception — releases the gate in
        `finally`, or a leaked gate wedges every later caller for this key."""
        cached = self.get(key)
        if cached is not None:
            return cached
        with self._lock:
            gate = self._gates.get(key)
            if gate is None:
                gate = _Gate()
                self._gates[key] = gate
            gate.waiters += 1
        try:
            with gate.lock:
                cached = self.get(key)  # another thread may have filled it while we waited
                if cached is not None:
                    return cached
                plan = compute()  # the slow part — runs outside `self._lock`
                self.put(key, plan)
                return plan
        finally:
            with self._lock:
                gate.waiters -= 1
                if gate.waiters == 0 and self._gates.get(key) is gate:
                    del self._gates[key]


_singleton: FeedCache | None = None
_singleton_lock = threading.Lock()


def default_feed_cache(ttl_s: float, max_entries: int) -> FeedCache:
    """The process-wide anonymous-plan cache — a per-request instance would never
    hit, exactly like `adapters.registry.default_cache()`. Built once from the
    first caller's Settings-derived `ttl_s`/`max_entries` (Render runs one process
    off one resolved Settings, so every `build_runtime` call agrees)."""
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = FeedCache(ttl_s=ttl_s, max_entries=max_entries)
        return _singleton
