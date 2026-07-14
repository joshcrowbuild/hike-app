"""Confidence — one property, computed on read (rules #2, #7; Stage 2 §4).

Confidence combines three axes — **freshness · authority · corroboration** — into
a single 0..1 score by **weakest-link fusion** (the MIN of the three, not a mean:
CDP-06 — a comfortable middle is a lie). That score does three things and *only*
these three:

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
    # Weakest-link fusion (CDP-06): a fact is only as trustworthy as its *weakest*
    # axis — freshness, authority, and corroboration must EACH hold up. The former
    # weighted mean (0.4a + 0.3f + 0.3c) let two strong axes paper over a weak third
    # (stale-but-authoritative, single-source-but-fresh) into a "comfortable middle"
    # that overstated trust; taking the MIN refuses that lie.
    #
    # AGGREGATE CONSEQUENCE (surfaced for review, never hidden): given today's axis
    # weights + corroboration curve, "stated" (score ≥ 0.75) is now UNREACHABLE for
    # every user-facing fact the engine emits — live conditions are single-source by
    # construction (c=0.6 → caps at 0.6 → hedged) and corpus facts are slow-freshness
    # (f=0.7 → caps at 0.7 → hedged), so the whole feed presents "hedged"/"flagged".
    # That is the honest floor: nothing here is verified by an independent second
    # origin. compute() itself still returns "stated" when all three axes clear 0.75
    # (see test_high_authority_live_corroborated_is_stated) — it is the *wiring* that
    # never feeds it such inputs. Restoring a reachable "stated" is a curve/weight
    # re-tune, deliberately OUT OF SCOPE for this fusion-only change (see PR body).
    score = round(min(a, f, c), 3)

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
