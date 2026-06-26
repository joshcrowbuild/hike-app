"""Tests for ingestion.route — route assembly + WKT→GeoJSON (Epic 016 S1, AC-1.3).

Pure geometry, no DB: assemble ordered segment lines into one route (LineString
when they join, MultiLineString when they don't) and convert to GeoJSON in
`(lon, lat)` order. Source-or-silence: unparseable input → `None`, never a fake.
"""

from __future__ import annotations

from shapely.geometry import LineString, MultiLineString, Point

from ingestion.route import (
    assemble_geometry,
    assemble_route,
    geometry_to_geojson,
    parse_wkt,
    wkt_to_geojson,
)

# ── parse_wkt: degrade, never raise (Rule #1/#6) ──────────────────────────────


def test_parse_wkt_valid_line():
    g = parse_wkt("LINESTRING(-78.28 38.55, -78.27 38.56)")
    assert g is not None and g.geom_type == "LineString"


def test_parse_wkt_none_and_garbage_return_none():
    assert parse_wkt(None) is None
    assert parse_wkt("") is None
    assert parse_wkt("not wkt at all") is None
    assert parse_wkt("LINESTRING EMPTY") is None


# ── wkt_to_geojson: (lon, lat) order; lines only (AC-1.3) ─────────────────────


def test_wkt_to_geojson_linestring_lon_lat_order():
    gj = wkt_to_geojson("LINESTRING(-78.28 38.55, -78.27 38.56)")
    assert gj == {
        "type": "LineString",
        "coordinates": [[-78.28, 38.55], [-78.27, 38.56]],
    }


def test_wkt_to_geojson_multilinestring():
    gj = wkt_to_geojson("MULTILINESTRING((0 0, 1 1), (5 5, 6 6))")
    assert gj is not None
    assert gj["type"] == "MultiLineString"
    assert gj["coordinates"] == [[[0.0, 0.0], [1.0, 1.0]], [[5.0, 5.0], [6.0, 6.0]]]


def test_wkt_to_geojson_rejects_non_line_and_invalid():
    assert wkt_to_geojson("POINT(1 2)") is None  # not a route line
    assert wkt_to_geojson(None) is None
    assert wkt_to_geojson("garbage") is None


def test_geometry_to_geojson_point_is_none():
    assert geometry_to_geojson(Point(1, 2)) is None
    assert geometry_to_geojson(None) is None


# ── assemble_route: join contiguous segments into one LineString (AC-1.1/1.3) ──


def test_assemble_contiguous_segments_into_one_linestring():
    wkt = assemble_route(["LINESTRING(0 0, 1 1)", "LINESTRING(1 1, 2 2)"])
    g = parse_wkt(wkt)
    assert g is not None and g.geom_type == "LineString"
    assert list(g.coords) == [(0.0, 0.0), (1.0, 1.0), (2.0, 2.0)]


def test_assemble_joins_regardless_of_segment_direction():
    # Second segment runs toward the shared vertex; linemerge still joins them.
    wkt = assemble_route(["LINESTRING(0 0, 1 1)", "LINESTRING(2 2, 1 1)"])
    g = parse_wkt(wkt)
    assert g is not None and g.geom_type == "LineString"
    assert list(g.coords) == [(0.0, 0.0), (1.0, 1.0), (2.0, 2.0)]


def test_assemble_single_segment_is_linestring():
    wkt = assemble_route(["LINESTRING(-78.28 38.55, -78.27 38.56)"])
    g = parse_wkt(wkt)
    assert g is not None and g.geom_type == "LineString"


# ── assemble_route: disconnected segments → ordered MultiLineString ───────────


def test_assemble_disconnected_segments_into_multilinestring():
    wkt = assemble_route(["LINESTRING(0 0, 1 1)", "LINESTRING(5 5, 6 6)"])
    g = parse_wkt(wkt)
    assert g is not None and g.geom_type == "MultiLineString"
    assert len(g.geoms) == 2


def test_assemble_orders_disconnected_parts_west_to_east_deterministically():
    # Input order reversed; assembly must still start at the westernmost endpoint.
    forward = assemble_route(["LINESTRING(0 0, 1 1)", "LINESTRING(5 5, 6 6)"])
    reverse = assemble_route(["LINESTRING(5 5, 6 6)", "LINESTRING(0 0, 1 1)"])
    assert forward == reverse  # deterministic → idempotent ingest
    g = parse_wkt(forward)
    assert list(g.geoms[0].coords)[0] == (0.0, 0.0)  # westernmost part first


# ── source-or-silence: nothing parseable → None (Rule #1) ─────────────────────


def test_assemble_empty_and_all_invalid_returns_none():
    assert assemble_route([]) is None
    assert assemble_route([None, "", "garbage"]) is None


def test_assemble_skips_unparseable_segments_keeps_valid():
    wkt = assemble_route(["garbage", "LINESTRING(0 0, 1 1)", None])
    g = parse_wkt(wkt)
    assert g is not None and g.geom_type == "LineString"


# ── assemble_geometry: collapse a union geometry (spine Feature.geom) ──────────


def test_assemble_geometry_collapses_contiguous_multiline_to_line():
    mls = MultiLineString([[(0, 0), (1, 1)], [(1, 1), (2, 2)]])
    g = assemble_geometry(mls)
    assert g is not None and g.geom_type == "LineString"


def test_assemble_geometry_passes_linestring_through():
    g = assemble_geometry(LineString([(0, 0), (1, 1), (2, 2)]))
    assert g is not None and g.geom_type == "LineString"


def test_assemble_geometry_none_for_empty():
    assert assemble_geometry(None) is None
    assert assemble_geometry(Point(1, 2)) is None  # no line component
