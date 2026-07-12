"""Epic 039 S2 — FeedCache unit tests (mirrors tests/test_live_registry.py's shape:
an injected fake clock, no network, no neo4j marker).

`CachedPlan` here carries a bare sentinel payload (a string) rather than a real
`PlannedTrail` tuple — `FeedCache` is generic over its stored value and never
inspects `CachedPlan.planned`/`notices`/`set_aside`, so the sentinel is enough to
prove get/put/TTL/FIFO/single-flight without dragging in the whole engine stack.
"""

from __future__ import annotations

import threading

from orchestration.feed_cache import CachedPlan, FeedCache


def _plan(tag: str) -> CachedPlan:
    return CachedPlan(planned=(tag,), notices=(), set_aside=())


def _tag(plan: CachedPlan) -> str:
    return plan.planned[0]


# ── get/put round trip + stats ──


def test_get_miss_then_put_then_hit_updates_stats() -> None:
    cache = FeedCache(ttl_s=100.0, clock=lambda: 0.0)
    key = ("q", 38.5, -78.4, 10)

    assert cache.get(key) is None
    assert cache.stats.misses == 1
    assert cache.stats.hits == 0

    cache.put(key, _plan("a"))
    hit = cache.get(key)
    assert hit is not None and _tag(hit) == "a"
    assert cache.stats.hits == 1
    assert cache.stats.misses == 1  # unchanged by the hit


def test_distinct_keys_never_collide() -> None:
    cache = FeedCache(ttl_s=100.0, clock=lambda: 0.0)
    cache.put(("q1", 0.0, 0.0, 10), _plan("a"))
    cache.put(("q2", 0.0, 0.0, 10), _plan("b"))
    assert _tag(cache.get(("q1", 0.0, 0.0, 10))) == "a"
    assert _tag(cache.get(("q2", 0.0, 0.0, 10))) == "b"


# ── AC-2.6: TTL expiry evicts on read ──


def test_ttl_expiry_is_a_miss_and_evicts_on_read() -> None:
    clock = [0.0]
    cache = FeedCache(ttl_s=10.0, clock=lambda: clock[0])
    key = ("q", 38.5, -78.4, 10)
    cache.put(key, _plan("a"))

    clock[0] = 5.0
    assert cache.get(key) is not None  # still fresh

    clock[0] = 10.001  # past ttl_s
    assert cache.get(key) is None  # expired → miss
    assert len(cache._store) == 0  # evicted on the expired read, not left to linger


# ── AC-2.6: FIFO size cap ──


def test_fifo_eviction_at_max_entries() -> None:
    cache = FeedCache(ttl_s=100.0, max_entries=2, clock=lambda: 0.0)
    cache.put(("a", 0.0, 0.0, 1), _plan("a"))
    cache.put(("b", 0.0, 0.0, 1), _plan("b"))
    cache.put(("c", 0.0, 0.0, 1), _plan("c"))  # evicts "a" (oldest inserted)

    assert len(cache._store) == 2
    assert cache.get(("a", 0.0, 0.0, 1)) is None
    assert cache.get(("b", 0.0, 0.0, 1)) is not None
    assert cache.get(("c", 0.0, 0.0, 1)) is not None


def test_fifo_cap_never_exceeded_across_many_inserts() -> None:
    cache = FeedCache(ttl_s=100.0, max_entries=3, clock=lambda: 0.0)
    for i in range(20):
        cache.put((f"q{i}", 0.0, 0.0, 1), _plan(f"p{i}"))
        assert len(cache._store) <= 3


def test_put_overwriting_an_existing_key_does_not_evict() -> None:
    cache = FeedCache(ttl_s=100.0, max_entries=1, clock=lambda: 0.0)
    key = ("q", 0.0, 0.0, 1)
    cache.put(key, _plan("a"))
    cache.put(key, _plan("b"))  # same key, cache already at cap → must not evict itself
    assert len(cache._store) == 1
    assert _tag(cache.get(key)) == "b"


# ── AC-2.8: single-flight ──


def test_get_or_compute_hit_never_calls_compute() -> None:
    cache = FeedCache(ttl_s=100.0, clock=lambda: 0.0)
    key = ("q", 0.0, 0.0, 1)
    cache.put(key, _plan("cached"))

    def _boom() -> CachedPlan:
        raise AssertionError("compute must not run on a cache hit")

    assert _tag(cache.get_or_compute(key, _boom)) == "cached"


def test_get_or_compute_miss_runs_compute_once_and_stores() -> None:
    cache = FeedCache(ttl_s=100.0, clock=lambda: 0.0)
    key = ("q", 0.0, 0.0, 1)
    calls = []

    def _compute() -> CachedPlan:
        calls.append(1)
        return _plan("computed")

    out = cache.get_or_compute(key, _compute)
    assert _tag(out) == "computed"
    assert len(calls) == 1
    assert _tag(cache.get(key)) == "computed"


