"""Truthfulness eval-harness tests (fakes; no engine run needed)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from evals.truthfulness import (
    Scenario,
    evaluate,
    no_blocked_surfaced,
    source_or_silence_ok,
)
from orchestration.adapters.base import VerifiedFact
from orchestration.curator import GuardrailVerdict
from orchestration.engine import PlannedTrail
from orchestration.scout import Candidate


def _trail(*, source: str = "NWS", blocked: bool = False) -> PlannedTrail:
    fact = VerifiedFact(value={"x": 1}, source=source, fetched_at=datetime.now(timezone.utc))
    return PlannedTrail(
        Candidate("a", "A", "th", 10.0), {"weather": fact}, {}, GuardrailVerdict(blocked)
    )


def test_clean_run_passes_all() -> None:
    report = evaluate(Scenario("clean", lambda: [_trail()]), n=3)
    assert report.passed()
    assert {c.name for c in report.criteria} == {"source_or_silence", "no_blocked_surfaced"}


def test_missing_source_fails_source_or_silence() -> None:
    assert source_or_silence_ok([_trail(source="")]) is False
    assert not evaluate(Scenario("bad", lambda: [_trail(source="")]), n=2).passed()


def test_blocked_trail_fails_integrity() -> None:
    assert no_blocked_surfaced([_trail(blocked=True)]) is False


def test_judge_criterion_added_and_scored() -> None:
    judge: Any = lambda planned: False  # noqa: E731 - terse fake for the test
    report = evaluate(Scenario("j", lambda: [_trail()]), n=4, judge=judge)
    fact_accuracy = next(c for c in report.criteria if c.name == "fact_accuracy")
    assert fact_accuracy.rate == 0.0
    assert not report.passed()
