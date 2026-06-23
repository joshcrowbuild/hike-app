"""Tests for ingestion.pipeline (network-free: all I/O patched)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from shapely.geometry import LineString

from ingestion.conflate.match import Feature
from ingestion.pipeline import consolidate_osm_segments, load_region, run_pipeline


def _make_region_file(region_id: str = "test-region") -> tuple[Path, dict]:
    data = {
        "type": "Feature",
        "properties": {
            "region_id": region_id,
            "bbox": [-79.4, 37.8, -78.0, 39.1],
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [[-79.4, 37.8], [-78.0, 37.8], [-78.0, 39.1], [-79.4, 39.1], [-79.4, 37.8]]
            ],
        },
    }
    d = tempfile.mkdtemp()
    path = Path(d) / f"{region_id}.geojson"
    path.write_text(json.dumps(data))
    return path, data


def test_load_region_parses_bbox(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "regions").mkdir()
    (tmp_path / "regions" / "my-region.geojson").write_text(
        json.dumps(
            {
                "type": "Feature",
                "properties": {"region_id": "my-region", "bbox": [-79.0, 38.0, -78.0, 39.0]},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[-79.0, 38.0], [-78.0, 38.0], [-78.0, 39.0], [-79.0, 39.0], [-79.0, 38.0]]
                    ],
                },
            }
        )
    )
    region = load_region("my-region")
    # bbox stored as (south, west, north, east)
    assert region["bbox"] == (38.0, -79.0, 39.0, -78.0)


def _fake_feature(name: str, source: str, lon: float = -78.28) -> Feature:
    return Feature(
        name=name,
        geom=LineString([[lon, 38.55], [lon + 0.01, 38.56]]),
        source=source,
        ref=f"ref:{name}",
    )


def test_pipeline_dry_run_returns_counts(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "regions").mkdir()
    (tmp_path / "regions" / "test-r.geojson").write_text(
        json.dumps(
            {
                "type": "Feature",
                "properties": {"region_id": "test-r", "bbox": [-79.4, 37.8, -78.0, 39.1]},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[-79.4, 37.8], [-78.0, 37.8], [-78.0, 39.1], [-79.4, 39.1], [-79.4, 37.8]]
                    ],
                },
            }
        )
    )

    region = load_region("test-r")

    osm_feats = [_fake_feature("Old Rag Loop", "OSM", -78.28)]
    nps_feats = [_fake_feature("Old Rag", "NPS", -78.28)]

    with (
        patch("ingestion.pipeline.osm_fetch.fetch", return_value=osm_feats),
        patch("ingestion.pipeline.nps_fetch.fetch", return_value=nps_feats),
        patch("ingestion.pipeline.usfs_fetch.fetch", return_value=[]),
    ):
        counts = run_pipeline(region, dry_run=True)

    assert counts["osm"] == 1
    assert counts["osm_consolidated"] == 1
    assert counts["nps"] == 1
    # auto-accept depends on name+geom scores — just check structure exists
    assert "auto_accept" in counts
    assert "loaded" in counts


def test_pipeline_counts_all_sources(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "regions").mkdir()
    (tmp_path / "regions" / "test-r.geojson").write_text(
        json.dumps(
            {
                "type": "Feature",
                "properties": {"region_id": "test-r", "bbox": [-79.4, 37.8, -78.0, 39.1]},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[-79.4, 37.8], [-78.0, 37.8], [-78.0, 39.1], [-79.4, 39.1], [-79.4, 37.8]]
                    ],
                },
            }
        )
    )
    region = load_region("test-r")

    with (
        patch("ingestion.pipeline.osm_fetch.fetch", return_value=[_fake_feature("A", "OSM")]),
        patch("ingestion.pipeline.nps_fetch.fetch", return_value=[_fake_feature("B", "NPS")]),
        patch("ingestion.pipeline.usfs_fetch.fetch", return_value=[_fake_feature("C", "USFS")]),
    ):
        counts = run_pipeline(region, dry_run=True)

    assert counts["osm"] == 1
    assert counts["nps"] == 1
    assert counts["usfs"] == 1


# ── consolidate_osm_segments ──────────────────────────────────────────────────


def _seg(name: str, lon_start: float) -> Feature:
    return Feature(
        name=name,
        geom=LineString([[lon_start, 38.55], [lon_start + 0.01, 38.56]]),
        source="OSM",
        ref=f"way/{int(lon_start * 1000)}",
    )


def test_consolidate_merges_same_name_segments():
    segs = [_seg("Old Rag Loop", -78.28), _seg("Old Rag Loop", -78.27),
            _seg("Old Rag Loop", -78.26)]
    result = consolidate_osm_segments(segs)
    assert len(result) == 1
    assert result[0].name == "Old Rag Loop"
    assert result[0].source == "OSM"
    assert result[0].ref is None  # ref cleared when merging multiple ways


def test_consolidate_keeps_distinct_names():
    segs = [_seg("Old Rag Loop", -78.28), _seg("Stony Man Trail", -78.30)]
    result = consolidate_osm_segments(segs)
    assert len(result) == 2
    names = {f.name for f in result}
    assert names == {"Old Rag Loop", "Stony Man Trail"}


def test_consolidate_normalizes_before_grouping():
    # "Old Rag Trail" and "Old Rag" normalize the same → should merge
    segs = [_seg("Old Rag Trail", -78.28), _seg("Old Rag", -78.27)]
    result = consolidate_osm_segments(segs)
    assert len(result) == 1
    # Longest raw name wins
    assert result[0].name == "Old Rag Trail"


def test_consolidate_combined_geometry_contains_all_coords():
    segs = [_seg("Ridge Trail", -78.28), _seg("Ridge Trail", -78.35)]
    result = consolidate_osm_segments(segs)
    assert len(result) == 1
    # Combined geom should cover both segments' x-range
    bounds = result[0].geom.bounds  # (minx, miny, maxx, maxy)
    assert bounds[0] < -78.34  # covers left segment
    assert bounds[2] >= -78.27  # covers right segment


def test_consolidate_single_segment_preserved():
    seg = _seg("Lone Trail", -78.28)
    result = consolidate_osm_segments([seg])
    assert len(result) == 1
    assert result[0].ref == seg.ref  # ref kept when no merge happened
