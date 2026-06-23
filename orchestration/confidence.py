"""Confidence — one property, computed on read (rules #2, #7; Stage 2 §4).

Confidence combines three axes — **freshness · authority · corroboration** — into
a single 0..1 score. That score does three things and *only* these three:

  1. sets a **floor** (below it, a fact is flagged / not stated as fact),
  2. sets the **presentation** (stated / hedged / flagged),
  3. acts as a **safety flag**.

It must **never penalize ranking** (rule #2) — uncertainty is not low quality. The
Curator's taste ranking does not read confidence; this module is consumed only by
presentation and guardrail-flagging. Nothing here is persisted (computed on read).
"""

from __future__ import annotations

from dataclasses import dataclass

from orchestration.adapters.base import VerifiedFact

# Per-source authority for a datum (Stage 1 §4 tiering; generous defaults).
AUTHORITY_WEIGHT: dict[str, float] = {
    "tier1": 1.0,
    "tier1_gov": 1.0,
    "tier2": 0.6,
    "tier3": 0.4,
    "mid": 0.6,
    "med-high": 0.7,
    "low-med": 0.45,
    "low": 0.3,
    "derived": 0.7,
}
FRESHNESS_WEIGHT: dict[str, float] = {
    "live": 1.0,
    "near_real_time": 0.9,
    "slow": 0.7,
    "stale": 0.3,
}
_AUTHORITY_DEFAULT = 0.4
_FRESHNESS_DEFAULT = 0.6
FLOOR = 0.4


@dataclass(frozen=True)
class Confidence:
    score: float  # 0..1
    level: str  # "high" | "medium" | "low"
    presentation: str  # "stated" | "hedged" | "flagged"
    floor_met: bool  # below the floor -> must flag, never state as fact


def compute(
    *,
    authority: str | None = None,
    freshness: str | None = None,
    corroboration: int = 1,
    floor: float = FLOOR,
) -> Confidence:
    a = AUTHORITY_WEIGHT.get(authority or "", _AUTHORITY_DEFAULT)
    f = FRESHNESS_WEIGHT.get(freshness or "", _FRESHNESS_DEFAULT)
    # 1 independent source = baseline; more corroboration helps, with diminishing
    # returns (1 -> 0.6, 2 -> 0.8, 3+ -> 1.0).
    c = min(1.0, 0.6 + 0.2 * max(0, corroboration - 1))
    score = round(0.4 * a + 0.3 * f + 0.3 * c, 3)

    level = "high" if score >= 0.75 else "medium" if score >= 0.5 else "low"
    presentation = {"high": "stated", "medium": "hedged", "low": "flagged"}[level]
    return Confidence(score=score, level=level, presentation=presentation, floor_met=score >= floor)


def for_fact(fact: VerifiedFact, *, corroboration: int = 1) -> Confidence:
    inputs = fact.confidence_inputs if isinstance(fact.confidence_inputs, dict) else {}
    authority = inputs.get("authority")
    freshness = inputs.get("freshness")
    return compute(
        authority=authority if isinstance(authority, str) else None,
        freshness=freshness if isinstance(freshness, str) else None,
        corroboration=corroboration,
    )
