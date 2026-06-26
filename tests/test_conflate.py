"""Conflation matcher tests — on synthetic geometries (no network)."""

from __future__ import annotations

from shapely.geometry import LineString

from ingestion.conflate.match import (
    Agreement,
    Feature,
    classify,
    geometry_agreement,
    match,
    normalize_name,
)

LINE = LineString([(-78.280, 38.550), (-78.270, 38.560)])
LINE_NEAR = LineString([(-78.28001, 38.55001), (-78.27001, 38.56001)])  # ~1 m shift
LINE_FAR = LineString([(-79.000, 39.000), (-79.000, 39.010)])


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
