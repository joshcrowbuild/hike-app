"""Engine composition test — Scout -> Verifier -> guardrail filter.

Fake session + fake probe; no DB, no network. Asserts a guardrail-blocked trail
is filtered out of the plan.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from orchestration.adapters.base import VerifiedFact
from orchestration.curator import GuardrailVerdict
from orchestration.engine import PlannedTrail, plan_from_origin, rank_plan
from orchestration.providers.base import LLMResponse
from orchestration.scout import Candidate


class _FakeSession:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def run(self, query: tuple[str, dict[str, Any]]) -> list[dict[str, Any]]:
        return self.rows


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

    def weather(lat: float, lon: float) -> VerifiedFact:
        alerts = ["Flash Flood Warning"] if lat == 39.0 else []
        return _fact({"active_alerts": alerts})

    planned = plan_from_origin(
        38.5,
        -78.4,
        _FakeSession(rows),
        {"weather": weather},
        k=10,  # type: ignore[arg-type]
    )
    assert [p.candidate.canonical_id for p in planned] == ["safe"]  # flooded hard-filtered
    assert planned[0].facts["weather"].value["active_alerts"] == []
    assert "weather" in planned[0].confidences  # confidence computed per surfaced fact


class _FakeJudge:
    name = "fake"

    def __init__(self, text: str) -> None:
        self.text = text

    def complete(self, request: Any) -> LLMResponse:
        return LLMResponse(text=self.text, model=request.model, provider=self.name)


def _planned(cid: str, dist: float) -> PlannedTrail:
    return PlannedTrail(Candidate(cid, cid.upper(), "th", dist), {}, {}, GuardrailVerdict(False))


def test_rank_plan_reorders_by_taste() -> None:
    plan = [_planned("a", 10.0), _planned("b", 20.0)]  # distance order: a, b
    out = rank_plan(plan, _FakeJudge('["b","a"]'), "m")  # judge prefers b
    assert [p.candidate.canonical_id for p in out] == ["b", "a"]
