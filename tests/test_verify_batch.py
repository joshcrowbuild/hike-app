"""`verify_batch` — the concurrent live-probe fan-out (latency follow-up to Epic 018
S6: /plan's live-condition fan-out used to probe candidates one at a time, up to
k * len(kinds) serial round-trips end to end).

These tests prove the batched path is a pure latency change, not a behavior change:

- `verify_batch(points, probes, cache=cache)` returns byte-for-byte the same result
  `[verify(p, probes, cache=cache) for p in points]` would (source-or-silence,
  primary->fallback, and cache-hit short-circuiting all preserved).
- A failing/silent probe still degrades to an absent kind, never a fabricated fact,
  under the batched path too.
- Probes actually overlap in wall-clock time (the whole point) and stay bounded by
  `max_workers` regardless of how many candidates/kinds are in flight.
- Points that round to the same TTLCache key are coalesced into one real probe
  before fan-out, so a batch of nearby candidates can't thundering-herd a shared
  coordinate against a rate-limited source (a concurrency hazard the old strictly-
  sequential loop didn't have, since the cache was already warm by the time a later
  candidate at the same point ran).

No network: adapters are call-counting fakes with a controllable artificial delay.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from orchestration.adapters.base import (
    AdapterHealth,
    ConditionKind,
    LiveAdapter,
    LiveCapabilities,
    Point,
    VerifiedFact,
)
from orchestration.adapters.registry import TTLCache
from orchestration.verifier import verify, verify_batch

_NOW = datetime(2026, 7, 1, tzinfo=timezone.utc)


class _ConcurrencyCounter:
    """Tracks the max number of overlapping `enter`/`exit` pairs — the only reliable
    way to prove probes actually ran concurrently rather than one at a time."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = 0
        self.peak = 0

    def enter(self) -> None:
        with self._lock:
            self._active += 1
            self.peak = max(self.peak, self._active)

    def exit(self) -> None:
        with self._lock:
            self._active -= 1


class _SlowAdapter(LiveAdapter):
    """A live adapter that sleeps `delay_s` per probe (simulating a real network
    round-trip) and can be told to fail (source-or-silence) or report unhealthy."""

    def __init__(
        self,
        name: str,
        kind: ConditionKind,
        *,
        delay_s: float = 0.0,
        fail: bool = False,
        health: AdapterHealth = AdapterHealth.OK,
        counter: _ConcurrencyCounter | None = None,
    ) -> None:
        self.name = name
        self.kind = kind
        self._delay_s = delay_s
        self._fail = fail
        self._health = health
        self._counter = counter
        self.probe_calls = 0

    def capabilities(self) -> LiveCapabilities:
        return LiveCapabilities(True, False, True)

    def probe(self, point: Point, when: datetime | None = None) -> VerifiedFact | None:
        self.probe_calls += 1
        if self._counter is not None:
            self._counter.enter()
        try:
            if self._delay_s:
                time.sleep(self._delay_s)
            if self._fail:
                return None
            return VerifiedFact(
                value={"src": self.name, "lat": point.lat, "lon": point.lon},
                source=self.name,
                fetched_at=_NOW,
            )
        finally:
            if self._counter is not None:
                self._counter.exit()

    def health(self) -> AdapterHealth:
        return self._health

    @classmethod
    def from_config(cls, settings: object) -> "LiveAdapter | None":  # pragma: no cover
        return None


# ── Equivalence: verify_batch == [verify(p, ...) for p in points] ──


def test_verify_batch_matches_sequential_verify_per_point() -> None:
    points = [Point(38.0 + i * 0.2, -78.0 - i * 0.2) for i in range(6)]
    probes: dict[ConditionKind, list[LiveAdapter]] = {
        ConditionKind.weather: [_SlowAdapter("w", ConditionKind.weather)],
        ConditionKind.air: [_SlowAdapter("a", ConditionKind.air)],
        ConditionKind.water: [_SlowAdapter("wa", ConditionKind.water, fail=True)],
        ConditionKind.fire: [_SlowAdapter("f", ConditionKind.fire)],
    }
    expected = [verify(p, probes) for p in points]
    got = verify_batch(points, probes)
    assert got == expected
    assert all(ConditionKind.water not in r for r in got)  # the failing kind: absent, not empty


def test_verify_batch_matches_sequential_verify_with_shared_cache() -> None:
    """Same equivalence, but through the shared TTLCache (mirrors the real /plan
    wiring) — proves cache-hit short-circuiting also survives the batched path."""
    points = [Point(38.5, -78.4), Point(38.5, -78.4), Point(39.0, -79.0)]
    probes: dict[ConditionKind, list[LiveAdapter]] = {
        ConditionKind.weather: [_SlowAdapter("w", ConditionKind.weather)],
    }
    seq_cache = TTLCache()
    expected = [verify(p, probes, cache=seq_cache) for p in points]

    batch_cache = TTLCache()
    got = verify_batch(points, probes, cache=batch_cache)
    assert got == expected


