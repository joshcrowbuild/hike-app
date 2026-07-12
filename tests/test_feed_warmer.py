"""Epic 039 B5 — default-frame feed warmer tests (hermetic: injected fakes for the
runtime builder and the plan pipeline, no network, no neo4j marker).

The warmer's contract under test: it derives each region's default frame from the
same config the picker serves, skips a frame the cache already holds fresh (spending
nothing), isolates per-frame failures so a broken frame never starves the round or
kills the loop, keeps its cadence, and stamps every computing run's metrics
`warmed=True` so the spend stays measured.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import pytest

from api.feed_warmer import (
    DEFAULT_FRAME_K,
    DEFAULT_FRAME_QUERY,
    FeedWarmer,
    WarmFrame,
    default_frames,
)
from orchestration.config import Settings
from orchestration.engine import Feed, _anon_key
from orchestration.feed_cache import CachedPlan, FeedCache

FRAME = WarmFrame(
    region_id="shenandoah-gwj",
    origin_key="frontRoyal",
    query=DEFAULT_FRAME_QUERY,
    lat=38.918,
    lon=-78.194,
    k=DEFAULT_FRAME_K,
)
OTHER_FRAME = WarmFrame(
    region_id="richmond",
    origin_key="richmond",
    query=DEFAULT_FRAME_QUERY,
    lat=37.5407,
    lon=-77.436,
    k=DEFAULT_FRAME_K,
)


@dataclass
class _FakeRuntime:
    """Just the Runtime attributes `_warm_frame` touches."""

    feed_cache: FeedCache | None
    cache: Any = None
    feed_cache_hit: bool = False


@dataclass
class _PlanSpy:
    """Records each plan invocation; optionally raises for chosen frames."""

    fail_lats: frozenset[float] = frozenset()
    calls: list[tuple[str, tuple[float, float], int]] = field(default_factory=list)

    def __call__(
        self, query: str, origin: tuple[float, float], runtime: Any, *, k: int, viewer_id: str
    ) -> Feed:
        assert viewer_id == "anonymous"  # the warmer only ever warms the anonymous path
        self.calls.append((query, origin, k))
        if origin[0] in self.fail_lats:
            raise ConnectionError("probe stack down")
        return Feed(query=query, cards=[])


def _warmer(
    plan: _PlanSpy,
    feed_cache: FeedCache | None,
    *,
    frames: list[WarmFrame] | None = None,
    interval_s: float = 0.01,
    ready: threading.Event | None = None,
) -> FeedWarmer:
    if ready is None:
        ready = threading.Event()
        ready.set()
    return FeedWarmer(
        Settings.from_env({}),  # defaults: feed_cache_ttl_s=300 (enabled)
        graph_client=None,  # only handed to the injected runtime builder below
        ready=ready,
        interval_s=interval_s,
        frames=lambda: list(frames if frames is not None else [FRAME]),
        build_runtime_fn=lambda settings, graph, viewer: _FakeRuntime(feed_cache=feed_cache),
        plan_fn=plan,
    )


def _wait_until(predicate: Any, timeout_s: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    pytest.fail("condition not reached within timeout")


# ── default frames derive from the picker's region config ──


def test_default_frames_come_from_region_config() -> None:
    frames = {f.region_id: f for f in default_frames()}
    # Every region file with origins yields exactly one frame, at its FIRST origin.
    shen = frames["shenandoah-gwj"]
    assert shen.origin_key == "frontRoyal"  # the frontend defaultState origin
    assert (shen.lat, shen.lon) == (38.918, -78.194)
    for frame in frames.values():
        assert frame.query == DEFAULT_FRAME_QUERY
        assert frame.k == DEFAULT_FRAME_K


# ── skip-if-warm: a fresh entry spends nothing ──


def test_skips_frame_the_cache_already_holds_fresh() -> None:
    fc = FeedCache(ttl_s=100.0, clock=lambda: 0.0)
    fc.put(
        _anon_key(FRAME.query, (FRAME.lat, FRAME.lon), FRAME.k),
        CachedPlan(planned=(), notices=(), set_aside=()),
    )
    plan = _PlanSpy()
    hits_before, misses_before = fc.stats.hits, fc.stats.misses

    assert _warmer(plan, fc).run_round() == 0

    assert plan.calls == []  # nothing computed, nothing spent
    # The warm-check is a peek, never a stats-counted read (AC: telemetry honesty).
    assert (fc.stats.hits, fc.stats.misses) == (hits_before, misses_before)


def test_expired_entry_is_rewarmed() -> None:
    clock = [0.0]
    fc = FeedCache(ttl_s=10.0, clock=lambda: clock[0])
    fc.put(
        _anon_key(FRAME.query, (FRAME.lat, FRAME.lon), FRAME.k),
        CachedPlan(planned=(), notices=(), set_aside=()),
    )
    clock[0] = 11.0  # past TTL → the frame is cold again
    plan = _PlanSpy()

    assert _warmer(plan, fc).run_round() == 1
    assert plan.calls == [(FRAME.query, (FRAME.lat, FRAME.lon), FRAME.k)]


# ── failure isolation: a broken frame never starves the round or kills the loop ──


def test_one_frames_failure_does_not_starve_the_rest_of_the_round() -> None:
    fc = FeedCache(ttl_s=100.0, clock=lambda: 0.0)
    plan = _PlanSpy(fail_lats=frozenset({FRAME.lat}))

    warmed = _warmer(plan, fc, frames=[FRAME, OTHER_FRAME]).run_round()  # must not raise

    assert warmed == 1  # the healthy frame still warmed
    assert [c[1] for c in plan.calls] == [
        (FRAME.lat, FRAME.lon),
        (OTHER_FRAME.lat, OTHER_FRAME.lon),
    ]


def test_loop_survives_rounds_that_always_fail() -> None:
    fc = FeedCache(ttl_s=100.0, clock=lambda: 0.0)
    plan = _PlanSpy(fail_lats=frozenset({FRAME.lat}))  # every round fails
    warmer = _warmer(plan, fc, interval_s=0.01)
    warmer.start()
    try:
        _wait_until(lambda: len(plan.calls) >= 3)  # kept retrying on cadence
    finally:
        warmer.stop()


# ── cadence ──


def test_cadence_runs_startup_round_then_repeats_on_interval() -> None:
    plan = _PlanSpy()
    # No feed-cache entry ever lands (the fake plan_fn doesn't put), so every
    # cadence tick recomputes — each call is one tick.
    warmer = _warmer(plan, FeedCache(ttl_s=100.0, clock=lambda: 0.0), interval_s=0.01)
    warmer.start()
    try:
        _wait_until(lambda: len(plan.calls) >= 3)
    finally:
        warmer.stop()


def test_waits_for_the_readiness_gate_before_the_first_round() -> None:
    ready = threading.Event()  # NOT set: /plan's dependency stack still warming
    plan = _PlanSpy()
    warmer = _warmer(plan, FeedCache(ttl_s=100.0, clock=lambda: 0.0), ready=ready)
    warmer.start()
    try:
        time.sleep(0.05)
        assert plan.calls == []  # parked — never hammers a cold stack
        ready.set()
        _wait_until(lambda: len(plan.calls) >= 1)
    finally:
        warmer.stop()


# ── kill switches ──


def test_interval_zero_disables_the_warmer() -> None:
    warmer = _warmer(_PlanSpy(), FeedCache(ttl_s=100.0, clock=lambda: 0.0), interval_s=0.0)
    warmer.start()
    assert warmer._thread is None  # no thread ever spawned


def test_disabled_feed_cache_disables_the_warmer() -> None:
    plan = _PlanSpy()
    warmer = FeedWarmer(
        Settings.from_env({"ADVENTURE_ANON_FEED_CACHE_TTL_S": "0"}),
        graph_client=None,
        ready=threading.Event(),
        interval_s=240.0,
        plan_fn=plan,
    )
    warmer.start()
    assert warmer._thread is None


def test_runtime_without_feed_cache_skips_without_computing() -> None:
    # The cache can be kill-switched between rounds (fresh Settings per build_runtime
    # in prod); a None feed_cache must be a quiet no-op, never a crash or a spend.
    plan = _PlanSpy()
    assert _warmer(plan, feed_cache=None).run_round() == 0
    assert plan.calls == []


# ── metrics honesty: warm runs are visible, stamped warmed=True ──


def test_warm_run_emits_plan_metrics_stamped_warmed(caplog: pytest.LogCaptureFixture) -> None:
    fc = FeedCache(ttl_s=100.0, clock=lambda: 0.0)
    plan = _PlanSpy()
    with caplog.at_level(logging.INFO, logger="api.observability"):
        assert _warmer(plan, fc).run_round() == 1
    lines = [r.getMessage() for r in caplog.records if r.name == "api.observability"]
    assert len(lines) == 1
    assert "warmed=True" in lines[0]
    assert "viewer=anon" in lines[0]


def test_skip_emits_no_metrics(caplog: pytest.LogCaptureFixture) -> None:
    fc = FeedCache(ttl_s=100.0, clock=lambda: 0.0)
    fc.put(
        _anon_key(FRAME.query, (FRAME.lat, FRAME.lon), FRAME.k),
        CachedPlan(planned=(), notices=(), set_aside=()),
    )
    with caplog.at_level(logging.INFO, logger="api.observability"):
        _warmer(_PlanSpy(), fc).run_round()
    assert not [r for r in caplog.records if r.name == "api.observability"]
