"""Confidence edge cases — boundaries, defaults, and input coercion."""

from __future__ import annotations

from datetime import datetime, timezone

from orchestration.adapters.base import VerifiedFact
from orchestration.confidence import compute, for_fact


def test_none_authority_and_freshness_use_defaults() -> None:
    c = compute(authority=None, freshness=None, corroboration=1)
    # authority default 0.4, freshness default 0.6, corroboration 0.6 → weakest-link
    # MIN = 0.4 (the default authority binds).
    expected = round(min(0.4, 0.6, 0.6), 3)
    assert c.score == expected  # 0.4
    assert c.level == "low"  # 0.4 sits below the 0.5 boundary
    assert c.presentation == "flagged"
    assert c.floor_met  # 0.4 >= FLOOR (0.4)


def test_custom_floor_changes_floor_met() -> None:
    c = compute(authority="low", freshness="stale", corroboration=1, floor=0.2)
    # weakest-link MIN(0.3, 0.3, 0.6) = 0.3 (authority/freshness both bind)
    assert c.level == "low"
    assert c.floor_met is True  # 0.3 >= 0.2


def test_high_floor_flags_medium_confidence() -> None:
    c = compute(authority="mid", freshness="slow", corroboration=1, floor=0.75)
    assert c.level == "medium"  # MIN(0.6, 0.7, 0.6) = 0.6
    assert c.floor_met is False


def test_corroboration_zero_same_as_one() -> None:
    zero = compute(authority="tier1", freshness="live", corroboration=0)
    one = compute(authority="tier1", freshness="live", corroboration=1)
    assert zero.score == one.score
    # MIN(1.0, 1.0, 0.6) = 0.6 → medium: a single source can't reach "high" (see
    # test_high_level_requires_every_axis_strong).
    assert zero.level == one.level == "medium"


def test_corroboration_cap_at_three() -> None:
    three = compute(authority="tier1", freshness="live", corroboration=3)
    ten = compute(authority="tier1", freshness="live", corroboration=10)
    assert three.score == ten.score


def test_high_level_requires_every_axis_strong() -> None:
    # Weakest-link: "high" (>= 0.75) demands ALL three axes clear it — one weak axis
    # caps the score at that axis, however strong the other two.
    strong = compute(authority="tier1_gov", freshness="live", corroboration=3)  # 1.0/1.0/1.0
    assert strong.level == "high"
    weak_corr = compute(authority="tier1_gov", freshness="live", corroboration=1)  # c=0.6 binds
    assert weak_corr.level == "medium"  # a single source can't be "high"
    weak_fresh = compute(authority="tier1_gov", freshness="stale", corroboration=3)  # f=0.3 binds
    assert weak_fresh.level == "low"  # stale can't be "high"


def test_score_level_boundary_at_05() -> None:
    low = compute(authority="low", freshness="stale", corroboration=1)
    assert low.level == "low"  # MIN(0.3, 0.3, 0.6) = 0.3
    # MIN(0.6, 0.7, 0.6) = 0.6 → medium (>= 0.5, < 0.75)
    medium = compute(authority="mid", freshness="slow", corroboration=1)
    assert medium.level == "medium"


def test_for_fact_ignores_non_string_confidence_inputs() -> None:
    fact = VerifiedFact(
        value={},
        source="test",
        fetched_at=datetime.now(timezone.utc),
        confidence_inputs={"authority": 123, "freshness": ["live"]},  # wrong types
    )
    c = for_fact(fact)
    assert c.level == "low"  # defaults applied; MIN(0.4, 0.6, 0.6) = 0.4 (authority binds)


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
    assert c.score == round(min(0.4, 0.6, 0.6), 3)  # 0.4 — weakest-link on the defaults
