"""Confidence model tests — the three axes, floor, and presentation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from orchestration.adapters.base import VerifiedFact
from orchestration.confidence import compute, for_fact


def test_high_authority_live_corroborated_is_stated() -> None:
    c = compute(authority="tier1_gov", freshness="live", corroboration=3)
    assert c.level == "high"
    assert c.presentation == "stated"
    assert c.floor_met


def test_low_authority_stale_single_is_flagged_below_floor() -> None:
    c = compute(authority="low", freshness="stale", corroboration=1)
    assert c.level == "low"
    assert c.presentation == "flagged"
    assert not c.floor_met  # below the floor -> never stated as fact


def test_corroboration_raises_score_when_it_is_the_weakest_link() -> None:
    # Under weakest-link fusion (CDP-06) corroboration lifts the score only when it is
    # the binding (weakest) axis — so hold authority + freshness strong and vary it.
    one = compute(authority="tier1_gov", freshness="live", corroboration=1)
    three = compute(authority="tier1_gov", freshness="live", corroboration=3)
    assert three.score > one.score


def test_weakest_link_is_min_not_weighted_mean() -> None:
    # A comfortable middle is a lie (CDP-06): stale data, however authoritative and
    # corroborated, is only as trustworthy as its weakest axis (freshness here). The
    # old weighted mean produced ~0.79 ("stated"); weakest-link tells the truth.
    c = compute(authority="tier1_gov", freshness="stale", corroboration=3)
    assert c.score == 0.3  # min(1.0, 0.3, 1.0) — the stale-freshness floor wins
    assert c.presentation == "flagged"
    old_weighted_mean = round(0.4 * 1.0 + 0.3 * 0.3 + 0.3 * 1.0, 3)  # 0.79
    assert old_weighted_mean >= 0.75 > c.score  # the mean overstated; MIN corrects it


def test_for_fact_reads_confidence_inputs() -> None:
    fact = VerifiedFact(
        value={"x": 1},
        source="NWS",
        fetched_at=datetime.now(timezone.utc),
        confidence_inputs={"authority": "tier1_gov", "freshness": "live"},
    )
    c = for_fact(fact)
    # A single-source live fact reads its inputs (tier1_gov + live) but is capped at
    # the corroboration=1 floor (0.6) → medium/hedged under weakest-link fusion.
    assert c.level == "medium"


def test_missing_inputs_fall_back_to_defaults() -> None:
    bare: Any = VerifiedFact(value=1, source="x", fetched_at=datetime.now(timezone.utc))
    c = for_fact(bare)
    assert 0.0 <= c.score <= 1.0  # defaults applied, no crash
