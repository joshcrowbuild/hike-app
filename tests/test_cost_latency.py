"""Epic 018 S6 — cost, caching & latency on the live fan-out.

The fan-out probes up to five live sources per candidate, each with real per-call cost
and latency. These lock the three S6 acceptance criteria:

- AC-6.1 — the TTL cache instruments the true underlying-call count and per-kind
  wall-clock, and the API observability layer reports them as per-request deltas.
- AC-6.2 — per-source TTLs are tuned to real volatility (CDP-08) and provably cut
  repeat calls within a feed.
- AC-6.3 — a slow / rate-limited source degrades-and-discloses (source-or-silence)
  rather than failing the whole card, and the expensive `/plan` path stays rate-bounded.

No network: adapters are call-counting fakes driven through the real cache + verifier.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

from api.observability import PlanMetrics
from api.ratelimit import DEFAULT_PLAN_LIMIT, plan_limit
from orchestration.adapters import registry
from orchestration.adapters.airnow import AirNowAdapter
from orchestration.adapters.base import (
    AdapterHealth,
    ConditionKind,
    LiveAdapter,
    LiveCapabilities,
    Point,
    VerifiedFact,
)
from orchestration.adapters.firms import FirmsAdapter
from orchestration.adapters.nws import NwsAdapter
from orchestration.adapters.ridb import RidbAdapter
from orchestration.adapters.usgs_water import UsgsWaterAdapter
from orchestration.verifier import verify

_NOW = datetime(2026, 7, 1, tzinfo=timezone.utc)


class _CountingAdapter(LiveAdapter):
    """A weather source that counts real probes and can be told to fail (return None)."""

    kind = ConditionKind.weather
    ttl_seconds = 600

    def __init__(
        self, name: str = "counting", *, fact: bool = True, health: AdapterHealth = AdapterHealth.OK
    ) -> None:
        self.name = name
        self.calls = 0
        self._fact = fact
        self._health = health

    def capabilities(self) -> LiveCapabilities:
        return LiveCapabilities(True, False, True)

    def probe(self, point: Point, when: datetime | None = None) -> VerifiedFact | None:
        self.calls += 1
        if not self._fact:
            return None  # source-or-silence: a failed/slow source contributes nothing
        return VerifiedFact(value={"n": self.calls}, source=self.name, fetched_at=_NOW)

    def health(self) -> AdapterHealth:
        return self._health

    @classmethod
    def from_config(cls, settings: object) -> "LiveAdapter | None":  # pragma: no cover
        return cls()


class _CountingWater(_CountingAdapter):
    kind = ConditionKind.water


# ── AC-6.2 — TTLs tuned to real volatility (CDP-08) ──


def test_ac62_ttls_ordered_by_true_volatility() -> None:
    """Windows reflect CDP-08: weather in hours, streamflow shorter (min-hours), permits
    in days. Locking the ordering reds the build if a window drifts off its volatility."""
    assert NwsAdapter.ttl_seconds >= 3600  # weather: hours
    assert AirNowAdapter.ttl_seconds >= 3600  # air (AQI): hourly
    assert FirmsAdapter.ttl_seconds >= 3600  # fire: satellite-pass hours
    # Streamflow is the most volatile source → strictly shorter than the weather window.
    assert UsgsWaterAdapter.ttl_seconds < NwsAdapter.ttl_seconds
    # Permits (facility/requirement data) are near-static → a full day.
    assert RidbAdapter.ttl_seconds >= 86400


def test_ac62_ttl_cache_cuts_repeat_calls_within_a_feed() -> None:
    """Candidates that resolve to the same rounded point (e.g. a shared trailhead, or the
    fall-back-to-origin path) probe a source once, then serve the rest from cache."""
    clock = [1000.0]
    cache = registry.TTLCache(clock=lambda: clock[0])
    adapter = _CountingAdapter()
    point = Point(38.5, -78.4)
    probes = {ConditionKind.weather: [adapter]}

    for _ in range(5):  # five candidates in one feed at the same locale
        verify(point, probes, cache=cache)

    assert adapter.calls == 1  # one real third-party call for the whole feed
    assert cache.stats.misses == 1
    assert cache.stats.hits == 4  # the other four served from cache


# ── AC-6.1 — instrument live-call count + per-kind wall-clock ──


def test_ac61_stats_count_calls_and_time_per_kind() -> None:
    """The cache records the true underlying-call count and cumulative wall-clock per
    ConditionKind. The clock doubles as the probe timer, so a fake clock makes timing
    deterministic; here each probe 'takes' 0.25 s of monotonic time."""
    ticks = [0.0]

    def clock() -> float:
        ticks[0] += 0.25
        return ticks[0]

    cache = registry.TTLCache(clock=clock)
    weather = _CountingAdapter("nws-fake")
    water = _CountingWater("usgs-fake")

    cache.probe(weather, Point(38.5, -78.4))
    cache.probe(water, Point(39.0, -79.0))

    assert cache.stats.misses == 2
    assert cache.stats.calls_by_kind == {"weather": 1, "water": 1}
    assert cache.stats.wall_ms_by_kind["weather"] > 0
    assert cache.stats.wall_ms_by_kind["water"] > 0


def test_am1_probe_store_and_stats_are_guarded_by_a_lock() -> None:
    """AM1: FastAPI's sync routes run in a threadpool, so concurrent /plan requests can
    hit the process-wide TTLCache at once — `self.stats.misses += 1` and
    `self._store[key] = ...` are read-modify-write races without a lock. A real timing
    race is unreliable to force under the GIL, so this proves mutual exclusion directly:
    while `_lock` is held (simulating another thread mid-critical-section), a concurrent
    `peek()` — which runs the same locked store-read path `probe()` does — must block
    until the lock is released."""
    cache = registry.TTLCache()
    adapter = _CountingAdapter("held")
    cache.probe(adapter, Point(1.0, 2.0))  # populate one fresh entry via the locked path

    started = threading.Event()
    proceeded = threading.Event()

    def _reader() -> None:
        started.set()
        cache.peek(adapter, Point(1.0, 2.0))
        proceeded.set()

    with cache._lock:  # hold the lock as if another thread were mid-update
        t = threading.Thread(target=_reader)
        t.start()
        assert started.wait(timeout=1.0)
        # The reader must NOT be able to acquire the lock while we hold it.
        assert not proceeded.wait(timeout=0.2)

    # Released — the blocked reader now proceeds.
    t.join(timeout=1.0)
    assert proceeded.is_set()


def test_am1_slow_underlying_probe_does_not_serialize_other_requests() -> None:
    """The lock must NOT wrap the network call itself — only the store/stats access —
    or concurrent /plan requests would queue behind one slow live-adapter call instead
    of fanning out in parallel."""
    cache = registry.TTLCache()
    release = threading.Event()
    entered = threading.Event()
    slow = _CountingAdapter("slow")

    def _blocking_probe(point: Point, when: datetime | None = None) -> VerifiedFact | None:
        entered.set()
        release.wait(timeout=2.0)
        return VerifiedFact(value={"n": 1}, source="slow", fetched_at=_NOW)

    slow.probe = _blocking_probe  # type: ignore[method-assign]

    t = threading.Thread(target=lambda: cache.probe(slow, Point(1.0, 2.0)))
    t.start()
    assert entered.wait(timeout=1.0)  # the slow probe is now running, unlocked

    # A second, unrelated probe must complete immediately — not wait on the first.
    fast = _CountingAdapter("fast")
    fact = cache.probe(fast, Point(9.0, 9.0))
    assert fact is not None
    assert fast.calls == 1

    release.set()
    t.join(timeout=2.0)


def test_ac61_snapshot_is_detached() -> None:
    """A snapshot must not move once taken, so a before/after delta is stable mid-flight."""
    cache = registry.TTLCache(clock=lambda: 0.0)
    before = cache.stats.snapshot()
    cache.probe(_CountingAdapter(), Point(1.0, 2.0))
    assert before.misses == 0  # unchanged by the later probe
    assert cache.stats.misses == 1


def test_ac61_plan_metrics_report_deltas_and_emit() -> None:
    """PlanMetrics turns before/after ProbeStats snapshots into this request's true live
    call count, cache-hit count, and per-kind wall-clock — and emits them on one line."""
    before = registry.ProbeStats(hits=2, misses=3, wall_ms_by_kind={"weather": 10.0})
    after = registry.ProbeStats(hits=6, misses=5, wall_ms_by_kind={"weather": 42.0, "water": 8.0})
    m = PlanMetrics(
        viewer_tag="anon",
        latency_ms=123.4,
        card_count=3,
        cache_entries_before=1,
        cache_entries_after=6,
        est_tokens=100,
        probe_stats_before=before,
        probe_stats_after=after,
    )
    assert m.live_calls == 2  # 5 - 3 underlying calls this request
    assert m.cache_hits == 4  # 6 - 2 served from cache
    assert m.wall_ms_by_kind == {"weather": 32.0, "water": 8.0}


def test_ac61_plan_metrics_degrade_without_stats() -> None:
    """Missing snapshots (a stub runtime with no cache) must read as zero, never crash —
    observability can never break the request path."""
    m = PlanMetrics(
        viewer_tag="anon",
        latency_ms=1.0,
        card_count=0,
        cache_entries_before=0,
        cache_entries_after=0,
        est_tokens=0,
    )
    assert m.live_calls == 0
    assert m.cache_hits == 0
    assert m.wall_ms_by_kind == {}


# ── Epic 039 S2 AC-2.9 — a feed-cache hit never fabricates spend ──


def test_s2_ac9_feed_cache_hit_reports_zero_spend_and_the_hit_flag() -> None:
    """A feed-cache hit ran no intent-parse/taste-rank LLM call and no live probe:
    api/app.py must pass est_tokens=0 (never estimated from the still-rendered cached
    card text) and probe_stats_before==probe_stats_after (no probe fired), so
    live_calls/cache_hits/cache_misses/est_cost_usd all read zero alongside
    feed_cache_hit=True."""
    stats = registry.ProbeStats(hits=2, misses=3, wall_ms_by_kind={"weather": 10.0})
    m = PlanMetrics(
        viewer_tag="anon",
        latency_ms=4.2,  # a cache-hit response is fast — not asserted here, just plausible
        card_count=3,
        cache_entries_before=6,  # unchanged before/after: no probe ran on a hit
        cache_entries_after=6,
        est_tokens=0,  # the caller (api/app.py) zeroes this on a hit — never estimated
        probe_stats_before=stats.snapshot(),
        probe_stats_after=stats.snapshot(),
        feed_cache_hit=True,
    )
    assert m.feed_cache_hit is True
    assert m.est_tokens == 0
    assert m.est_cost_usd == 0.0
    assert m.live_calls == 0
    assert m.cache_hits == 0
    assert m.cache_misses == 0


def test_s2_ac9_feed_cache_miss_defaults_hit_flag_false() -> None:
    """A normal (miss) call's PlanMetrics must default feed_cache_hit=False — every
    call site that predates Epic 039 S2 (and any that never sets it) reports a miss,
    never a silently-wrong hit."""
    m = PlanMetrics(
        viewer_tag="anon",
        latency_ms=250.0,
        card_count=3,
        cache_entries_before=0,
        cache_entries_after=5,
        est_tokens=120,
    )
    assert m.feed_cache_hit is False


# ── AC-6.3 — slow/rate-limited source degrades-and-discloses; path stays bounded ──


def test_ac63_failed_source_degrades_without_failing_the_card() -> None:
    """A source that self-drops (a slow/failed probe returns None) leaves its kind absent
    while every other kind still resolves — source-or-silence, never a whole-card failure."""
    dead_weather = _CountingAdapter("nws-down", fact=False)
    good_water = _CountingWater("usgs-ok")
    probes = {
        ConditionKind.weather: [dead_weather],
        ConditionKind.water: [good_water],
    }

    facts = verify(Point(38.5, -78.4), probes)  # must not raise

    assert ConditionKind.weather not in facts  # absent, not fabricated
    assert ConditionKind.water in facts  # the healthy source still lands


def test_ac63_rate_limited_source_falls_over_to_a_fallback() -> None:
    """A rate-limited primary is skipped for the same kind's fallback rather than dragging
    the fan-out down — the degrade path the tuned TTLs are meant to keep off the wire."""
    primary = _CountingAdapter("nws-primary", health=AdapterHealth.RATE_LIMITED)
    fallback = _CountingAdapter("nws-backup")
    probes = {ConditionKind.weather: [primary, fallback]}

    facts = verify(Point(38.5, -78.4), probes)

    assert primary.calls == 0  # rate-limited primary never probed
    assert facts[ConditionKind.weather].source == "nws-backup"


def test_ac63_expensive_plan_path_stays_rate_bounded() -> None:
    """The `/plan` fan-out is the costly path; its per-IP limit must be configured so a
    single client can't drain budget across the fan-out (#53 tie-in)."""
    assert DEFAULT_PLAN_LIMIT  # a bound exists by default
    assert "/" in plan_limit()  # slowapi "<count>/<window>" shape
