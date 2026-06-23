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


def test_corroboration_raises_score_without_changing_axes() -> None:
    one = compute(authority="mid", freshness="slow", corroboration=1)
    three = compute(authority="mid", freshness="slow", corroboration=3)
    assert three.score > one.score


def test_for_fact_reads_confidence_inputs() -> None:
    fact = VerifiedFact(
        value={"x": 1},
        source="NWS",
        fetched_at=datetime.now(timezone.utc),
        confidence_inputs={"authority": "tier1_gov", "freshness": "live"},
    )
    c = for_fact(fact)
    assert c.level == "high"


def test_missing_inputs_fall_back_to_defaults() -> None:
    bare: Any = VerifiedFact(value=1, source="x", fetched_at=datetime.now(timezone.utc))
    c = for_fact(bare)
    assert 0.0 <= c.score <= 1.0  # defaults applied, no crash
