"""Endpoint + contract test for GET /trail/{canonical_id} (Epic 016 S1 + 017 S4).

Asserts the JSON shape matches the frozen contract EXACTLY (the Lane A↔B coupling),
including the honest `null` cases and the runtime segment-assembly fallback. A fake
GraphClient stands in for Neo4j (no live DB) — the DB round-trip is covered by the
`@pytest.mark.neo4j` integration test.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fastapi.testclient import TestClient

import api.app as app_mod
from api.app import app
from orchestration.config import Settings

# A trail with the precomputed route + a stored elevation profile + a trailhead.
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

# A trail with NO geometry at all (trailhead only) and no profile.
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

    def run(self, query: tuple[str, dict[str, Any]]) -> list[dict[str, Any]]:
        _, params = query
        row = _ROWS.get(params.get("cid"))
        return [row] if row is not None else []


class _FakeGraphClient:
    def scoped_session(self, viewer_id: str, granted_ids: Sequence[str] = ()) -> _FakeSession:
        return _FakeSession(viewer_id)

    def close(self) -> None:  # pragma: no cover - lifespan shutdown
        pass


def _client() -> TestClient:
    client = TestClient(app)
    client.__enter__()
    app_mod._settings = Settings.from_env({})
    app_mod._graph_client = _FakeGraphClient()  # type: ignore[assignment]
    return client


# ── full contract shape (the frozen Lane A↔B coupling) ────────────────────────


def test_full_trail_returns_exact_contract_shape():
    client = _client()
    try:
        r = client.get("/trail/ct:has")
    finally:
        client.__exit__(None, None, None)

    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"canonical_id", "name", "geometry", "trailhead", "elevationProfile"}

    assert body["geometry"]["type"] == "LineString"
    assert body["geometry"]["coordinates"][0] == [-78.30, 38.55]  # (lon, lat) order

    assert body["trailhead"] == {"lat": 38.5707, "lon": -78.2861}

    prof = body["elevationProfile"]
    assert set(prof) == {
        "samples",
        "totalGainMeters",
        "totalLossMeters",
        "maxGradePercent",
        "source",
        "resolutionMeters",
    }
    assert prof["samples"][0] == {"distanceMeters": 0.0, "elevationMeters": 600.0}
    assert prof["totalGainMeters"] == 300.0
    assert prof["maxGradePercent"] == 21.5
    assert prof["source"] == "usgs-3dep"
    assert prof["resolutionMeters"] == 20.0


# ── runtime fallback: assemble geometry from segments when no precomputed route ─


def test_segments_only_assembles_geometry_and_nulls_profile():
    client = _client()
    try:
        body = client.get("/trail/ct:segs").json()
    finally:
        client.__exit__(None, None, None)

    # Two contiguous segments assemble into one LineString.
    assert body["geometry"]["type"] == "LineString"
    assert body["geometry"]["coordinates"] == [[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]]
    # No trailhead point → falls back to the trail point.
    assert body["trailhead"] == {"lat": 1.0, "lon": 1.0}
    assert body["elevationProfile"] is None  # no profile stored → null, not faked


# ── honest null geometry (trailhead only) — Rule #1 / D5 ──────────────────────


def test_no_geometry_returns_null_geometry_with_trailhead():
    client = _client()
    try:
        body = client.get("/trail/ct:bare").json()
    finally:
        client.__exit__(None, None, None)

    assert body["geometry"] is None  # route not mapped — never fabricated
    assert body["trailhead"] == {"lat": 40.0, "lon": -105.0}
    assert body["elevationProfile"] is None


# ── 404 for an unknown trail ──────────────────────────────────────────────────


def test_unknown_trail_returns_404():
    client = _client()
    try:
        r = client.get("/trail/ct:nope")
    finally:
        client.__exit__(None, None, None)
    assert r.status_code == 404
