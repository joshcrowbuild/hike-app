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
    # source_kind="aggregated" keeps corroboration the binding axis at n=1 (0.6); a
    # "primary" single source would already be at 0.85 here (see the primary tests
    # below), which would make this comparison less illustrative of the climb.
    one = compute(
        authority="tier1_gov", freshness="live", corroboration=1, source_kind="aggregated"
    )
    three = compute(
        authority="tier1_gov", freshness="live", corroboration=3, source_kind="aggregated"
    )
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
    # A single-source live fact from a named institutional origin, tagged
    # source_kind="primary" exactly as every real live adapter tags it (NWS/USGS/
    # FIRMS/NPS/RIDB), reads "stated": corroboration=1 no longer caps a primary source
    # the way it caps an aggregated one (CDP-06 retune). The explicit tag in
    # confidence_inputs wins over for_fact's fail-closed default.
    fact = VerifiedFact(
        value={"x": 1},
        source="NWS",
        fetched_at=datetime.now(timezone.utc),
        confidence_inputs={"authority": "tier1_gov", "freshness": "live", "source_kind": "primary"},
    )
    c = for_fact(fact)
    assert c.level == "high"
    assert c.presentation == "stated"


def test_for_fact_untagged_source_is_fail_closed_hedged() -> None:
    # Fail-closed default (rule #1 in spirit): a fact whose confidence_inputs omit
    # source_kind is treated as unverified/"aggregated", NOT authoritative — even with
    # maxed authority + freshness it hedges at the corroboration=1 baseline (0.6). This
    # removes the latent over-trust risk if a future adapter forgets to tag; every real
    # adapter tags explicitly today, so no real fact is affected.
    fact = VerifiedFact(
        value={"x": 1},
        source="untagged",
        fetched_at=datetime.now(timezone.utc),
        confidence_inputs={"authority": "tier1_gov", "freshness": "live"},
    )
    c = for_fact(fact)
    assert c.score == 0.6
    assert c.presentation == "hedged"


def test_for_fact_aggregated_single_source_stays_hedged() -> None:
    # AirNow-shaped fact: explicit source_kind="aggregated" in confidence_inputs (no
    # distinct-origin id — a blend of monitors) keeps the original 0.6 n=1 baseline,
    # so it hedges even though authority + freshness are both maxed.
    fact = VerifiedFact(
        value={"aqi": 42},
        source="EPA AirNow",
        fetched_at=datetime.now(timezone.utc),
        confidence_inputs={
            "authority": "tier1_gov",
            "freshness": "live",
            "source_kind": "aggregated",
        },
    )
    c = for_fact(fact)
    assert c.level == "medium"
    assert c.presentation == "hedged"


def test_missing_inputs_fall_back_to_defaults() -> None:
    bare: Any = VerifiedFact(value=1, source="x", fetched_at=datetime.now(timezone.utc))
    c = for_fact(bare)
    assert 0.0 <= c.score <= 1.0  # defaults applied, no crash


# ── CDP-06 retune: the presentation must discriminate under weakest-link MIN, and a
# genuinely strong fact must be able to reach "stated" again (Rule #2 / vision: a
# hedge on everything stops being a signal). Four archetypes the engine actually
# emits, pinned explicitly so a future curve change cannot silently flatten them.


def test_authoritative_live_single_source_is_stated() -> None:
    # A single but institutionally-designated live origin (NWS gridpoint forecast,
    # USGS gauge, FIRMS satellite detection, NPS unit) is NOT the same thing as an
    # unverified single source — there is no second "independent" NWS office to
    # demand for the same gridpoint. It reaches "stated" at corroboration=1, exactly
    # how the engine actually wires live facts (engine.py always passes
    # corroboration=1 for point conditions; see PlannedTrail docs).
    c = compute(authority="tier1_gov", freshness="live", corroboration=1, source_kind="primary")
    assert c.score == 0.85
    assert c.level == "high"
    assert c.presentation == "stated"
    assert c.floor_met


def test_aggregated_single_source_condition_is_hedged_not_stated() -> None:
    # AirNow-shaped input: aggregated authority with no distinct-origin id must NOT
    # reach "stated" merely because it's fresh and nominally "tier1_gov" — the
    # aggregation itself is the uncorroborated part. Corroboration=1 caps it at 0.6.
    c = compute(authority="tier1_gov", freshness="live", corroboration=1, source_kind="aggregated")
    assert c.score == 0.6
    assert c.level == "medium"
    assert c.presentation == "hedged"


def test_slow_corpus_fact_corroborated_is_stated() -> None:
    # A slow/structural corpus fact (a trail's geometry from OSM/USGS) is not "stale"
    # at its expected cadence — cadence-aware freshness (0.85) no longer binds it
    # below "stated" once genuine cross-provider corroboration (>= 2 distinct
    # origins) supplies the second check. min(1.0, 0.85, 0.8) = 0.8.
    c = compute(authority="tier1", freshness="slow", corroboration=2, source_kind="aggregated")
    assert c.score == 0.8
    assert c.level == "high"
    assert c.presentation == "stated"
    # A third origin lifts corroboration to 1.0, but slow freshness (0.85) now binds
    # instead — still "stated" either way. min(1.0, 0.85, 1.0) = 0.85.
    three = compute(authority="tier1", freshness="slow", corroboration=3, source_kind="aggregated")
    assert three.score == 0.85
    assert three.presentation == "stated"


def test_single_source_corpus_fact_stays_hedged() -> None:
    # The corroboration gate is honest in both directions: a slow structural fact
    # backed by only ONE upstream provider (not yet SAME_AS-matched to a second) is
    # genuinely unverified — the "aggregated" n=1 baseline (0.6) still binds even
    # though slow freshness alone would clear the bar.
    c = compute(authority="tier1", freshness="slow", corroboration=1, source_kind="aggregated")
    assert c.score == 0.6
    assert c.presentation == "hedged"


def test_stale_fact_is_flagged_even_when_authoritative_and_corroborated() -> None:
    # A stale fact reads "flagged" no matter how authoritative or corroborated, and
    # regardless of source_kind — the stale-freshness floor (0.3) binds.
    c = compute(authority="tier1_gov", freshness="stale", corroboration=3, source_kind="primary")
    assert c.score == 0.3
    assert c.level == "low"
    assert c.presentation == "flagged"
    assert not c.floor_met


def test_presentation_discriminates_across_the_four_archetypes() -> None:
    # The whole point of the retune: distinct fact archetypes the engine actually
    # emits do NOT collapse to one presentation. If a future curve change flattens
    # them, this fails loudly.
    authoritative_live = compute(
        authority="tier1_gov", freshness="live", corroboration=1, source_kind="primary"
    )
    aggregated_live = compute(
        authority="tier1_gov", freshness="live", corroboration=1, source_kind="aggregated"
    )
    corroborated_corpus = compute(
        authority="tier1", freshness="slow", corroboration=2, source_kind="aggregated"
    )
    stale = compute(
        authority="tier1_gov", freshness="stale", corroboration=3, source_kind="primary"
    )
    assert authoritative_live.presentation == "stated"
    assert aggregated_live.presentation == "hedged"
    assert corroborated_corpus.presentation == "stated"
    assert stale.presentation == "flagged"
