"""Confidence edge cases — boundaries, defaults, and input coercion."""

from __future__ import annotations

from datetime import datetime, timezone

from orchestration.adapters.base import VerifiedFact
from orchestration.confidence import compute, for_fact


def test_none_authority_and_freshness_use_defaults() -> None:
    c = compute(authority=None, freshness=None, corroboration=1)
    # authority default 0.4, freshness default 0.6, corroboration 0.6
    expected = round(0.4 * 0.4 + 0.3 * 0.6 + 0.3 * 0.6, 3)
    assert c.score == expected
    assert c.level == "medium"  # 0.52 is above the 0.5 boundary
    assert c.presentation == "hedged"
    assert c.floor_met  # 0.52 >= FLOOR (0.4)


def test_custom_floor_changes_floor_met() -> None:
    c = compute(authority="low", freshness="stale", corroboration=1, floor=0.2)
    # score is low (0.4 * 0.3 + 0.3 * 0.3 + 0.3 * 0.6 = 0.39)
    assert c.level == "low"
    assert c.floor_met is True  # 0.39 >= 0.2


def test_high_floor_flags_medium_confidence() -> None:
    c = compute(authority="mid", freshness="slow", corroboration=1, floor=0.75)
    assert c.level == "medium"  # score ~0.58
    assert c.floor_met is False


def test_corroboration_zero_same_as_one() -> None:
    zero = compute(authority="tier1", freshness="live", corroboration=0)
    one = compute(authority="tier1", freshness="live", corroboration=1)
    assert zero.score == one.score
    assert zero.level == one.level == "high"


def test_corroboration_cap_at_three() -> None:
    three = compute(authority="tier1", freshness="live", corroboration=3)
    ten = compute(authority="tier1", freshness="live", corroboration=10)
    assert three.score == ten.score


def test_score_level_boundary_at_075() -> None:
    just_below = compute(authority="tier1", freshness="live", corroboration=1)
    # a=1.0, f=1.0, c=0.6 -> score = 0.4 + 0.3 + 0.18 = 0.88 high
    assert just_below.level == "high"
    # Derive a case that sits exactly at medium/high boundary if possible
    # a=1.0, f=0.9, c=0.6 -> 0.4 + 0.27 + 0.18 = 0.85 high
    # a=0.7, f=0.9, c=0.6 -> 0.28 + 0.27 + 0.18 = 0.73 medium
    medium = compute(authority="med-high", freshness="near_real_time", corroboration=1)
    assert medium.level == "medium"
    high = compute(authority="med-high", freshness="live", corroboration=1)
    assert high.level == "high"


def test_score_level_boundary_at_05() -> None:
    low = compute(authority="low", freshness="stale", corroboration=1)
    assert low.level == "low"
    # a=0.3, f=0.3, c=0.6 -> 0.12 + 0.09 + 0.18 = 0.39 low
    # a=0.4, f=0.6, c=0.6 -> 0.16 + 0.18 + 0.18 = 0.52 medium
    medium = compute(authority="tier3", freshness="slow", corroboration=1)
    assert medium.level == "medium"


def test_for_fact_ignores_non_string_confidence_inputs() -> None:
    fact = VerifiedFact(
        value={},
        source="test",
        fetched_at=datetime.now(timezone.utc),
        confidence_inputs={"authority": 123, "freshness": ["live"]},  # wrong types
    )
    c = for_fact(fact)
    assert c.level == "medium"  # defaults applied, score ~0.52


def test_for_fact_missing_confidence_inputs() -> None:
    fact = VerifiedFact(value={}, source="test", fetched_at=datetime.now(timezone.utc))
    c = for_fact(fact)
    assert 0.0 <= c.score <= 1.0
    assert c.level in {"high", "medium", "low"}


def test_for_fact_corroboration_passed_through() -> None:
    fact = VerifiedFact(
        value={},
        source="test",
        fetched_at=datetime.now(timezone.utc),
        confidence_inputs={"authority": "tier1", "freshness": "live"},
    )
    one = for_fact(fact, corroboration=1)
    three = for_fact(fact, corroboration=3)
    assert three.score > one.score
    assert three.level == "high"


def test_unknown_authority_and_freshness_map_to_defaults() -> None:
    c = compute(authority="not-a-tier", freshness="ancient", corroboration=1)
    assert c.score == round(0.4 * 0.4 + 0.3 * 0.6 + 0.3 * 0.6, 3)
