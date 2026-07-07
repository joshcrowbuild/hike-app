"""Endpoint + contract test for GET /trail/{canonical_id} (Epic 016 S1 + 017 S4).

Asserts the JSON shape matches the frozen contract EXACTLY (the Lane A↔B coupling),
including the honest `null` cases and the runtime segment-assembly fallback. A fake
GraphClient stands in for Neo4j (no live DB) — the DB round-trip is covered by the
`@pytest.mark.neo4j` integration test.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest
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

# A trail whose precomputed route is corrupt/unparseable but whose segments are good.
_CORRUPT_ROUTE_ROW = {
    "canonical_id": "ct:corrupt",
    "name": "Corrupt Route Trail",
    "route_geom_wkt": "LINESTRING(garbage not wkt",
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

# A trail with profile arrays but NO provenance source (a data-integrity anomaly).
_NO_SOURCE_ROW = {
    "canonical_id": "ct:nosrc",
    "name": "No Source Trail",
    "route_geom_wkt": "LINESTRING(0 0, 1 1)",
    "segment_wkts": ["LINESTRING(0 0, 1 1)"],
    "trail_point": {"latitude": 0.5, "longitude": 0.5},
    "trailhead_point": None,
    "profile_distances_m": [0.0, 100.0],
    "profile_elevations_m": [10.0, 20.0],
    "total_gain_m": 10.0,
    "total_loss_m": 0.0,
    "max_grade_pct": 10.0,
    "elev_source": None,  # missing provenance
    "elev_resolution_m": 20.0,
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

_ROWS = {
    r["canonical_id"]: r
    for r in (_FULL_ROW, _SEGMENTS_ONLY_ROW, _CORRUPT_ROUTE_ROW, _NO_SOURCE_ROW, _BARE_ROW)
}


class _FakeSession:
    def __init__(self, viewer_id: str) -> None:
        self.viewer_id = viewer_id

    def run(self, query: tuple[str, dict[str, Any]]) -> list[dict[str, Any]]:
        _, params = query
        if "cids" in params:  # batched trails_detail (feed)
            return [_ROWS[c] for c in params["cids"] if c in _ROWS]
        row = _ROWS.get(params.get("cid"))  # single trail_detail (detail endpoint)
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
    assert set(body) == {
        "canonical_id",
        "name",
        "geometry",
        "trailhead",
        "geometry_confidence",
        "summit",
        "elevation_profile",
    }

    assert body["geometry"]["type"] == "LineString"
    assert body["geometry"]["coordinates"][0] == [-78.30, 38.55]  # (lon, lat) order
    assert body["geometry_confidence"] == "stated"  # clean single LineString
    # A surveyed trailhead → derived=False (a real trailhead is never marked approximate).
    assert body["trailhead"] == {"lat": 38.5707, "lon": -78.2861, "derived": False}
    assert body["summit"] is None  # no high-point concept yet → null (source-or-silence)

    prof = body["elevation_profile"]
    assert set(prof) == {
        "samples",
        "total_gain_m",
        "total_loss_m",
        "max_grade_pct",
        "source",
        "resolution_m",
        "estimated_duration_min",
    }
    assert prof["samples"][0] == {"distance_m": 0.0, "elevation_m": 600.0}
    # total_gain_m/max_grade_pct are now derived fresh from the samples (not the
    # stored scalars in _FULL_ROW) — 600→680→900 over a 3m noise threshold both
    # register as real climb, so this still lands on 300.0.
    assert prof["total_gain_m"] == 300.0
    assert prof["max_grade_pct"] == pytest.approx(220 / 150 * 100)
    assert prof["source"] == "usgs-3dep"
    assert prof["resolution_m"] == 20.0
    # Grade-aware (Epic 032): this fixture's two segments (0->100m at 80% grade,
    # 100->250m at ~146.7% grade) are pathologically steep synthetic gradients,
    # each well past the ported curve's +15% tabulated endpoint, so both extrapolate
    # to large time factors (~11.3x/~20.3x) with no upper clamp by design (AC-1.4) —
    # real corpus grades stay sub-100% and never reach this regime. Value taken
    # from calling `_estimated_duration_min`, not hand-derived.
    assert prof["estimated_duration_min"] == pytest.approx(50.025)


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
    # No surveyed trailhead → falls back to the trail's geometry point, disclosed as a
    # derived/approximate access point (D7 / Rule #1) rather than posing as a trailhead.
    assert body["trailhead"] == {"lat": 1.0, "lon": 1.0, "derived": True}
    assert body["elevation_profile"] is None  # no profile stored → null, not faked


# ── robustness: a corrupt stored route falls back to assembling the segments ──


def test_corrupt_route_falls_back_to_segment_assembly():
    client = _client()
    try:
        body = client.get("/trail/ct:corrupt").json()
    finally:
        client.__exit__(None, None, None)

    # The unparseable route_geom_wkt must not blank the map; segments assemble instead.
    assert body["geometry"]["type"] == "LineString"
    assert body["geometry"]["coordinates"] == [[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]]


# ── honesty: a stored profile missing its provenance is treated as absent ──────


def test_profile_without_source_is_null_not_mislabeled():
    client = _client()
    try:
        body = client.get("/trail/ct:nosrc").json()
    finally:
        client.__exit__(None, None, None)

    # Provenance is never defaulted/fabricated → no source means no profile (Rule #1).
    assert body["elevation_profile"] is None
    assert body["geometry"] is not None  # geometry still served


# ── honest null geometry (trailhead only) — Rule #1 / D5 ──────────────────────


def test_no_geometry_returns_null_geometry_with_trailhead():
    client = _client()
    try:
        body = client.get("/trail/ct:bare").json()
    finally:
        client.__exit__(None, None, None)

    assert body["geometry"] is None  # route not mapped — never fabricated
    # Trailhead-only trail: the marker is the surveyed trailhead → derived=False.
    assert body["trailhead"] == {"lat": 40.0, "lon": -105.0, "derived": False}
    assert body["elevation_profile"] is None


# ── viewer_id validation (AH4) — invalid shape 422s before reaching Cypher ─────


def test_viewer_id_bad_chars_is_422_never_500():
    client = _client()
    try:
        r = client.get("/trail/ct:has", params={"viewer_id": "josh; DROP TABLE"})
    finally:
        client.__exit__(None, None, None)
    assert r.status_code == 422


def test_viewer_id_too_long_is_422_never_500():
    client = _client()
    try:
        r = client.get("/trail/ct:has", params={"viewer_id": "a" * 65})
    finally:
        client.__exit__(None, None, None)
    assert r.status_code == 422


# ── canonical_id path param bound (AL2) — hygiene, not injection (parameterized) ─


def test_canonical_id_too_long_is_422_never_500():
    client = _client()
    try:
        r = client.get(f"/trail/{'a' * 201}")
    finally:
        client.__exit__(None, None, None)
    assert r.status_code == 422


def test_canonical_id_with_control_char_is_422_never_500():
    client = _client()
    try:
        r = client.get("/trail/ct:has%00evil")
    finally:
        client.__exit__(None, None, None)
    assert r.status_code == 422


# ── 404 for an unknown trail ──────────────────────────────────────────────────


# ── D7: the start marker is honest about surveyed vs derived access points ────


def test_trailhead_marks_surveyed_vs_derived_vs_absent():
    # A surveyed trailhead wins and is NOT flagged derived (regions that tag
    # trailheads — e.g. Shenandoah — are unchanged).
    surveyed = app_mod._trailhead(
        {"trailhead_point": {"latitude": 38.57, "longitude": -78.29}, "trail_point": None}
    )
    assert surveyed is not None
    assert (surveyed.lat, surveyed.lon, surveyed.derived) == (38.57, -78.29, False)

    # No surveyed trailhead → fall back to the trail's geometry point, disclosed as a
    # derived/approximate access point (D7 / Rule #1) — the barrier-island / urban case.
    derived = app_mod._trailhead(
        {"trailhead_point": None, "trail_point": {"latitude": 36.17, "longitude": -75.75}}
    )
    assert derived is not None
    assert (derived.lat, derived.lon, derived.derived) == (36.17, -75.75, True)

    # A surveyed trailhead is preferred even when a trail point also exists.
    both = app_mod._trailhead(
        {
            "trailhead_point": {"latitude": 1.0, "longitude": 2.0},
            "trail_point": {"latitude": 9.0, "longitude": 9.0},
        }
    )
    assert both is not None
    assert (both.lat, both.lon, both.derived) == (1.0, 2.0, False)

    # Neither point → no start marker (never fabricated).
    assert app_mod._trailhead({"trailhead_point": None, "trail_point": None}) is None


def test_feed_card_surfaces_derived_access_point_for_trailless_trail():
    # The D7 end-to-end shape on the feed path: a trail with geometry but no surveyed
    # trailhead still yields a card whose start marker is a disclosed derived point.
    from types import SimpleNamespace

    session = _FakeSession("anonymous")
    maps_by_cid = app_mod._fetch_maps_by_canonical(session, ["ct:segs"])
    card = app_mod._card_response(
        SimpleNamespace(
            canonical_id="ct:segs",
            name="Segment Trail",
            distance_mi=1.1,
            lines=[],
            warnings=[],
            unavailable=[],
        ),
        maps_by_cid["ct:segs"],
    ).model_dump()
    assert card["trailhead"] == {"lat": 1.0, "lon": 1.0, "derived": True}


def test_unknown_trail_returns_404():
    client = _client()
    try:
        r = client.get("/trail/ct:nope")
    finally:
        client.__exit__(None, None, None)
    assert r.status_code == 404


# ── feed cards carry the same maps fields (batched, per card) ─────────────────


def test_feed_card_carries_maps_fields():
    from types import SimpleNamespace

    session = _FakeSession("anonymous")
    maps_by_cid = app_mod._fetch_maps_by_canonical(session, ["ct:has", "ct:bare"])
    assert set(maps_by_cid) == {"ct:has", "ct:bare"}  # batched read returned both

    full = app_mod._card_response(
        SimpleNamespace(
            canonical_id="ct:has",
            name="Old Rag Loop",
            distance_mi=3.2,
            lines=[],
            warnings=[],
            unavailable=[],
        ),
        maps_by_cid["ct:has"],
    ).model_dump()
    assert full["geometry"]["type"] == "LineString"
    assert full["geometry_confidence"] == "stated"
    assert full["trailhead"] == {"lat": 38.5707, "lon": -78.2861, "derived": False}
    assert full["summit"] is None
    assert full["elevation_profile"]["total_gain_m"] == 300.0
    assert full["elevation_profile"]["samples"][0] == {"distance_m": 0.0, "elevation_m": 600.0}
    # See the grade-aware note above — same _FULL_ROW fixture, same recomputed value.
    assert full["elevation_profile"]["estimated_duration_min"] == pytest.approx(50.025)

    # A card with no mapped route degrades honestly — geometry/profile null.
    bare = app_mod._card_response(
        SimpleNamespace(
            canonical_id="ct:bare",
            name="Unmapped",
            distance_mi=None,
            lines=[],
            warnings=[],
            unavailable=[],
        ),
        maps_by_cid["ct:bare"],
    ).model_dump()
    assert bare["geometry"] is None
    assert bare["geometry_confidence"] is None
    assert bare["elevation_profile"] is None
    # trailhead still served; a surveyed trailhead → derived=False.
    assert bare["trailhead"] == {"lat": 40.0, "lon": -105.0, "derived": False}
