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
from typing import Literal

from orchestration.adapters.base import VerifiedFact

SourceKind = Literal["primary", "aggregated"]

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
# Cadence-aware freshness (CDP-06 retune): "slow" is the expected cadence of
# bulk-ingested corpus data (a trail's distance/ascent from OSM/USGS), not a decay
# clock. A way mapped months ago is still there — it is not "6-hour-old weather" —
# so slow-but-at-its-expected-cadence data is honestly high-trust (0.85, above the
# 0.75 "stated" bar), leaving corroboration as the axis that actually gates
# structural facts to "stated". Genuinely outdated data still reads "stale" (0.3)
# and is unaffected by this change.
FRESHNESS_WEIGHT: dict[str, float] = {
    "live": 1.0,
    "near_real_time": 0.9,
    "slow": 0.85,
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
    source_kind: SourceKind = "aggregated",
    floor: float = FLOOR,
) -> Confidence:
    a = AUTHORITY_WEIGHT.get(authority or "", _AUTHORITY_DEFAULT)
    f = FRESHNESS_WEIGHT.get(freshness or "", _FRESHNESS_DEFAULT)
    n = max(1, corroboration)
    # CDP-06 retune — corroboration discriminates WHAT "one source" means, not just
    # how many there are. The pre-retune curve conflated two different situations
    # under the same n=1 baseline (0.6):
    #   • a single AUTHORITATIVE/PRIMARY origin — the one NWS office+gridpoint for a
    #     point, the nearest USGS gauge, a FIRMS satellite detection, the nearest NPS
    #     unit: each names a specific, uniquely-designated institutional source. There
    #     is no second "independent" NWS forecast for the same gridpoint to demand —
    #     asking for one is a category error, so hedging it as "single unverified
    #     source" misrepresents its reliability. These start at 0.85 (clears "stated"
    #     with strong authority+freshness) and still climb toward 1.0 if a genuinely
    #     distinct second/third origin does show up.
    #   • a single AGGREGATED/UNVERIFIED origin — AirNow blends many monitors behind
    #     one number with no distinct-origin id (self-documented in the adapter); a
    #     corpus fact backed by only one upstream data provider (not yet SAME_AS-
    #     matched to a second) is similarly not yet independently checked. These keep
    #     the original 0.6 baseline, climbing with diminishing returns as real distinct
    #     origins are added (1 -> 0.6, 2 -> 0.8, 3+ -> 1.0) — corroboration is the
    #     honest gate to "stated" for this kind, exactly as the pre-retune curve
    #     intended it to be for everything.
    # Either way, more corroboration never hurts and 3+ distinct origins saturate at
    # 1.0 — only the n=1 floor differs by kind.
    if source_kind == "primary":
        c = 0.85 if n <= 1 else (0.9 if n == 2 else 1.0)
    else:
        c = min(1.0, 0.6 + 0.2 * (n - 1))
    # Weakest-link fusion (CDP-06): a fact is only as trustworthy as its *weakest*
    # axis — freshness, authority, and corroboration must EACH hold up. The former
    # weighted mean (0.4a + 0.3f + 0.3c) let two strong axes paper over a weak third
    # (stale-but-authoritative, single-source-but-fresh) into a "comfortable middle"
    # that overstated trust; taking the MIN refuses that lie.
    #
    # RETUNE OUTCOME (was: "stated" unreachable for every fact; see git history for
    # that interim state and its rationale). With cadence-aware freshness (slow=0.85)
    # and the primary/aggregated corroboration split above, "stated" is reachable
    # again for genuinely strong facts — a single authoritative live reading (NWS/
    # USGS/FIRMS/NPS) or a cross-provider-corroborated structural corpus fact — while
    # staying unreachable for a single aggregated/unverified source or actually-stale
    # data. See tests/test_confidence.py for the pinned archetypes.
    score = round(min(a, f, c), 3)

    level = "high" if score >= 0.75 else "medium" if score >= 0.5 else "low"
    presentation = {"high": "stated", "medium": "hedged", "low": "flagged"}[level]
    return Confidence(score=score, level=level, presentation=presentation, floor_met=score >= floor)


def for_fact(
    fact: VerifiedFact, *, corroboration: int = 1, source_kind: SourceKind = "aggregated"
) -> Confidence:
    """The `source_kind` default is fail-closed "aggregated" (source-or-silence in
    spirit, rule #1): an *untagged* source is treated as unverified — it must earn
    "stated" through real corroboration, and can never falsely reach "stated" on the
    single-authoritative-origin baseline just because someone forgot to tag it. Every
    real adapter today tags explicitly in its `confidence_inputs["source_kind"]`
    (NWS/USGS/FIRMS/NPS/RIDB -> "primary"; AirNow -> "aggregated"), and that explicit
    tag always wins over this default — so the reachability of every real fact is
    unchanged; only an unlabeled future fact hedges instead of over-trusting."""
    inputs = fact.confidence_inputs if isinstance(fact.confidence_inputs, dict) else {}
    authority = inputs.get("authority")
    freshness = inputs.get("freshness")
    kind = inputs.get("source_kind")
    return compute(
        authority=authority if isinstance(authority, str) else None,
        freshness=freshness if isinstance(freshness, str) else None,
        corroboration=corroboration,
        source_kind=kind if kind in ("primary", "aggregated") else source_kind,
    )
