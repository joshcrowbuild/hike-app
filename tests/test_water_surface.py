"""Epic 041 — the water-overlay read surface on `GET /trail/{canonical_id}`.

Hermetic throughout: a fake session stands in for the graph (the same posture as
`tests/test_elevation_profile_api.py`), so every assertion is on the emitted
query spec and the returned wire shape — no DB, no network.

The load-bearing behaviour under test is the CDP-02 three-way distinction:
  - **sources**       — water within the near radius → an answer
  - **none_nearby**   — the corpus has water mapped around this trail, none near
                        → an answered-empty (still an answer)
  - **silence (None)**— the region was never water-ingested, or the read failed
                        → `water_sources: null`, no claim either way
plus the distance-honesty rule: `water_sources_near` measures from a single
point, so "near the route" is only claimed after API-layer math over the route
vertices (`basis: "route"`); a trail with no drawable route falls back to its
start point (`basis: "start"`).
"""

from __future__ import annotations

from typing import Any

from api.app import (
    WATER_COARSE_LIMIT,
    WATER_COVERAGE_RADIUS_M,
    WATER_MAX_SOURCES,
    WATER_NEAR_RADIUS_M,
    _water_sources,
)
from api.schemas import TrailWaterResponse, TripDetailResponse, WaterSourceResponse

# ── Fixtures ──────────────────────────────────────────────────────────────────

# A short two-vertex route near Front Royal; midpoint vertex is the second one.
_ROUTE_ROW: dict[str, Any] = {
    "canonical_id": "ct:osm:test-loop",
    "name": "Test Loop",
    "route_geom_wkt": "LINESTRING (-78.4 38.5, -78.39 38.51)",
    "segment_wkts": [],
    "trail_point": {"latitude": 38.505, "longitude": -78.395},
    "trailhead_point": {"latitude": 38.5, "longitude": -78.4},
}

# No drawable route at all — the start-point fallback path.
_POINT_ONLY_ROW: dict[str, Any] = {
    "canonical_id": "ct:osm:unmapped",
    "name": "Unmapped",
    "route_geom_wkt": None,
    "segment_wkts": [],
    "trail_point": None,
    "trailhead_point": {"latitude": 38.5, "longitude": -78.4},
}


def _water_row(
    water_id: str,
    lat: float,
    lon: float,
    *,
    water_type: str = "spring",
    name: str | None = None,
    seasonal: str | None = None,
    distance_m: float = 0.0,
) -> dict[str, Any]:
    return {
        "water_id": water_id,
        "water_type": water_type,
        "name": name,
        "point": {"latitude": lat, "longitude": lon},
        "seasonal": seasonal,
        "source": "OSM",
        "distance_m": distance_m,
    }


class _FakeSession:
    """Records the (cypher, params) spec it is handed; returns canned rows."""

    def __init__(self, rows: list[dict[str, Any]] | Exception) -> None:
        self._rows = rows
        self.specs: list[tuple[str, dict[str, Any]]] = []

    def run(self, query: tuple[str, dict[str, Any]]) -> list[dict[str, Any]]:
        self.specs.append(query)
        if isinstance(self._rows, Exception):
            raise self._rows
        return self._rows


# ── The three-way silence distinction (binding decision 2) ────────────────────


def test_sources_near_the_route_return_an_answer() -> None:
    # ~11 m and ~44 m off the first route vertex; the far one proves coverage.
    session = _FakeSession(
        [
            _water_row("water:osm:node/2", 38.5004, -78.4, water_type="water_tap"),
            _water_row("water:osm:node/1", 38.5001, -78.4, name="Furnace Spring", seasonal="yes"),
            _water_row("water:osm:node/9", 38.7, -78.6),  # ~25 km — coverage only
        ]
    )
    out = _water_sources(session, _ROUTE_ROW)

    assert out is not None
    assert out.state == "sources"
    assert out.basis == "route"
    assert out.radius_m == WATER_NEAR_RADIUS_M
    assert out.source == "OSM"
    assert [w.water_id for w in out.sources] == ["water:osm:node/1", "water:osm:node/2"]
    assert all(w.distance_m <= WATER_NEAR_RADIUS_M for w in out.sources)
    spring = out.sources[0]
    assert spring.water_type == "spring"
    assert spring.name == "Furnace Spring"
    assert spring.seasonal == "yes"
    assert spring.lat == 38.5001 and spring.lon == -78.4


def test_answered_empty_when_the_region_is_covered_but_nothing_is_near() -> None:
    session = _FakeSession([_water_row("water:osm:node/9", 38.7, -78.6)])
    out = _water_sources(session, _ROUTE_ROW)

    assert out is not None
    assert out.state == "none_nearby"
    assert out.sources == []
    assert out.source == "OSM"  # the answered-empty still names its basis


