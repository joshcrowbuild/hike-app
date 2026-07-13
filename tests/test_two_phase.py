"""Epic 040 — two-phase render at the engine layer (S1 + S2).

Hermetic: fake session + spy adapters, no DB, no network, no model provider.
Covers the honesty spine of the split:

  S1  phase 1 issues ZERO live probes; every point kind is honest `not_fetched`
      silence (no source, no timestamp, no warnings, no set-asides); the taste
      rank runs exactly as the full anonymous path (judge failure re-raises);
      a phase-1 plan NEVER enters the anonymous feed cache; a warm key serves
      the full plan as a complete response instead.
  S2  the conditions call composes the parked phase-1 plan with the live
      fan-out through the shared `verify_planned` path: verified facts fold in,
      hard blocks become disclosed set-asides (remove, never reorder), the
      composed plan warms the feed cache, unknown ids are disclosed, and the
      no-holding-pen fallback resolves ids from the graph without warming.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from orchestration.adapters.base import (
    AdapterHealth,
    ConditionKind,
    LiveAdapter,
    LiveCapabilities,
    Point,
    VerifiedFact,
)
from orchestration.engine import Runtime, _anon_key, plan
from orchestration.feed_cache import FeedCache
from orchestration.providers.base import LLMResponse
from orchestration.two_phase import plan_cards, plan_conditions
from orchestration.verifier import DEFAULT_MAX_WORKERS

# ── fakes ─────────────────────────────────────────────────────────────────────


class _FakeSession:
    """Dispatching fake for the scoped session: scout rows for the candidate read,
    detail rows for the two-phase graph fallback, [] for everything personal."""

    def __init__(
        self, rows: list[dict[str, Any]], detail_rows: list[dict[str, Any]] | None = None
    ) -> None:
        self.rows = rows
        self.detail_rows = detail_rows if detail_rows is not None else []

    def run(self, query: tuple[str, dict[str, Any]]) -> list[dict[str, Any]]:
        cypher, _ = query
        if any(k in cypher for k in ("Belief", "PhysicalProfile", "Episode")):
            return []
        if "SAME_AS" in cypher:
            return []
        if "WHERE t.canonical_id IN $cids" in cypher:
            return self.detail_rows
        return self.rows


class _SpyAdapter(LiveAdapter):
    """A point-probe adapter that counts every probe() call (Epic 040 AC-1.1's spy)."""

    def __init__(self, name: str, kind: ConditionKind, value: Any) -> None:
        self.name = name
        self.kind = kind
        self.value = value
        self.calls = 0

    def capabilities(self) -> LiveCapabilities:
        return LiveCapabilities(True, False, True)

    def probe(self, point: Point, when: datetime | None = None) -> VerifiedFact | None:
        self.calls += 1
        value = self.value(point.lat, point.lon) if callable(self.value) else self.value
        if value is None:
            return None
        return VerifiedFact(value=value, source=self.name, fetched_at=datetime.now(timezone.utc))

    def health(self) -> AdapterHealth:
        return AdapterHealth.OK

    @classmethod
    def from_config(cls, settings: Any) -> "LiveAdapter | None":
        return None


class _CountingJudge:
    name = "fake-judge"

    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    def complete(self, request: Any) -> LLMResponse:
        self.calls += 1
        return LLMResponse(text=self.text, model=request.model, provider=self.name)


class _RaisingJudge:
    name = "fake-judge"

    def complete(self, request: Any) -> LLMResponse:
        raise ConnectionError("judge unavailable")


def _row(cid: str, lat: float, lon: float, dist: float) -> dict[str, Any]:
    return {
        "canonical_id": cid,
        "name": cid,
        "trailhead_id": "th",
        "distance_m": dist,
        "point": {"latitude": lat, "longitude": lon},
    }


def _detail_row(cid: str, lat: float, lon: float) -> dict[str, Any]:
    return {
        "canonical_id": cid,
        "name": cid,
        "trail_point": {"latitude": lat, "longitude": lon},
        "trailhead_point": None,
    }


_ORIGIN = (38.5, -78.4)
_ROWS = [_row("a", 38.5, -78.4, 100.0), _row("b", 38.6, -78.5, 200.0)]


def _runtime(
    *,
    weather: _SpyAdapter | None = None,
    air: _SpyAdapter | None = None,
    feed_cache: FeedCache | None = None,
    phase1_pending: FeedCache | None = None,
    judge: Any = None,
    detail_rows: list[dict[str, Any]] | None = None,
) -> Runtime:
    probes: dict[ConditionKind, list[LiveAdapter]] = {}
    if weather is not None:
        probes[ConditionKind.weather] = [weather]
    if air is not None:
        probes[ConditionKind.air] = [air]
    return Runtime(
        session=_FakeSession(_ROWS, detail_rows=detail_rows),  # type: ignore[arg-type]
        probes=probes,
        judge=(judge or _CountingJudge('["a","b"]'), "m"),
        feed_cache=feed_cache,
        phase1_pending=phase1_pending,
    )


# ── S1: phase 1 — graph-only plan ────────────────────────────────────────────


def test_ac11_phase1_issues_zero_live_probes() -> None:
    weather = _SpyAdapter("nws", ConditionKind.weather, {"temp_f": 70})
    runtime = _runtime(weather=weather)

    feed, complete = plan_cards("mellow loop", _ORIGIN, runtime, k=5)

    assert weather.calls == 0  # the spy recorded no probe() for any point kind
    assert complete is False
    assert [c.canonical_id for c in feed.cards] == ["a", "b"]


def test_ac12_phase1_cards_wear_honest_not_fetched_silence() -> None:
    weather = _SpyAdapter("nws", ConditionKind.weather, {"temp_f": 70})
    runtime = _runtime(weather=weather)

    feed, _ = plan_cards("mellow loop", _ORIGIN, runtime, k=5)

    assert feed.set_aside == ()  # nothing verified -> nothing blocked
    for card in feed.cards:
        assert card.lines == []  # no condition lines before verification
        assert card.warnings == ()
        assert card.unavailable == ()
        kinds = [s.kind for s in card.conditions]
        assert kinds == ["weather", "air", "fire", "water", "closures", "permits"]
        for status in card.conditions:
            assert status.state == "not_fetched"
            assert status.source == ""  # no fabricated attribution (rule #1)
            assert status.checked_at is None


def test_ac13_anonymous_judge_failure_still_raises_on_phase1() -> None:
    # The phase-1 rank is the SAME anonymous rank as the full path — a judge
    # failure re-raises rather than silently degrading (Epic 014 semantics held).
    runtime = _runtime(judge=_RaisingJudge())
    with pytest.raises(ConnectionError):
        plan_cards("mellow loop", _ORIGIN, runtime, k=5)


def test_ac14_phase1_never_written_to_feed_cache() -> None:
    fc = FeedCache(ttl_s=300.0, clock=lambda: 0.0)
    pending = FeedCache(ttl_s=180.0, clock=lambda: 0.0)
    judge = _CountingJudge('["a","b"]')
    runtime = _runtime(feed_cache=fc, phase1_pending=pending, judge=judge)

    _, complete = plan_cards("mellow loop", _ORIGIN, runtime, k=5)
    assert complete is False

    # The phase-1 plan parked in the holding pen, NOT the feed cache…
    key = _anon_key("mellow loop", _ORIGIN, 5)
    assert pending.peek(key)
    assert not fc.peek(key)
    # …so a later full /plan on the same key must MISS and compute (hits stay 0).
    plan("mellow loop", _ORIGIN, runtime, k=5)
    assert fc.stats.hits == 0
    assert judge.calls == 2  # phase-1 rank + the full request's own rank


def test_ac14_warm_key_serves_full_plan_as_complete() -> None:
    weather = _SpyAdapter("nws", ConditionKind.weather, {"temp_f": 70})
    fc = FeedCache(ttl_s=300.0, clock=lambda: 0.0)
    judge = _CountingJudge('["a","b"]')
    runtime = _runtime(weather=weather, feed_cache=fc, judge=judge)

    plan("mellow loop", _ORIGIN, runtime, k=5)  # warms the key with the FULL plan
    probes_before = weather.calls
    feed, complete = plan_cards("mellow loop", _ORIGIN, runtime, k=5)

    assert complete is True  # facts already paid for are never withheld (D7)
    assert runtime.feed_cache_hit is True
    assert weather.calls == probes_before  # no recompute, no re-probe
    states = {s.kind: s.state for s in feed.cards[0].conditions}
    assert states["weather"] == "present"  # the verified fact, not a not_fetched mask


def test_phase1_for_non_anonymous_viewer_never_enters_shared_stores() -> None:
    fc = FeedCache(ttl_s=300.0, clock=lambda: 0.0)
    pending = FeedCache(ttl_s=180.0, clock=lambda: 0.0)
    judge = _CountingJudge('["a","b"]')
    runtime = _runtime(feed_cache=fc, phase1_pending=pending, judge=judge)
    runtime.personalized_judge = (judge, "m")

    feed, complete = plan_cards("mellow loop", _ORIGIN, runtime, k=5, viewer_id="mem:josh")

    assert complete is False
    assert len(feed.cards) == 2
    # Rule #5: a personalized plan never lands in either anonymous shared store.
    key = _anon_key("mellow loop", _ORIGIN, 5)
    assert not pending.peek(key)
    assert not fc.peek(key)


# ── S2: the conditions patch ─────────────────────────────────────────────────


def test_conditions_composes_pending_plan_and_warms_the_cache() -> None:
    weather = _SpyAdapter("nws", ConditionKind.weather, {"temp_f": 70})
    fc = FeedCache(ttl_s=300.0, clock=lambda: 0.0)
    pending = FeedCache(ttl_s=180.0, clock=lambda: 0.0)
    judge = _CountingJudge('["a","b"]')
    runtime = _runtime(weather=weather, feed_cache=fc, phase1_pending=pending, judge=judge)

    plan_cards("mellow loop", _ORIGIN, runtime, k=5)
    patch = plan_conditions("mellow loop", _ORIGIN, runtime, ["a", "b"], k=5)

    assert patch.from_cache is False
    assert weather.calls == 2  # one probe per card — the fan-out actually ran
    assert judge.calls == 1  # the conditions call NEVER ranks (AC-2.3)
    assert [c.canonical_id for c in patch.cards] == ["a", "b"]  # phase-1 order held
    for card in patch.cards:
        states = {s.kind: s.state for s in card.conditions}
        assert states["weather"] == "present"
        weather_status = next(s for s in card.conditions if s.kind == "weather")
        assert weather_status.source  # sourced + timestamped (the answered contract)
        assert weather_status.checked_at is not None
        assert len(card.lines) == 1  # the weather line rendered

    # AC-2.5: the COMPOSED plan warmed the key — a follow-up full /plan hits…
    plan("mellow loop", _ORIGIN, runtime, k=5)
    assert runtime.feed_cache_hit is True
    assert judge.calls == 1
    # …and a repeat conditions call serves from the cache without re-probing.
    patch2 = plan_conditions("mellow loop", _ORIGIN, runtime, ["a"], k=5)
    assert patch2.from_cache is True
    assert weather.calls == 2


def test_conditions_hard_block_returns_disclosed_set_aside_never_a_card() -> None:
    air = _SpyAdapter(
        "airnow",
        ConditionKind.air,
        lambda lat, lon: {"aqi": 350} if lat > 38.55 else {"aqi": 40},
    )
    fc = FeedCache(ttl_s=300.0, clock=lambda: 0.0)
    pending = FeedCache(ttl_s=180.0, clock=lambda: 0.0)
    runtime = _runtime(air=air, feed_cache=fc, phase1_pending=pending)

    plan_cards("mellow loop", _ORIGIN, runtime, k=5)
    patch = plan_conditions("mellow loop", _ORIGIN, runtime, ["a", "b"], k=5)

    assert [c.canonical_id for c in patch.cards] == ["a"]  # order preserved, "b" removed
    assert [t.canonical_id for t in patch.set_aside] == ["b"]
    reason = patch.set_aside[0].reasons[0]
    assert "air quality hazardous" in reason.text and reason.source  # cause + source


def test_conditions_unknown_id_is_disclosed_never_fabricated() -> None:
    fc = FeedCache(ttl_s=300.0, clock=lambda: 0.0)
    pending = FeedCache(ttl_s=180.0, clock=lambda: 0.0)
    runtime = _runtime(feed_cache=fc, phase1_pending=pending)

    plan_cards("mellow loop", _ORIGIN, runtime, k=5)
    patch = plan_conditions("mellow loop", _ORIGIN, runtime, ["a", "ghost"], k=5)

    assert [c.canonical_id for c in patch.cards] == ["a"]
    assert patch.unknown == ("ghost",)


def test_conditions_fallback_resolves_from_graph_without_warming_cache() -> None:
    # No pending plan and a cold cache (holding pen expired / another instance):
    # the ids resolve straight from the graph and the overlay still verifies —
    # but the cache is NOT warmed (no faithful full plan exists to warm it with).
    weather = _SpyAdapter("nws", ConditionKind.weather, {"temp_f": 70})
    fc = FeedCache(ttl_s=300.0, clock=lambda: 0.0)
    runtime = _runtime(
        weather=weather,
        feed_cache=fc,
        detail_rows=[_detail_row("a", 38.5, -78.4)],
    )

    patch = plan_conditions("mellow loop", _ORIGIN, runtime, ["a", "ghost"], k=5)

    assert [c.canonical_id for c in patch.cards] == ["a"]
    assert patch.unknown == ("ghost",)
    assert weather.calls == 1
    states = {s.kind: s.state for s in patch.cards[0].conditions}
    assert states["weather"] == "present"
    assert not fc.peek(_anon_key("mellow loop", _ORIGIN, 5))


def test_verify_planned_bounds_workers_default() -> None:
    # Guard the shared constant wiring: the module must default to the verifier's
    # own bound, not a private copy that could drift.
    from orchestration import two_phase

    assert two_phase.DEFAULT_MAX_WORKERS is DEFAULT_MAX_WORKERS