def test_verify_batch_preserves_primary_fallback_per_task() -> None:
    down = _SlowAdapter("down", ConditionKind.weather, health=AdapterHealth.DOWN)
    up = _SlowAdapter("up", ConditionKind.weather)
    points = [Point(38.5, -78.4), Point(1.0, 2.0), Point(-5.0, 100.0)]
    results = verify_batch(points, {ConditionKind.weather: [down, up]})
    assert down.probe_calls == 0  # down primary never probed, same as verify()
    assert all(r[ConditionKind.weather].source == "up" for r in results)


def test_verify_batch_skips_drive_time() -> None:
    dt = _SlowAdapter("valhalla", ConditionKind.drive_time)
    results = verify_batch([Point(0.0, 0.0)], {ConditionKind.drive_time: [dt]})
    assert results == [{}]
    assert dt.probe_calls == 0


def test_verify_batch_empty_points_and_empty_probes() -> None:
    assert (
        verify_batch([], {ConditionKind.weather: [_SlowAdapter("w", ConditionKind.weather)]}) == []
    )
    assert verify_batch([Point(0.0, 0.0), Point(1.0, 1.0)], {}) == [{}, {}]


# ── Source-or-silence: a failing probe still degrades cleanly under the batch path ──


def test_verify_batch_failed_probe_degrades_to_absent_never_fabricated() -> None:
    points = [Point(38.5, -78.4), Point(39.0, -79.0), Point(40.0, -80.0)]
    dead = _SlowAdapter("dead", ConditionKind.weather, fail=True)
    alive = _SlowAdapter("alive", ConditionKind.air)
    results = verify_batch(points, {ConditionKind.weather: [dead], ConditionKind.air: [alive]})

    assert all(ConditionKind.weather not in r for r in results)  # rule #1: never fabricated
    assert all(ConditionKind.air in r for r in results)  # the healthy kind still resolves
    assert dead.probe_calls == len(points)  # attempted for every point, not silently skipped


def test_verify_batch_all_adapters_silent_leaves_kind_absent() -> None:
    points = [Point(38.5, -78.4)]
    probes = {
        ConditionKind.weather: [
            _SlowAdapter("w1", ConditionKind.weather, fail=True),
            _SlowAdapter("w2", ConditionKind.weather, fail=True),
        ]
    }
    assert verify_batch(points, probes) == [{}]


# ── The point of the change: probes overlap in wall-clock time, bounded by a cap ──


def test_verify_batch_runs_probes_concurrently_not_serially() -> None:
    counter = _ConcurrencyCounter()
    delay = 0.05
    points = [Point(38.0 + i * 1.0, -78.0 - i * 1.0) for i in range(6)]  # distinct, no dedup
    probes: dict[ConditionKind, list[LiveAdapter]] = {
        ConditionKind.weather: [
            _SlowAdapter("w", ConditionKind.weather, delay_s=delay, counter=counter)
        ],
        ConditionKind.air: [_SlowAdapter("a", ConditionKind.air, delay_s=delay, counter=counter)],
    }
    started = time.monotonic()
    verify_batch(points, probes, max_workers=8)
    elapsed = time.monotonic() - started

    assert counter.peak > 1  # more than one probe was in flight at once
    # 6 points * 2 kinds = 12 serial probes would take ~12 * delay; the concurrent
    # fan-out must finish in a handful of delay-widths, not all twelve.
    assert elapsed < delay * 6


def test_verify_batch_respects_max_workers_cap() -> None:
    counter = _ConcurrencyCounter()
    delay = 0.05
    points = [Point(38.0 + i * 1.0, -78.0 - i * 1.0) for i in range(10)]
    probes: dict[ConditionKind, list[LiveAdapter]] = {
        ConditionKind.weather: [
            _SlowAdapter("w", ConditionKind.weather, delay_s=delay, counter=counter)
        ]
    }
    verify_batch(points, probes, max_workers=3)
    assert counter.peak <= 3


# ── Dedup: points that round to the same cache key share one real probe ──


def test_verify_batch_dedupes_points_sharing_a_cache_key() -> None:
    cache = TTLCache()
    adapter = _SlowAdapter("w", ConditionKind.weather, delay_s=0.01)
    # All eight round to the same (lat, lon) at TTLCache's 3-decimal precision.
    points = [Point(38.50001 + i * 0.0000001, -78.40001) for i in range(8)]
    probes: dict[ConditionKind, list[LiveAdapter]] = {ConditionKind.weather: [adapter]}

    results = verify_batch(points, probes, cache=cache, max_workers=8)

    assert adapter.probe_calls == 1  # one real third-party call for the whole shared point
    assert cache.stats.misses == 1
    assert cache.stats.hits == 0  # coalesced before fan-out — the cache never saw a repeat
    assert all(ConditionKind.weather in r for r in results)
    first = results[0][ConditionKind.weather]
    assert all(r[ConditionKind.weather] == first for r in results)  # identical fact, shared


def test_verify_batch_distinct_points_each_get_their_own_probe() -> None:
    cache = TTLCache()
    adapter = _SlowAdapter("w", ConditionKind.weather, delay_s=0.0)
    points = [Point(38.5, -78.4), Point(39.5, -79.4), Point(40.5, -80.4)]
    verify_batch(points, {ConditionKind.weather: [adapter]}, cache=cache)
    assert adapter.probe_calls == 3
    assert cache.stats.misses == 3