def test_silence_when_the_region_has_no_water_data() -> None:
    # An empty coarse read means the corpus was never water-ingested here —
    # that is NOT an answered-empty; it must be silence (None on the wire).
    session = _FakeSession([])
    assert _water_sources(session, _ROUTE_ROW) is None


def test_read_failure_degrades_to_silence_never_a_500() -> None:
    session = _FakeSession(RuntimeError("bolt down"))
    assert _water_sources(session, _ROUTE_ROW) is None


# ── Distance honesty (binding decision 1) ─────────────────────────────────────


def test_route_basis_uses_min_distance_to_route_vertices_not_the_anchor() -> None:
    # Near the route START but ~1.4 km from the midpoint anchor the coarse
    # query measures from: the per-source distance must be the route-vertex
    # minimum (~11 m), never the anchor distance.
    session = _FakeSession([_water_row("water:osm:node/1", 38.5001, -78.4)])
    out = _water_sources(session, _ROUTE_ROW)

    assert out is not None and out.state == "sources"
    assert out.sources[0].distance_m < 50.0


def test_start_basis_fallback_when_no_route_is_drawable() -> None:
    session = _FakeSession([_water_row("water:osm:node/1", 38.5001, -78.4, distance_m=11.1)])
    out = _water_sources(session, _POINT_ONLY_ROW)

    assert out is not None
    assert out.basis == "start"
    assert out.sources[0].distance_m == 11.1  # the graph's own point distance


def test_no_anchor_at_all_is_silence_and_never_queries() -> None:
    row = {**_POINT_ONLY_ROW, "trailhead_point": None, "trail_point": None}
    session = _FakeSession([_water_row("water:osm:node/1", 38.5, -78.4)])
    assert _water_sources(session, row) is None
    assert session.specs == []  # no anchor → no query, not a fabricated origin


def test_coarse_query_is_coverage_scale_from_the_route_midpoint() -> None:
    session = _FakeSession([])
    _water_sources(session, _ROUTE_ROW)

    assert len(session.specs) == 1
    cypher, params = session.specs[0]
    assert "WaterSource" in cypher
    assert params["radius_m"] == WATER_COVERAGE_RADIUS_M
    assert params["limit"] == WATER_COARSE_LIMIT
    # Anchor = the route's midpoint vertex (the 2-vertex line's second point).
    assert params["origin"] == {"latitude": 38.51, "longitude": -78.39}


def test_answer_is_sorted_nearest_first_and_capped() -> None:
    rows = [_water_row(f"water:osm:node/{i}", 38.5 + i * 0.00001, -78.4) for i in range(20)]
    session = _FakeSession(list(reversed(rows)))
    out = _water_sources(session, _ROUTE_ROW)

    assert out is not None and out.state == "sources"
    assert len(out.sources) == WATER_MAX_SOURCES
    dists = [w.distance_m for w in out.sources]
    assert dists == sorted(dists)


def test_row_with_unusable_point_is_skipped_not_raised_on() -> None:
    session = _FakeSession(
        [
            {"water_id": "water:osm:node/7", "water_type": "spring", "point": None},
            _water_row("water:osm:node/1", 38.5001, -78.4),
        ]
    )
    out = _water_sources(session, _ROUTE_ROW)
    assert out is not None
    assert [w.water_id for w in out.sources] == ["water:osm:node/1"]


# ── Wire shape + the Rule #1 guard ────────────────────────────────────────────


def test_trip_detail_response_defaults_water_to_null_silence() -> None:
    resp = TripDetailResponse(canonical_id="ct:osm:x", name="X")
    assert resp.water_sources is None
    assert "water_sources" in TripDetailResponse.model_fields


def test_no_potability_claim_in_the_new_schema_field_names() -> None:
    # Epic 035 Guard 2, carried to the wire layer: field NAMES must never carry
    # a potability token. (`drinking_water` is a legitimate OSM category VALUE
    # and lives in data, not in a field name.)
    names = set(WaterSourceResponse.model_fields) | set(TrailWaterResponse.model_fields)
    for banned in ("potable", "drinkable", "safe", "drink"):
        assert not any(banned in n.lower() for n in names), f"{banned!r} leaked into {names}"


def test_water_types_pass_through_verbatim_never_reworded() -> None:
    session = _FakeSession(
        [
            _water_row("water:osm:node/1", 38.5001, -78.4, water_type="drinking_water"),
            _water_row("water:osm:node/2", 38.5002, -78.4, water_type="water_well"),
        ]
    )
    out = _water_sources(session, _ROUTE_ROW)
    assert out is not None
    assert {w.water_type for w in out.sources} == {"drinking_water", "water_well"}
