"""Tests for ingestion fetch layer (network-free: injectable httpx client + fake file)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import httpx
import pytest
from shapely.geometry import LineString, MultiLineString

from ingestion.fetch import nps as nps_fetch
from ingestion.fetch import osm as osm_fetch
from ingestion.fetch import usfs as usfs_fetch

# ── Helpers ───────────────────────────────────────────────────────────────────


def _osm_response(elements: list[dict]) -> httpx.Response:
    body = json.dumps({"elements": elements}).encode()
    return httpx.Response(200, content=body, headers={"content-type": "application/json"})


def _arcgis_response(features: list[dict]) -> httpx.Response:
    body = json.dumps({"type": "FeatureCollection", "features": features}).encode()
    return httpx.Response(200, content=body, headers={"content-type": "application/json"})


def _osm_element(name: str, osm_id: int = 1, coords: list | None = None) -> dict:
    coords = coords or [[-78.28, 38.55], [-78.27, 38.56]]
    return {
        "type": "way",
        "id": osm_id,
        "tags": {"name": name, "highway": "path"},
        "geometry": [{"lon": c[0], "lat": c[1]} for c in coords],
    }


def _arcgis_feature(name: str, name_field: str = "TRLNAME", coords: list | None = None) -> dict:
    coords = coords or [[-78.28, 38.55], [-78.27, 38.56]]
    return {
        "type": "Feature",
        "properties": {name_field: name},
        "geometry": {"type": "LineString", "coordinates": coords},
    }


# ── OSM fetch ─────────────────────────────────────────────────────────────────


def test_osm_fetch_returns_features():
    transport = httpx.MockTransport(lambda r: _osm_response([_osm_element("Old Rag Loop", 123)]))
    client = httpx.Client(transport=transport)
    features = osm_fetch.fetch((38.55, -78.45, 38.70, -78.25), client=client)
    assert len(features) == 1
    assert features[0].name == "Old Rag Loop"
    assert features[0].source == "OSM"
    assert features[0].ref == "way/123"
    assert isinstance(features[0].geom, LineString)


def test_osm_fetch_skips_unnamed():
    unnamed = {
        "type": "way",
        "id": 2,
        "tags": {"highway": "path"},
        "geometry": [{"lon": -78.28, "lat": 38.55}, {"lon": -78.27, "lat": 38.56}],
    }
    transport = httpx.MockTransport(lambda r: _osm_response([unnamed]))
    client = httpx.Client(transport=transport)
    features = osm_fetch.fetch((38.55, -78.45, 38.70, -78.25), client=client)
    assert features == []


def test_osm_fetch_returns_empty_on_error():
    transport = httpx.MockTransport(lambda r: httpx.Response(500))
    client = httpx.Client(transport=transport)
    features = osm_fetch.fetch((38.55, -78.45, 38.70, -78.25), client=client)
    assert features == []


def test_osm_fetch_skips_short_geometry():
    short = {
        "type": "way",
        "id": 3,
        "tags": {"name": "Ghost Trail", "highway": "path"},
        "geometry": [{"lon": -78.28, "lat": 38.55}],
    }
    transport = httpx.MockTransport(lambda r: _osm_response([short]))
    client = httpx.Client(transport=transport)
    assert osm_fetch.fetch((38.55, -78.45, 38.70, -78.25), client=client) == []


# ── NPS fetch ─────────────────────────────────────────────────────────────────


def test_nps_fetch_returns_features():
    feats = [_arcgis_feature("Old Rag", name_field="TRLNAME")]
    responses = [_arcgis_response(feats), _arcgis_response([])]
    call_count = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        r = responses[min(call_count[0], len(responses) - 1)]
        call_count[0] += 1
        return r

    client = httpx.Client(transport=httpx.MockTransport(handler))
    features = nps_fetch.fetch((38.55, -78.45, 38.70, -78.25), client=client)
    assert len(features) == 1
    assert features[0].name == "Old Rag"
    assert features[0].source == "NPS"


def test_nps_fetch_collapses_multipart_into_one_feature():
    # A MultiLineString with 2 parts sharing one OBJECTID must yield ONE Feature
    # whose geometry contains both parts, never two Features (Epic 023 S3).
    multi = {
        "type": "Feature",
        "properties": {"TRLNAME": "Fragmented Trail", "OBJECTID": 42},
        "geometry": {
            "type": "MultiLineString",
            "coordinates": [
                [[-78.28, 38.55], [-78.27, 38.56]],
                [[-78.27, 38.56], [-78.26, 38.57]],
            ],
        },
    }
    responses = [_arcgis_response([multi]), _arcgis_response([])]
    call_count = [0]

    def handler(r: httpx.Request) -> httpx.Response:
        resp = responses[min(call_count[0], len(responses) - 1)]
        call_count[0] += 1
        return resp

    client = httpx.Client(transport=httpx.MockTransport(handler))
    features = nps_fetch.fetch((38.55, -78.45, 38.70, -78.25), client=client)
    assert len(features) == 1
    assert features[0].name == "Fragmented Trail"
    assert features[0].ref == "42"
    all_coords = (
        list(features[0].geom.coords)
        if not isinstance(features[0].geom, MultiLineString)
        else [c for line in features[0].geom.geoms for c in line.coords]
    )
    assert (-78.28, 38.55) in all_coords
    assert (-78.26, 38.57) in all_coords


def test_nps_fetch_skips_null_names():
    feats = [_arcgis_feature("NULL", name_field="TRLNAME")]
    responses = [_arcgis_response(feats), _arcgis_response([])]
    call_count = [0]

    def handler(r: httpx.Request) -> httpx.Response:
        resp = responses[min(call_count[0], len(responses) - 1)]
        call_count[0] += 1
        return resp

    client = httpx.Client(transport=httpx.MockTransport(handler))
    features = nps_fetch.fetch((38.55, -78.45, 38.70, -78.25), client=client)
    assert features == []


# ── USFS fetch (file-based) ───────────────────────────────────────────────────


def test_usfs_fetch_from_file():
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"TRAIL_NAME": "Jones Run Trail", "TRAIL_NO": "1"},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[-78.30, 38.60], [-78.29, 38.61]],
                },
            }
        ],
    }
    with tempfile.NamedTemporaryFile(suffix=".geojson", mode="w", delete=False) as f:
        json.dump(geojson, f)
        tmp = Path(f.name)

    try:
        features = usfs_fetch.fetch((37.8, -79.4, 39.1, -78.0), geojson_path=tmp)
        assert len(features) == 1
        assert features[0].name == "Jones Run Trail"
        assert features[0].source == "USFS"
    finally:
        tmp.unlink(missing_ok=True)


def test_usfs_fetch_absent_file_returns_empty():
    features = usfs_fetch.fetch(
        (37.8, -79.4, 39.1, -78.0), geojson_path=Path("nonexistent.geojson")
    )
    assert features == []


def test_usfs_fetch_captures_gis_miles():
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "TRAIL_NAME": "Jones Run Trail",
                    "TRAIL_NO": "1",
                    "GIS_MILES": 4.2,
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[-78.30, 38.60], [-78.29, 38.61]],
                },
            }
        ],
    }
    with tempfile.NamedTemporaryFile(suffix=".geojson", mode="w", delete=False) as f:
        json.dump(geojson, f)
        tmp = Path(f.name)

    try:
        features = usfs_fetch.fetch((37.8, -79.4, 39.1, -78.0), geojson_path=tmp)
        assert len(features) == 1
        assert features[0].length_mi == pytest.approx(4.2)
        assert features[0].length_source == "USFS"
    finally:
        tmp.unlink(missing_ok=True)


@pytest.mark.parametrize("bad_value", [None, "", "not-a-number", 0, -1.5])
def test_usfs_fetch_never_fabricates_length_for_unusable_gis_miles(bad_value):
    props = {"TRAIL_NAME": "No Length Trail", "TRAIL_NO": "2"}
    if bad_value is not None:
        props["GIS_MILES"] = bad_value
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": props,
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[-78.30, 38.60], [-78.29, 38.61]],
                },
            }
        ],
    }
    with tempfile.NamedTemporaryFile(suffix=".geojson", mode="w", delete=False) as f:
        json.dump(geojson, f)
        tmp = Path(f.name)

    try:
        features = usfs_fetch.fetch((37.8, -79.4, 39.1, -78.0), geojson_path=tmp)
        assert len(features) == 1
        assert features[0].length_mi is None
        assert features[0].length_source is None
    finally:
        tmp.unlink(missing_ok=True)


def test_usfs_fetch_collapses_multipart_into_one_feature():
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"TRAIL_NAME": "Split Trail", "TRAIL_NO": "9"},
                "geometry": {
                    "type": "MultiLineString",
                    "coordinates": [
                        [[-78.30, 38.60], [-78.29, 38.61]],
                        [[-78.29, 38.61], [-78.28, 38.62]],
                    ],
                },
            }
        ],
    }
    with tempfile.NamedTemporaryFile(suffix=".geojson", mode="w", delete=False) as f:
        json.dump(geojson, f)
        tmp = Path(f.name)

    try:
        features = usfs_fetch.fetch((37.8, -79.4, 39.1, -78.0), geojson_path=tmp)
        assert len(features) == 1
        assert features[0].name == "Split Trail"
    finally:
        tmp.unlink(missing_ok=True)


def test_usfs_fetch_clips_to_bbox():
    # Feature outside the bbox should be excluded
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"TRAIL_NAME": "Far Away Trail"},
                "geometry": {"type": "LineString", "coordinates": [[-100.0, 45.0], [-100.1, 45.1]]},
            }
        ],
    }
    with tempfile.NamedTemporaryFile(suffix=".geojson", mode="w", delete=False) as f:
        json.dump(geojson, f)
        tmp = Path(f.name)

    try:
        features = usfs_fetch.fetch((37.8, -79.4, 39.1, -78.0), geojson_path=tmp)
        assert features == []
    finally:
        tmp.unlink(missing_ok=True)
