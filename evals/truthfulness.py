"""Truthfulness eval (T4) — thin Phase-0 harness (Stage 4 §7).

Runs a scenario N times against injected engine output and scores each run on the
core promises:
  * **source-or-silence** — every surfaced fact carries a non-empty source + a
    timestamp;
  * **guardrail integrity** — no guardrail-blocked trail is ever surfaced.
An optional `judge` (the judgment-tier LLM, injected) scores fact accuracy vs the
captured adapter output. The flow is stochastic, so we report pass *rates*, not a
single pass/fail. This is the harness the provider bake-off runs (same eval,
local vs. cloud). Stage 7 deepens the methodology.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from orchestration.engine import PlannedTrail

Run = Callable[[], list[PlannedTrail]]
Judge = Callable[[list[PlannedTrail]], bool]


@dataclass(frozen=True)
class Scenario:
    name: str
    run: Run


@dataclass(frozen=True)
class CriterionResult:
    name: str
    passes: int
    runs: int

    @property
    def rate(self) -> float:
        return self.passes / self.runs if self.runs else 0.0


@dataclass(frozen=True)
class EvalReport:
    scenario: str
    runs: int
    criteria: list[CriterionResult]

    def passed(self, threshold: float = 1.0) -> bool:
        return all(c.rate >= threshold for c in self.criteria)


def source_or_silence_ok(planned: list[PlannedTrail]) -> bool:
    """Every surfaced fact must carry a non-empty source and a timestamp (#1)."""
    for trail in planned:
        for fact in trail.facts.values():
            if not fact.source or fact.fetched_at is None:
                return False
    return True


def no_blocked_surfaced(planned: list[PlannedTrail]) -> bool:
    """A guardrail-blocked trail must never reach the feed (Stage 4 §6)."""
    return all(not trail.verdict.blocked for trail in planned)


def evaluate(scenario: Scenario, n: int = 5, *, judge: Judge | None = None) -> EvalReport:
    counts = {"source_or_silence": 0, "no_blocked_surfaced": 0}
    if judge is not None:
        counts["fact_accuracy"] = 0
    for _ in range(n):
        planned = scenario.run()
        if source_or_silence_ok(planned):
            counts["source_or_silence"] += 1
        if no_blocked_surfaced(planned):
            counts["no_blocked_surfaced"] += 1
        if judge is not None and judge(planned):
            counts["fact_accuracy"] += 1
    return EvalReport(scenario.name, n, [CriterionResult(k, v, n) for k, v in counts.items()])
