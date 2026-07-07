"""Tests for ingestion/usfs_convert.py — the reproducible-fetch conversion core.

Hermetic: a tiny synthetic GeoJSON/GeoDataFrame fixture, no network, no real USFS
shapefile. `geopandas` is a `dev` extra (added alongside this feature, see
pyproject.toml) so this file imports it directly rather than `pytest.importorskip` —
CI is meant to actually exercise the reprojection seam, not silently skip it.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pyproj
import pytest
from shapely.geometry import LineString

from ingestion import usfs_convert

_REPO_ROOT = Path(__file__).resolve().parent.parent
_TO_3857 = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)


def _project_3857(coords: list[tuple[float, float]]) -> list[tuple[float, float]]:
    return [_TO_3857.transform(lon, lat) for lon, lat in coords]


def _feature(
    name: str | None,
    trail_no: str | None,
    coords: list[tuple[float, float]],
    name_field: str = "TRAIL_NAME",
    gis_miles: object = None,
) -> dict:
    props: dict[str, object] = {}
    if name is not None:
        props[name_field] = name
    if trail_no is not None:
        props["TRAIL_NO"] = trail_no
    if gis_miles is not None:
        props["GIS_MILES"] = gis_miles
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {"type": "LineString", "coordinates": [list(c) for c in coords]},
    }


# ── geodataframe_to_wgs84_features (the geopandas seam) ─────────────────────────


def test_geodataframe_to_wgs84_features_reprojects() -> None:
    wgs84_coords = [(-78.28, 38.55), (-78.27, 38.56)]
    line_3857 = LineString(_project_3857(wgs84_coords))
    gdf = gpd.GeoDataFrame(
        {"TRAIL_NAME": ["Test Trail"], "TRAIL_NO": ["100"]},
        geometry=[line_3857],
        crs="EPSG:3857",
    )
    features = usfs_convert.geodataframe_to_wgs84_features(gdf)
    assert len(features) == 1
    coords = features[0]["geometry"]["coordinates"]
    for (lon, lat), (exp_lon, exp_lat) in zip(coords, wgs84_coords):
        assert lon == pytest.approx(exp_lon, abs=1e-6)
        assert lat == pytest.approx(exp_lat, abs=1e-6)
    assert features[0]["properties"]["TRAIL_NAME"] == "Test Trail"


def test_geodataframe_to_wgs84_features_noop_when_already_wgs84() -> None:
    line = LineString([(-78.28, 38.55), (-78.27, 38.56)])
    gdf = gpd.GeoDataFrame({"TRAIL_NAME": ["X"]}, geometry=[line], crs="EPSG:4326")
    features = usfs_convert.geodataframe_to_wgs84_features(gdf)
    assert features[0]["geometry"]["coordinates"] == [[-78.28, 38.55], [-78.27, 38.56]]


def test_geodataframe_to_wgs84_features_no_crs_passes_through() -> None:
    # A GeoDataFrame with no CRS set (shouldn't happen for a real shapefile, but the
    # seam must not crash reprojecting an unknown CRS).
    line = LineString([(-78.28, 38.55), (-78.27, 38.56)])
    gdf = gpd.GeoDataFrame({"TRAIL_NAME": ["X"]}, geometry=[line])
    features = usfs_convert.geodataframe_to_wgs84_features(gdf)
    assert features[0]["geometry"]["coordinates"] == [[-78.28, 38.55], [-78.27, 38.56]]


# ── consolidate_by_trail_no ──────────────────────────────────────────────────────


def test_consolidate_merges_segments_sharing_trail_no() -> None:
    segs = [
        _feature("Jones Run Trail", "100", [(-78.3, 38.5), (-78.29, 38.51)]),
        _feature("Jones Run Trail", "100", [(-78.29, 38.51), (-78.28, 38.52)]),
        _feature("Jones Run Trail", "100", [(-78.5, 38.9), (-78.49, 38.91)]),
    ]
    consolidated = usfs_convert.consolidate_by_trail_no(segs)
    assert len(consolidated) == 1
    feat = consolidated[0]
    assert feat["properties"]["TRAIL_NAME"] == "Jones Run Trail"
    assert feat["geometry"]["type"] == "MultiLineString"
    assert len(feat["geometry"]["coordinates"]) == 3


def test_consolidate_leaves_single_segment_trail_unwrapped() -> None:
    segs = [_feature("Solo Trail", "200", [(-78.3, 38.5), (-78.29, 38.51)])]
    consolidated = usfs_convert.consolidate_by_trail_no(segs)
    assert len(consolidated) == 1
    assert consolidated[0]["geometry"]["type"] == "LineString"


def test_consolidate_does_not_merge_unrelated_unkeyed_features() -> None:
    # Two segments with no TRAIL_NO at all must stay separate, not get merged with
    # each other just because they share the "no trail number" bucket.
    segs = [
        _feature("Far Away Trail", None, [(-78.3, 38.5), (-78.29, 38.51)]),
        _feature("Another Trail", None, [(-79.0, 37.0), (-78.99, 37.01)]),
    ]
    consolidated = usfs_convert.consolidate_by_trail_no(segs)
    assert len(consolidated) == 2
    names = {f["properties"]["TRAIL_NAME"] for f in consolidated}
    assert names == {"Far Away Trail", "Another Trail"}


def test_consolidate_groups_by_trail_no_regardless_of_input_order() -> None:
    segs = [
        _feature("A", "1", [(0, 0), (1, 1)]),
        _feature("B", "2", [(5, 5), (6, 6)]),
        _feature("A", "1", [(2, 2), (3, 3)]),
    ]
    consolidated = usfs_convert.consolidate_by_trail_no(segs)
    assert len(consolidated) == 2
    # First-occurrence order preserved: trail "1" (seen first) precedes trail "2".
    trail_nos = [f["properties"]["TRAIL_NO"] for f in consolidated]
    assert trail_nos == ["1", "2"]


def test_consolidate_falls_back_to_trail_number_field() -> None:
    segs = [
        _feature("Fallback Trail", None, [(0, 0), (1, 1)]),
        _feature("Fallback Trail", None, [(2, 2), (3, 3)]),
    ]
    for seg in segs:
        seg["properties"]["TRAIL_NUMBER"] = "999"
    consolidated = usfs_convert.consolidate_by_trail_no(segs)
    assert len(consolidated) == 1
    assert consolidated[0]["geometry"]["type"] == "MultiLineString"


def test_consolidate_empty_input() -> None:
    assert usfs_convert.consolidate_by_trail_no([]) == []


# ── GIS_MILES aggregation (Epic 023 S2) ──────────────────────────────────────────


def test_consolidate_sums_gis_miles_across_group() -> None:
    segs = [
        _feature("Jones Run Trail", "100", [(-78.3, 38.5), (-78.29, 38.51)], gis_miles=0.174),
        _feature("Jones Run Trail", "100", [(-78.29, 38.51), (-78.28, 38.52)], gis_miles=1.35),
        _feature("Jones Run Trail", "100", [(-78.5, 38.9), (-78.49, 38.91)], gis_miles=0.627),
    ]
    consolidated = usfs_convert.consolidate_by_trail_no(segs)
    assert len(consolidated) == 1
    assert consolidated[0]["properties"]["GIS_MILES"] == pytest.approx(0.174 + 1.35 + 0.627)


def test_consolidate_gis_miles_absent_when_no_segment_has_usable_value() -> None:
    segs = [
        _feature("No Miles Trail", "300", [(-78.3, 38.5), (-78.29, 38.51)]),
        _feature("No Miles Trail", "300", [(-78.29, 38.51), (-78.28, 38.52)], gis_miles=""),
    ]
    consolidated = usfs_convert.consolidate_by_trail_no(segs)
    assert len(consolidated) == 1
    assert "GIS_MILES" not in consolidated[0]["properties"]


def test_consolidate_gis_miles_ignores_non_positive_and_non_numeric_segments() -> None:
    segs = [
        _feature("Partial Trail", "400", [(-78.3, 38.5), (-78.29, 38.51)], gis_miles=0),
        _feature("Partial Trail", "400", [(-78.29, 38.51), (-78.28, 38.52)], gis_miles="bogus"),
        _feature("Partial Trail", "400", [(-78.28, 38.52), (-78.27, 38.53)], gis_miles=2.5),
    ]
    consolidated = usfs_convert.consolidate_by_trail_no(segs)
    assert len(consolidated) == 1
    assert consolidated[0]["properties"]["GIS_MILES"] == pytest.approx(2.5)


def test_consolidate_single_segment_keeps_original_gis_miles_unchanged() -> None:
    segs = [_feature("Solo Trail", "200", [(-78.3, 38.5), (-78.29, 38.51)], gis_miles=3.1)]
    consolidated = usfs_convert.consolidate_by_trail_no(segs)
    assert len(consolidated) == 1
    assert consolidated[0]["properties"]["GIS_MILES"] == 3.1


# ── clip_to_bbox ──────────────────────────────────────────────────────────────


_SHENANDOAH_BBOX = (-79.4, 37.8, -78.0, 39.1)  # [west, south, east, north]


def test_clip_keeps_feature_inside_bbox() -> None:
    inside = _feature("Inside Trail", "1", [(-78.3, 38.5), (-78.29, 38.51)])
    assert usfs_convert.clip_to_bbox([inside], _SHENANDOAH_BBOX) == [inside]


def test_clip_drops_feature_outside_bbox() -> None:
    outside = _feature("Far Trail", "1", [(-100.0, 45.0), (-99.9, 45.1)])
    assert usfs_convert.clip_to_bbox([outside], _SHENANDOAH_BBOX) == []


def test_clip_keeps_feature_crossing_boundary() -> None:
    # One endpoint inside the bbox, one well outside — must intersect, so kept.
    crossing = _feature("Crossing Trail", "1", [(-78.3, 38.5), (-70.0, 38.5)])
    assert usfs_convert.clip_to_bbox([crossing], _SHENANDOAH_BBOX) == [crossing]


def test_clip_empty_input() -> None:
    assert usfs_convert.clip_to_bbox([], _SHENANDOAH_BBOX) == []


# ── manifest ────────────────────────────────────────────────────────────────────


def test_manifest_loads_and_has_required_keys() -> None:
    manifest = usfs_convert.load_manifest(_REPO_ROOT / usfs_convert.MANIFEST_PATH)
    for key in ("dataset", "source_url", "vintage", "sha256", "output"):
        assert key in manifest


def test_manifest_output_under_gitignored_data() -> None:
    manifest = usfs_convert.load_manifest(_REPO_ROOT / usfs_convert.MANIFEST_PATH)
    assert manifest["output"].startswith("data/usfs/")


def test_manifest_source_url_is_the_documented_usfs_edw_zip() -> None:
    manifest = usfs_convert.load_manifest(_REPO_ROOT / usfs_convert.MANIFEST_PATH)
    assert manifest["source_url"].startswith("https://data.fs.usda.gov/")
    assert manifest["source_url"].endswith(".zip")
