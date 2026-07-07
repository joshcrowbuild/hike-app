"""Conflation matcher tests — on synthetic geometries (no network)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from shapely.geometry import LineString

from ingestion.conflate.match import (
    Agreement,
    Feature,
    classify,
    geometry_agreement,
    match,
    name_similarity,
    normalize_for_match,
    normalize_name,
)

LINE = LineString([(-78.280, 38.550), (-78.270, 38.560)])
LINE_NEAR = LineString([(-78.28001, 38.55001), (-78.27001, 38.56001)])  # ~1 m shift
LINE_FAR = LineString([(-79.000, 39.000), (-79.000, 39.010)])
# A long trail and a short segment lying on its first third (real containment geometry).
LINE_LONG = LineString([(-78.280, 38.550), (-78.260, 38.550), (-78.240, 38.550)])
LINE_SUBSEG = LineString([(-78.278, 38.55001), (-78.272, 38.54999)])  # ~1/6 of LINE_LONG, on it


def test_normalize_name_strips_suffixes() -> None:
    assert normalize_name("Old Rag Trail") == "old rag"
    assert normalize_name("Whiteoak Canyon Trl") == "whiteoak canyon"
    assert normalize_name("FR 600 Road") == "600"


def test_geometry_agreement_near_vs_far() -> None:
    near = geometry_agreement(LINE, LINE_NEAR)
    far = geometry_agreement(LINE, LINE_FAR)
    assert near.overlap > 0.8
    assert near.hausdorff_m < 10
    assert far.overlap == 0.0
    assert far.hausdorff_m > 10_000


def test_classify_buckets() -> None:
    strong = Agreement(overlap=0.9, hausdorff_m=5)
    near = Agreement(overlap=0.1, hausdorff_m=50)
    apart = Agreement(overlap=0.0, hausdorff_m=99_999)
    assert classify(95, strong) == "auto-accept"
    assert classify(70, near) == "review"
    assert classify(95, apart) == "no-match"  # same name, totally different place
    assert classify(50, strong) == "no-match"  # geometry agrees but names don't


def test_match_end_to_end() -> None:
    osm = [Feature("Old Rag Trail", LINE, "osm")]
    agency = [Feature("Old Rag", LINE_NEAR, "agency"), Feature("Cedar Run", LINE_FAR, "agency")]
    results = match(osm, agency)
    assert len(results) == 1
    assert results[0].verdict == "auto-accept"
    assert results[0].b.name == "Old Rag"


# ── normalize_for_match — the matcher-local canonicaliser (distinct from normalize_name) ──


def test_normalize_for_match_strips_generic_qualifiers() -> None:
    # The marquee failure the Wave-2 review found: agencies decorate names with
    # National/Scenic/Recreation; OSM omits them. Strip so the pair scores high.
    assert normalize_for_match("Appalachian National Scenic Trail") == "appalachian"
    assert normalize_for_match("Virginia Creeper National Recreation Trail") == "virginia creeper"
    # A name that is ALL generic tokens must not collapse to "" (a false 100 vs any other).
    assert normalize_for_match("National Scenic Trail") == "national scenic trail"


def test_normalize_for_match_expands_true_abbreviations() -> None:
    assert normalize_for_match("Iron Mtn Trail") == "iron mountain"
    assert normalize_for_match("Big Cr") == "big creek"
    assert normalize_for_match("Laurel Fk") == "laurel fork"


def test_normalize_for_match_keeps_discriminating_suffixes_distinct() -> None:
    # spur/loop/tie/… are NOT stripped: a distinct route stays distinct.
    assert normalize_for_match("Mount Rogers Spur Trail") == "mount rogers spur"
    assert normalize_for_match("Old Rag Loop") == "old rag loop"
    assert normalize_for_match("Rogers Tie Trail") == "rogers tie"
    assert normalize_for_match("Mount Rogers Trail") != normalize_for_match("Mount Rogers Spur")


# ── Real agency↔OSM name pairs — marquee trails must reach the corpus ──────────


def test_marquee_agency_osm_pairs_score_high_and_auto_accept() -> None:
    # (osm_name, agency_name) — real forms that the OLD scorer left below the floor.
    pairs = [
        ("Appalachian Trail", "Appalachian National Scenic Trail"),  # old: ~58 → dropped
        ("Virginia Creeper Trail", "Virginia Creeper National Recreation Trail"),  # old: ~62
        ("Iron Mtn Trail", "Iron Mountain Trail"),  # abbreviation expansion
        ("Mount Rogers Trail", "Mount Rogers Trail"),
    ]
    for osm_name, agency_name in pairs:
        assert name_similarity(osm_name, agency_name) >= 85, (osm_name, agency_name)
        results = match(
            [Feature(osm_name, LINE, "osm")], [Feature(agency_name, LINE_NEAR, "agency")]
        )
        assert len(results) == 1, (osm_name, agency_name)
        assert results[0].verdict == "auto-accept", (osm_name, agency_name)


def test_spur_and_tie_do_not_merge_into_main_trail() -> None:
    # Both share geometry with the main trail (strong geometry), so a geometry-primary
    # matcher would happily merge them — but the discriminating suffix vetoes auto-accept,
    # so the main trail's authoritative name is never stamped onto the spur/tie (Rule #1).
    osm = [Feature("Mount Rogers Trail", LINE, "osm")]
    agency = [
        Feature("Mount Rogers Spur Trail", LINE_NEAR, "agency"),
        Feature("Mount Rogers Tie Trail", LINE_NEAR, "agency"),
    ]
    results = match(osm, agency)
    assert len(results) == 2
    assert all(r.verdict == "review" for r in results)  # flagged, never merged
    assert not any(r.verdict == "auto-accept" for r in results)


def test_contained_subsegment_is_kept_not_rejected() -> None:
    # Rule #5: a short agency segment lying ON a long OSM trail with an agreeing name is
    # KEPT (auto-accept), not rejected as a length mismatch. Its share of the long trail's
    # area is small, but its CONTAINMENT is ~1.
    ag = geometry_agreement(LINE_LONG, LINE_SUBSEG)
    assert ag.containment > 0.9
    results = match(
        [Feature("Big Run Trail", LINE_LONG, "osm")], [Feature("Big Run", LINE_SUBSEG, "agency")]
    )
    assert len(results) == 1
    assert results[0].verdict == "auto-accept"


# ── Epic 023 S1 — Feature carries length/gain, positional construction unaffected ──


def test_feature_positional_construction_defaults_length_gain_to_none() -> None:
    # Existing positional call sites (e.g. this exact call, test_match_end_to_end above)
    # must keep working — the four new fields are keyword-only-by-default and None.
    feat = Feature("Old Rag Trail", LINE, "osm")
    assert feat.length_mi is None
    assert feat.length_source is None
    assert feat.gain_ft is None
    assert feat.gain_source is None


def test_feature_length_gain_fields_settable_and_frozen() -> None:
    feat = Feature(
        "Old Rag Trail",
        LINE,
        "USFS",
        length_mi=4.2,
        length_source="USFS",
        gain_ft=1200.0,
        gain_source="USFS",
    )
    assert feat.length_mi == 4.2
    assert feat.length_source == "USFS"
    assert feat.gain_ft == 1200.0
    assert feat.gain_source == "USFS"
    with pytest.raises(FrozenInstanceError):
        feat.length_mi = 5.0  # type: ignore[misc]
