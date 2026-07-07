"""Tests for the OSM water-source overlay (Epic 035): fetch -> load -> read.

Network-free throughout: `httpx.MockTransport` for `fetch_water`, a
list-appender `Runner` for `load_water_source`, pure-function assertions for
`water_sources_near`. No `@pytest.mark.neo4j`, no DB.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

import httpx

from graph.load import load_water_source
from graph.queries import water_sources_near
from ingestion.fetch.osm import WaterSource, fetch_water

# ── Helpers ───────────────────────────────────────────────────────────────────


def _osm_response(elements: list[dict]) -> httpx.Response:
    body = json.dumps({"elements": elements}).encode()
    return httpx.Response(200, content=body, headers={"content-type": "application/json"})


def _water_node(
    osm_id: int, tags: dict[str, str], *, lat: float = 38.55, lon: float = -78.28
) -> dict:
    return {"type": "node", "id": osm_id, "lat": lat, "lon": lon, "tags": tags}


def _fetch_water_via_mirror(response: httpx.Response) -> list[WaterSource]:
    def handler(request: httpx.Request) -> httpx.Response:
        return response

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return fetch_water((38.0, -79.0, 39.0, -78.0), client=client)


# ── S1 — fetch_water ─────────────────────────────────────────────────────────


def test_water_source_field_set_has_no_potability_field():
    field_names = {f.name for f in dataclasses.fields(WaterSource)}
    assert field_names == {"osm_id", "water_type", "name", "lat", "lon", "seasonal"}
    for banned in ("potable", "drinkable", "safe", "drink"):
        assert not any(banned in n.lower() for n in field_names)


def test_fetch_water_named_node():
    node = _water_node(1, {"amenity": "drinking_water", "name": "Piney Spring"})
    sources = _fetch_water_via_mirror(_osm_response([node]))

    assert len(sources) == 1
    assert sources[0] == WaterSource(
        osm_id="node/1",
        water_type="drinking_water",
        name="Piney Spring",
        lat=38.55,
        lon=-78.28,
        seasonal=None,
    )


def test_fetch_water_unnamed_node_has_none_name():
    node = _water_node(2, {"natural": "spring"})
    sources = _fetch_water_via_mirror(_osm_response([node]))

    assert len(sources) == 1
    assert sources[0].name is None


def test_fetch_water_seasonal_node():
    node = _water_node(3, {"natural": "spring", "seasonal": "yes"})
    sources = _fetch_water_via_mirror(_osm_response([node]))

    assert len(sources) == 1
    assert sources[0].seasonal == "yes"


def test_fetch_water_falls_back_to_official_name():
    node = _water_node(4, {"man_made": "water_tap", "official_name": "Backcountry Tap"})
    sources = _fetch_water_via_mirror(_osm_response([node]))

    assert sources[0].name == "Backcountry Tap"


def test_fetch_water_classifies_water_well():
    node = _water_node(5, {"man_made": "water_well"})
    sources = _fetch_water_via_mirror(_osm_response([node]))

    assert sources[0].water_type == "water_well"


def test_fetch_water_priority_spring_beats_water_well():
    """A node tagged both natural=spring and man_made=water_well classifies as
    spring — spring wins (AC-1.3)."""
    node = _water_node(6, {"natural": "spring", "man_made": "water_well"})
    sources = _fetch_water_via_mirror(_osm_response([node]))

    assert len(sources) == 1
    assert sources[0].water_type == "spring"


def test_fetch_water_all_mirrors_fail_returns_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    sources = fetch_water((38.0, -79.0, 39.0, -78.0), client=client)

    assert sources == []


def test_fetch_water_skips_tagless_and_coordless_nodes():
    tagless = {"type": "node", "id": 7, "lat": 38.55, "lon": -78.28, "tags": {}}
    coordless = {"type": "node", "id": 8, "tags": {"amenity": "drinking_water"}}
    good = _water_node(9, {"amenity": "drinking_water"})

    sources = _fetch_water_via_mirror(_osm_response([tagless, coordless, good]))

    assert len(sources) == 1
    assert sources[0].osm_id == "node/9"


# ── S2 — load_water_source ───────────────────────────────────────────────────


def _appender_runner() -> tuple[Any, list[tuple[str, dict]]]:
    calls: list[tuple[str, dict]] = []

    def runner(cypher: str, params: dict) -> None:
        calls.append((cypher, params))

    return runner, calls


def test_load_water_source_emits_merge_with_core_fields():
    runner, calls = _appender_runner()

    load_water_source(
        runner,
        "water:osm:node/9",
        water_type="drinking_water",
        lat=38.55,
        lon=-78.28,
    )

    assert len(calls) == 1
    cypher, params = calls[0]
    assert "MERGE" in cypher
    assert "WaterSource" in cypher
    assert "water_id" in cypher
    assert params["water_type"] == "drinking_water"
    assert params["lat"] == 38.55
    assert params["lon"] == -78.28


def test_load_water_source_is_world_public_no_owner_scope():
    runner, calls = _appender_runner()

    load_water_source(runner, "water:osm:node/9", water_type="spring", lat=38.55, lon=-78.28)

    cypher, params = calls[0]
    assert "owner_id" not in cypher
    assert "$viewer_id" not in cypher
    assert "owner_id" not in params
    assert "viewer_id" not in params


def test_load_water_source_idempotent_merge_key():
    """Calling twice emits MERGE both times on the exact `water:osm:{osm_id}`
    key, so a re-ingest cannot silently orphan prior nodes (AC-2.4)."""
    source = WaterSource(
        osm_id="node/42", water_type="spring", name=None, lat=1.0, lon=2.0, seasonal=None
    )
    water_id = f"water:osm:{source.osm_id}"
    assert water_id == "water:osm:node/42"

    runner, calls = _appender_runner()
    load_water_source(
        runner, water_id, water_type=source.water_type, lat=source.lat, lon=source.lon
    )
    load_water_source(
        runner, water_id, water_type=source.water_type, lat=source.lat, lon=source.lon
    )

    assert len(calls) == 2
    for cypher, params in calls:
        assert "MERGE (w:WaterSource {water_id: $water_id})" in cypher
        assert params["water_id"] == "water:osm:node/42"


def test_load_water_source_optional_fields_only_set_when_present():
    runner, calls = _appender_runner()

    load_water_source(runner, "water:osm:node/1", water_type="spring", lat=1.0, lon=2.0)
    cypher, params = calls[0]
    assert "w.name" not in cypher
    assert "w.seasonal" not in cypher
    assert "name" not in params
    assert "seasonal" not in params

    load_water_source(
        runner,
        "water:osm:node/2",
        water_type="spring",
        lat=1.0,
        lon=2.0,
        name="Piney Spring",
        seasonal="yes",
    )
    cypher, params = calls[1]
    assert "w.name = $name" in cypher
    assert "w.seasonal = $seasonal" in cypher
    assert params["name"] == "Piney Spring"
    assert params["seasonal"] == "yes"


def test_load_water_source_no_potability_property():
    runner, calls = _appender_runner()

    load_water_source(
        runner,
        "water:osm:node/1",
        water_type="drinking_water",
        lat=1.0,
        lon=2.0,
        name="Test",
        seasonal="yes",
    )

    cypher, _ = calls[0]
    lowered = cypher.lower()
    for banned in ("potable", "drinkable", "safe", "drink"):
        assert banned not in lowered, f"found banned substring {banned!r} in Cypher"


# ── S3 — water_sources_near ──────────────────────────────────────────────────


def test_water_sources_near_is_pure_and_matches_shape():
    cypher, params = water_sources_near(38.55, -78.28, 500.0)

    assert "MATCH (w:WaterSource)" in cypher
    assert "point.distance(w.point, point($origin)) <= $radius_m" in cypher
    assert "ORDER BY distance_m ASC" in cypher
    assert "LIMIT $limit" in cypher
    assert params["origin"] == {"latitude": 38.55, "longitude": -78.28}
    assert params["radius_m"] == 500.0
    assert params["limit"] == 50


def test_water_sources_near_custom_limit():
    _, params = water_sources_near(38.55, -78.28, 500.0, limit=10)
    assert params["limit"] == 10


def test_water_sources_near_no_owner_scope():
    cypher, params = water_sources_near(38.55, -78.28, 500.0)

    assert "owner_id" not in cypher
    assert "$viewer_id" not in cypher
    assert "viewer_id" not in params
    assert "granted_ids" not in params


def test_water_sources_near_docstring_states_world_only():
    doc = water_sources_near.__doc__ or ""
    assert "World nodes only" in doc
    assert "no owner scope" in doc


def test_water_sources_near_no_potability_claim():
    cypher, _ = water_sources_near(38.55, -78.28, 500.0)
    lowered = cypher.lower()
    for banned in ("potable", "drinkable", "safe", "drink"):
        assert banned not in lowered, f"found banned substring {banned!r} in Cypher"
