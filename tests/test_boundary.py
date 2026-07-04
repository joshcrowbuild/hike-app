"""Spatial park-boundary classifier tests (Phase 2).

Covers the two things the durable signal must get right: (1) a real, irregular
protected-area polygon yields a usable boundary and cleanly separates inside from
outside; (2) everything else — a placeholder bbox rectangle, a missing file, a
non-polygon geometry — degrades to *no boundary* so the classifier abstains and the
name-only filter behaviour is unchanged (never worse than today).
"""

from __future__ import annotations

import json

from shapely.geometry import Polygon

from ingestion.boundary import (
    _is_placeholder_bbox,
    classify_outside_boundary,
    load_region_boundary,
)

# An irregular (L-shaped) "park" polygon — clearly not its own bbox. Inside point:
# (lon=-78.2, lat=38.9). Outside-but-in-bbox point: (lon=-78.05, lat=39.05), which a
# whole-bbox placeholder would wrongly call "inside".
_L_PARK = Polygon(
    [
        (-78.3, 38.8),
        (-78.1, 38.8),
        (-78.1, 39.0),
        (-78.0, 39.0),
        (-78.0, 39.1),
        (-78.3, 39.1),
        (-78.3, 38.8),
    ]
)


def _write_region(tmp_path, region_id, geometry):
    # load_region_boundary reads regions/{region_id}.geojson relative to CWD, so the
    # test runs from a tmp dir holding a regions/ subtree.
    regions = tmp_path / "regions"
    regions.mkdir(exist_ok=True)
    feat = {"type": "Feature", "properties": {"region_id": region_id}, "geometry": geometry}
    (regions / f"{region_id}.geojson").write_text(json.dumps(feat))


# ── placeholder-bbox detection ───────────────────────────────────────────────


def test_rectangle_is_placeholder():
    rect = Polygon([(-79.4, 37.8), (-78.0, 37.8), (-78.0, 39.1), (-79.4, 39.1)])
    assert _is_placeholder_bbox(rect)


def test_irregular_polygon_is_not_placeholder():
    assert not _is_placeholder_bbox(_L_PARK)


# ── classify_outside_boundary ────────────────────────────────────────────────


def test_point_inside_boundary_is_not_outside():
    assert classify_outside_boundary(38.9, -78.2, _L_PARK) is False


def test_point_outside_boundary_is_outside():
    # In the polygon's bbox but in the missing L-notch → genuinely outside.
    assert classify_outside_boundary(38.85, -78.05, _L_PARK) is True


def test_point_on_edge_counts_inside():
    # covers() keeps an on-boundary trail (a real trail must not vanish).
    assert classify_outside_boundary(38.8, -78.2, _L_PARK) is False


def test_no_boundary_degrades_to_none():
    assert classify_outside_boundary(38.9, -78.2, None) is None


def test_no_point_degrades_to_none():
    assert classify_outside_boundary(None, None, _L_PARK) is None


# ── load_region_boundary (file → polygon, with degradation) ──────────────────


def test_loads_real_polygon(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_region(tmp_path, "parkland", json.loads(json.dumps(_L_PARK.__geo_interface__)))
    boundary = load_region_boundary("parkland")
    assert boundary is not None
    assert classify_outside_boundary(38.85, -78.05, boundary) is True


def test_placeholder_bbox_region_yields_no_boundary(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rect = Polygon([(-79.4, 37.8), (-78.0, 37.8), (-78.0, 39.1), (-79.4, 39.1)])
    _write_region(tmp_path, "bboxonly", json.loads(json.dumps(rect.__geo_interface__)))
    assert load_region_boundary("bboxonly") is None


def test_missing_region_file_yields_no_boundary(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert load_region_boundary("does-not-exist") is None


def test_non_polygon_geometry_yields_no_boundary(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_region(
        tmp_path, "aline", {"type": "LineString", "coordinates": [[-78.3, 38.8], [-78.0, 39.1]]}
    )
    assert load_region_boundary("aline") is None


def test_suspicious_region_id_yields_no_boundary():
    assert load_region_boundary("../secrets") is None


def test_shipped_placeholder_regions_degrade():
    # Today's committed regions ship bbox placeholders — the signal must stay OFF for
    # them (degrade to the name-only filter) until a real boundary is committed.
    for region_id in ("shenandoah-gwj", "outer-banks", "richmond"):
        assert load_region_boundary(region_id) is None