def test_concurrent_identical_miss_collapses_to_one_compute() -> None:
    """AC-2.8: N concurrent identical-key misses invoke `compute` exactly once; every
    thread receives the same CachedPlan."""
    cache = FeedCache(ttl_s=100.0, clock=lambda: 0.0)
    key = ("q", 0.0, 0.0, 1)
    calls: list[int] = []
    call_lock = threading.Lock()
    release = threading.Event()
    entered = threading.Event()

    def _compute() -> CachedPlan:
        with call_lock:
            calls.append(1)
        entered.set()
        release.wait(timeout=2.0)  # hold the gate open so other threads pile up waiting
        return _plan("computed")

    results: list[CachedPlan] = []
    results_lock = threading.Lock()

    def _worker() -> None:
        out = cache.get_or_compute(key, _compute)
        with results_lock:
            results.append(out)

    threads = [threading.Thread(target=_worker) for _ in range(8)]
    for t in threads:
        t.start()
    assert entered.wait(timeout=2.0)
    release.set()
    for t in threads:
        t.join(timeout=2.0)

    assert len(calls) == 1  # compute ran exactly once despite 8 concurrent callers
    assert len(results) == 8
    assert all(_tag(r) == "computed" for r in results)
    assert cache._gates == {}  # every waiter released the gate — none leaked


def test_get_or_compute_raising_stores_nothing_and_releases_gate() -> None:
    """AC-2.5/AC-2.8: a raising `compute` propagates, stores nothing, and the gate is
    released (a later call for the same key must not wedge)."""
    cache = FeedCache(ttl_s=100.0, clock=lambda: 0.0)
    key = ("q", 0.0, 0.0, 1)

    def _raise() -> CachedPlan:
        raise ConnectionError("judge unavailable")

    try:
        cache.get_or_compute(key, _raise)
        raise AssertionError("expected ConnectionError to propagate")
    except ConnectionError:
        pass

    assert cache.get(key) is None  # nothing stored
    assert cache._gates == {}  # gate released in `finally`, not leaked

    # A subsequent call for the same key must not wedge behind the dead gate.
    out = cache.get_or_compute(key, lambda: _plan("recovered"))
    assert _tag(out) == "recovered"


def test_distinct_keys_never_serialize_behind_one_slow_compute() -> None:
    """The single-flight gate is per-key: a slow compute for one key must not block a
    concurrent request for a different key."""
    cache = FeedCache(ttl_s=100.0, clock=lambda: 0.0)
    slow_entered = threading.Event()
    release = threading.Event()

    def _slow() -> CachedPlan:
        slow_entered.set()
        release.wait(timeout=2.0)
        return _plan("slow")

    t = threading.Thread(target=lambda: cache.get_or_compute(("slow", 0.0, 0.0, 1), _slow))
    t.start()
    assert slow_entered.wait(timeout=2.0)

    # A different key's compute must finish immediately, not wait on the slow one.
    fast = cache.get_or_compute(("fast", 0.0, 0.0, 1), lambda: _plan("fast"))
    assert _tag(fast) == "fast"

    release.set()
    t.join(timeout=2.0)


# ── operator-misconfig guard: max_entries <= 0 degrades, never crashes ──


def test_max_entries_zero_or_negative_degrades_to_one_never_crashes() -> None:
    # ADVENTURE_ANON_FEED_CACHE_MAX_ENTRIES=0/-5 must degrade to a 1-entry cache:
    # unguarded, put()'s FIFO evict pops from an EMPTY store (StopIteration) and
    # every anonymous /plan 500s. TTL=0 is the kill switch; the size knob never is.
    for bad_cap in (0, -5):
        cache = FeedCache(ttl_s=100.0, max_entries=bad_cap, clock=lambda: 0.0)
        cache.put(("q", 38.5, -78.4, 10), _plan("a"))
        cache.put(("r", 38.5, -78.4, 10), _plan("b"))  # FIFO-evicts at the clamped cap
        hit = cache.get(("r", 38.5, -78.4, 10))
        assert hit is not None and _tag(hit) == "b"
        assert cache.get(("q", 38.5, -78.4, 10)) is None


# ── Epic 039 B5: peek (the warmer's skip-if-warm probe) ──


def test_peek_never_moves_stats_or_evicts() -> None:
    clock = [0.0]
    cache = FeedCache(ttl_s=10.0, clock=lambda: clock[0])
    key = ("q", 38.5, -78.4, 10)

    assert cache.peek(key) is False  # absent
    cache.put(key, _plan("a"))
    assert cache.peek(key) is True  # fresh

    clock[0] = 10.001
    assert cache.peek(key) is False  # expired reads as cold...
    assert len(cache._store) == 1  # ...but eviction stays get()'s business

    assert cache.stats.hits == 0 and cache.stats.misses == 0  # peeks are uncounted


def test_peek_horizon_reads_soon_to_expire_as_cold() -> None:
    # The warmer's re-prime lookahead (Epic 039 B5 self-review fix): an entry that
    # will expire within `horizon_s` is already cold for the warmer's purposes.
    clock = [0.0]
    cache = FeedCache(ttl_s=10.0, clock=lambda: clock[0])
    key = ("q", 38.5, -78.4, 10)
    cache.put(key, _plan("a"))  # expires at 10.0

    assert cache.peek(key, horizon_s=5.0) is True  # outlives the horizon
    assert cache.peek(key, horizon_s=10.0) is False  # dies within it → cold
    clock[0] = 6.0
    assert cache.peek(key, horizon_s=5.0) is False  # 4s left < 5s horizon
