"""Endpoint tests for GET /trail/{canonical_id}/export.gpx (Epic 028 S2).

Fake GraphClient in the `tests/test_trail_detail_endpoint.py` style (no live DB);
the fixtures below reuse that file's row shapes. Asserts: 200 + GPX content-type +
Content-Disposition for a known trail; the D4.3 altitude gate (present/absent);
404 for an unknown trail; 422 for a known trail with no exportable geometry; the
Rule #5 guard (only the world-only `trail_detail` Cypher is issued, no personal
fields); and `_resolve_viewer`'s anonymous posture (world data → anonymous-friendly).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Sequence
from typing import Any

import pytest
from fastapi.testclient import TestClient

import api.app as app_mod
from api.app import app
from orchestration.config import Settings

_GPX_NS = "{http://www.topografix.com/GPX/1/1}"

# A trail with the precomputed route + a stored elevation profile (vertex-aligned,
# unlike real production data — D4.3) + a surveyed trailhead.
_FULL_ROW = {
    "canonical_id": "ct:has",
    "name": "Old Rag Loop",
    "route_geom_wkt": "LINESTRING(-78.30 38.55, -78.29 38.56, -78.28 38.57)",
    "segment_wkts": ["LINESTRING(-78.30 38.55, -78.29 38.56)"],
    "trail_point": {"latitude": 38.55, "longitude": -78.29},
    "trailhead_point": {"latitude": 38.5707, "longitude": -78.2861},
    "profile_distances_m": [0.0, 100.0, 250.0],
    "profile_elevations_m": [600.0, 680.0, 900.0],
    "total_gain_m": 300.0,
    "total_loss_m": 0.0,
    "max_grade_pct": 21.5,
    "elev_source": "usgs-3dep",
    "elev_resolution_m": 20.0,
}

# A trail with NO precomputed route (only segments) and NO elevation profile.
_SEGMENTS_ONLY_ROW = {
    "canonical_id": "ct:segs",
    "name": "Segment Trail",
    "route_geom_wkt": None,
    "segment_wkts": ["LINESTRING(0 0, 1 1)", "LINESTRING(1 1, 2 2)"],
    "trail_point": {"latitude": 1.0, "longitude": 1.0},
    "trailhead_point": None,
    "profile_distances_m": None,
    "profile_elevations_m": None,
    "total_gain_m": None,
    "total_loss_m": None,
    "max_grade_pct": None,
    "elev_source": None,
    "elev_resolution_m": None,
}

# A trail with NO exportable geometry at all (no route, no segments).
_BARE_ROW = {
    "canonical_id": "ct:bare",
    "name": "Unmapped Trail",
    "route_geom_wkt": None,
    "segment_wkts": [],
    "trail_point": None,
    "trailhead_point": {"latitude": 40.0, "longitude": -105.0},
    "profile_distances_m": None,
    "profile_elevations_m": None,
    "total_gain_m": None,
    "total_loss_m": None,
    "max_grade_pct": None,
    "elev_source": None,
    "elev_resolution_m": None,
}

_ROWS = {r["canonical_id"]: r for r in (_FULL_ROW, _SEGMENTS_ONLY_ROW, _BARE_ROW)}


class _FakeSession:
    def __init__(self, viewer_id: str) -> None:
        self.viewer_id = viewer_id
        self.queries: list[str] = []

    def run(self, query: tuple[str, dict[str, Any]]) -> list[dict[str, Any]]:
        cypher, params = query
        self.queries.append(cypher)
        row = _ROWS.get(params.get("cid"))
        return [row] if row is not None else []


class _FakeGraphClient:
    def __init__(self) -> None:
        self.last_session: _FakeSession | None = None

    def scoped_session(self, viewer_id: str, granted_ids: Sequence[str] = ()) -> _FakeSession:
        self.last_session = _FakeSession(viewer_id)
        return self.last_session

    def close(self) -> None:  # pragma: no cover - lifespan shutdown
        pass


def _client() -> tuple[TestClient, _FakeGraphClient]:
    client = TestClient(app)
    client.__enter__()
    app_mod._settings = Settings.from_env({})
    graph_client = _FakeGraphClient()
    app_mod._graph_client = graph_client  # type: ignore[assignment]
    return client, graph_client


def test_known_trail_returns_gpx_with_download_headers():
    client, _ = _client()
    try:
        r = client.get("/trail/ct:has/export.gpx")
    finally:
        client.__exit__(None, None, None)

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/gpx+xml")
    assert r.headers["content-disposition"] == 'attachment; filename="ct-has.gpx"'
    root = ET.fromstring(r.text)
    assert root.tag == f"{_GPX_NS}gpx"


def test_altitude_present_for_vertex_aligned_profile():
    client, _ = _client()
    try:
        r = client.get("/trail/ct:has/export.gpx")
    finally:
        client.__exit__(None, None, None)

    root = ET.fromstring(r.text)
    pts = root.findall(f"{_GPX_NS}trk/{_GPX_NS}trkseg/{_GPX_NS}trkpt")
    assert len(pts) == 3
    assert all(pt.find(f"{_GPX_NS}ele") is not None for pt in pts)
    wpts = root.findall(f"{_GPX_NS}wpt")
    assert len(wpts) == 1
    assert float(wpts[0].get("lat")) == pytest.approx(38.5707)
    assert float(wpts[0].get("lon")) == pytest.approx(-78.2861)


def test_altitude_absent_for_no_elevation_row_expected_not_a_bug():
    client, _ = _client()
    try:
        r = client.get("/trail/ct:segs/export.gpx")
    finally:
        client.__exit__(None, None, None)

    assert r.status_code == 200
    root = ET.fromstring(r.text)
    pts = root.findall(f"{_GPX_NS}trk/{_GPX_NS}trkseg/{_GPX_NS}trkpt")
    assert len(pts) > 0
    assert all(pt.find(f"{_GPX_NS}ele") is None for pt in pts)
    assert root.findall(f"{_GPX_NS}wpt") == []  # no surveyed trailhead


def test_segment_assembly_fallback_produces_a_track():
    client, _ = _client()
    try:
        r = client.get("/trail/ct:segs/export.gpx")
    finally:
        client.__exit__(None, None, None)

    root = ET.fromstring(r.text)
    pts = root.findall(f"{_GPX_NS}trk/{_GPX_NS}trkseg/{_GPX_NS}trkpt")
    coords = [(float(pt.get("lon")), float(pt.get("lat"))) for pt in pts]
    assert coords == [(0.0, 0.0), (1.0, 1.0), (2.0, 2.0)]


def test_unknown_trail_returns_404():
    client, _ = _client()
    try:
        r = client.get("/trail/ct:nope/export.gpx")
    finally:
        client.__exit__(None, None, None)
    assert r.status_code == 404
    assert r.json() == {"detail": "Trail not found"}


def test_known_trail_with_no_geometry_returns_422_never_a_fabricated_track():
    client, _ = _client()
    try:
        r = client.get("/trail/ct:bare/export.gpx")
    finally:
        client.__exit__(None, None, None)
    assert r.status_code == 422
    assert r.json() == {"detail": "Trail has no exportable route geometry"}


def test_reads_only_world_only_trail_detail_cypher_no_personal_fields():
    client, graph_client = _client()
    try:
        client.get("/trail/ct:has/export.gpx")
    finally:
        client.__exit__(None, None, None)

    assert graph_client.last_session is not None
    queries = graph_client.last_session.queries
    assert len(queries) == 1
    cypher = queries[0]
    assert "CanonicalTrail" in cypher
    for personal in ("Episode", "Belief", "owner_id"):
        assert personal not in cypher


def test_anonymous_viewer_served_openly():
    client, _ = _client()
    try:
        r = client.get("/trail/ct:has/export.gpx", params={"viewer_id": "anonymous"})
    finally:
        client.__exit__(None, None, None)
    assert r.status_code == 200


def test_non_anonymous_viewer_without_dev_secret_is_403():
    client, _ = _client()
    try:
        r = client.get("/trail/ct:has/export.gpx", params={"viewer_id": "mem:josh"})
    finally:
        client.__exit__(None, None, None)
    assert r.status_code == 403
