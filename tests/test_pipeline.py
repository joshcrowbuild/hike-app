"""Tests for ingestion.pipeline (network-free: all I/O patched)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from shapely.geometry import LineString

from ingestion.conflate.match import Feature
from ingestion.pipeline import load_region, run_pipeline


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
