"""Engine composition test — Scout -> Verifier -> guardrail filter.

Fake session + fake adapters; no DB, no network. Asserts a guardrail-blocked trail
is filtered out of the plan, and that the pipeline still builds cards.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from orchestration.adapters.base import (
    AdapterHealth,
    ConditionKind,
    LiveAdapter,
    LiveCapabilities,
    Point,
    VerifiedFact,
)
from orchestration.curator import GuardrailVerdict
from orchestration.engine import PlannedTrail, Runtime, plan, plan_from_origin, rank_plan
from orchestration.providers.base import LLMResponse
from orchestration.scout import Candidate


class _FakeSession:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def run(self, query: tuple[str, dict[str, Any]]) -> list[dict[str, Any]]:
        cypher, _ = query
        # Context assembly queries (Belief, PhysicalProfile, Episode) return []
        # so they don't leak trail rows into the personal-context path.
        if any(k in cypher for k in ("Belief", "PhysicalProfile", "Episode")):
            return []
        return self.rows


class _FakeAdapter(LiveAdapter):
    """A point-probe adapter driven by a (lat, lon) -> value function."""

    def __init__(self, name: str, kind: ConditionKind, fn: Callable[[float, float], Any]) -> None:
        self.name = name
        self.kind = kind
        self._fn = fn

    def capabilities(self) -> LiveCapabilities:
        return LiveCapabilities(True, False, True)

    def probe(self, point: Point, when: datetime | None = None) -> VerifiedFact | None:
        value = self._fn(point.lat, point.lon)
        return None if value is None else _fact(value)

    def health(self) -> AdapterHealth:
        return AdapterHealth.OK

    @classmethod
    def from_config(cls, settings: Any) -> "LiveAdapter | None":
        return None


def _weather_probes(fn: Callable[[float, float], Any]) -> dict[ConditionKind, list[LiveAdapter]]:
    return {ConditionKind.weather: [_FakeAdapter("w", ConditionKind.weather, fn)]}


def _fact(value: Any) -> VerifiedFact:
    return VerifiedFact(value=value, source="t", fetched_at=datetime.now(timezone.utc))


def _row(cid: str, lat: float, lon: float, dist: float) -> dict[str, Any]:
    return {
        "canonical_id": cid,
        "name": cid,
        "trailhead_id": "th",
        "distance_m": dist,
        "point": {"latitude": lat, "longitude": lon},
    }


def test_plan_filters_guardrail_blocked_trails() -> None:
    rows = [_row("safe", 38.5, -78.4, 100), _row("flooded", 39.0, -79.0, 200)]

    def weather(lat: float, lon: float) -> Any:
        return {"active_alerts": ["Flash Flood Warning"] if lat == 39.0 else []}

    batch = plan_from_origin(
        38.5,
        -78.4,
        _FakeSession(rows),  # type: ignore[arg-type]
        _weather_probes(weather),
        k=10,
    )
    planned = batch.trails
    assert [p.candidate.canonical_id for p in planned] == ["safe"]  # flooded hard-filtered
    assert planned[0].facts[ConditionKind.weather].value["active_alerts"] == []
    assert ConditionKind.weather in planned[0].confidences  # confidence per surfaced fact


class _FakeJudge:
    name = "fake"

    def __init__(self, text: str) -> None:
        self.text = text

    def complete(self, request: Any) -> LLMResponse:
        return LLMResponse(text=self.text, model=request.model, provider=self.name)


def _planned(cid: str, dist: float) -> PlannedTrail:
    return PlannedTrail(Candidate(cid, cid.upper(), "th", dist), {}, {}, GuardrailVerdict(False))


def test_rank_plan_reorders_by_taste() -> None:
    plan_list = [_planned("a", 10.0), _planned("b", 20.0)]  # distance order: a, b
    out = rank_plan(plan_list, _FakeJudge('["b","a"]'), "m")  # judge prefers b
    assert [p.candidate.canonical_id for p in out] == ["b", "a"]


def test_plan_builds_feed_with_cards() -> None:
    rows = [_row("safe", 38.5, -78.4, 1609.344)]  # 1 mile out

    def weather(lat: float, lon: float) -> Any:
        return {"short_forecast": "Clear", "temperature": 60, "temperature_unit": "F"}

    runtime = Runtime(session=_FakeSession(rows), probes=_weather_probes(weather))  # type: ignore[arg-type]
    feed = plan("trails near me", (38.5, -78.4), runtime, k=5)
    assert feed.query == "trails near me"
    assert len(feed.cards) == 1
    card = feed.cards[0]
    assert card.canonical_id == "safe"
    assert card.distance_mi == 1.0
    assert any(line.kind == "weather" for line in card.lines)


# ── Drive-time integration (Epic 005 S4/S5) ──


class _CountingWeather(LiveAdapter):
    name = "w"
    kind = ConditionKind.weather

    def __init__(self) -> None:
        self.calls = 0

    def capabilities(self) -> LiveCapabilities:
        return LiveCapabilities(True, False, True)

    def probe(self, point: Point, when: datetime | None = None) -> VerifiedFact | None:
        self.calls += 1
        return _fact({"short_forecast": "Sunny"})

    def health(self) -> AdapterHealth:
        return AdapterHealth.OK

    @classmethod
    def from_config(cls, settings: Any) -> "LiveAdapter | None":
        return None


class _PruneComputer:
    """No isochrone → matrix-only; the second target is over budget."""

    def isochrone(self, origin: Any, time_budget_s: float) -> Any:
        return None

    def matrix(self, origin: Any, targets: list[Any]) -> list[VerifiedFact | None]:
        secs = [600, 1800]
        return [_fact({"drive_seconds": secs[i]}) for i in range(len(targets))]

    def health(self) -> Any:
        return None


def test_s4_ac4_pruned_candidate_incurs_no_probe() -> None:
    rows = [_row("near", 38.6, -78.5, 100), _row("far", 38.9, -79.0, 200)]
    weather = _CountingWeather()
    batch = plan_from_origin(
        38.5,
        -78.4,
        _FakeSession(rows),  # type: ignore[arg-type]
        {ConditionKind.weather: [weather]},
        k=10,
        drive_time=_PruneComputer(),  # type: ignore[arg-type]
        budget_s=1000.0,
    )
    kept = [p.candidate.canonical_id for p in batch.trails]
    assert kept == ["near"]  # far pruned by drive budget (1800 > 1000)
    assert weather.calls == 1  # the pruned candidate never reached the Verifier (AC-4.4)
    # The survivor carries a sourced drive-time fact, folded into facts.
    assert ConditionKind.drive_time in batch.trails[0].facts


def _planned_drive(cid: str, drive_secs: float) -> PlannedTrail:
    fact = _fact({"drive_seconds": drive_secs})
    return PlannedTrail(
        Candidate(cid, cid.upper(), "th", 0.0),
        {ConditionKind.drive_time: fact},
        {},
        GuardrailVerdict(False),
    )


def test_s5_ac1_closer_by_road_wins_when_judge_indifferent() -> None:
    far = _planned_drive("far", 3000.0)  # 50 min
    near = _planned_drive("near", 1200.0)  # 20 min
    out = rank_plan([far, near], _FakeJudge("[]"), "m")  # judge indifferent → drive pre-order holds
    assert [p.candidate.canonical_id for p in out] == ["near", "far"]


def test_s5_ac3_absent_drive_time_applies_no_penalty() -> None:
    # One candidate has a time, one does not → no deterministic pre-sort, judge order holds.
    timed = _planned_drive("timed", 3000.0)
    untimed = _planned("untimed", 0.0)  # no drive fact
    out = rank_plan([timed, untimed], _FakeJudge('["timed","untimed"]'), "m")
    assert [p.candidate.canonical_id for p in out] == ["timed", "untimed"]
