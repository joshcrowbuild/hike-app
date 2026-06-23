"""Truthfulness eval (T4) — the thin Phase-0 check (Stage 4 §7).

Measures, per run: does every surfaced fact carry a source + timestamp and match
the captured adapter output? And are guardrail-violating trails (closed /
unavailable / off-leash-required) ever surfaced? Deterministic checks catch
guardrail violations; a judgment-tier LLM-judge scores fact correctness. Because
the flow is stochastic, scenarios run N times and report a pass *rate*. Doubles as
the provider bake-off rig (same eval, local vs. cloud).
"""

from __future__ import annotations


def run(scenario: str, n: int = 5) -> object:
    """Run `scenario` N times; return per-criterion pass rates. Stage 7 deepens the
    methodology; Stage 4 ships the thin version."""
    raise NotImplementedError("evals.truthfulness.run is implemented in Stage 4")
