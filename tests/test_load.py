"""Tests for graph.load — idempotent MERGE upserts via injected runner."""

from __future__ import annotations

from graph.load import (
    clear_trail_segments,
    link_area_contains,
    load_area,
    load_canonical_trail,
    load_segment,
    load_source_record,
    load_trailhead,
    merge_same_as,
)


def test_load_area_produces_merge():
    calls: list[tuple[str, dict]] = []
    runner = lambda cypher, params: calls.append((cypher, params))  # noqa: E731

    load_area(runner, "nps:shen", "Shenandoah National Park", manager="NPS", lat=38.49, lon=-78.46)

    assert len(calls) == 1
    cypher, params = calls[0]
    assert "MERGE" in cypher
    assert "Area" in cypher
    assert params["area_id"] == "nps:shen"
    assert params["name"] == "Shenandoah National Park"
    assert params["manager"] == "NPS"


def test_load_canonical_trail():
    calls: list[tuple[str, dict]] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731

    load_canonical_trail(
        runner,
        "ct:old-rag-loop",
        "Old Rag Loop",
        lat=38.5519,
        lon=-78.2861,
        is_loop=True,
        length_mi=9.1,
    )

    assert len(calls) == 1
    _, params = calls[0]
    assert params["cid"] == "ct:old-rag-loop"
    assert params["length_mi"] == 9.1
    assert params["is_loop"] is True
    assert "lat" in params and "lon" in params


def test_load_source_record():
    calls: list[tuple[str, dict]] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731

    load_source_record(
        runner, "OSM:way/123456", "OSM", source_id="way/123456", raw_name="Old Rag Mountain"
    )

    assert len(calls) == 1
    _, params = calls[0]
    assert params["sr_uid"] == "OSM:way/123456"
    assert params["source"] == "OSM"
    assert params["raw_name"] == "Old Rag Mountain"


def test_merge_same_as():
    calls: list[tuple[str, dict]] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731

    merge_same_as(runner, "ct:old-rag-loop", "OSM:way/123456", source="OSM", match_score=0.92)

    assert len(calls) == 1
    cypher, params = calls[0]
    assert "SAME_AS" in cypher
    assert "MERGE" in cypher
    assert params["source"] == "OSM"
    assert params["score"] == 0.92


def test_load_trailhead_with_links():
    calls: list[tuple[str, dict]] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731

    load_trailhead(
        runner,
        "th:old-rag-lot",
        "Old Rag Parking",
        38.5707,
        -78.2861,
        canonical_ids=["ct:old-rag-loop"],
        area_id="nps:shen",
    )

    # Should produce: MERGE trailhead + MERGE access link + MERGE located_in link
    assert len(calls) == 3
    cypher_first = calls[0][0]
    assert "Trailhead" in cypher_first

    cypher_second = calls[1][0]
    assert "ACCESSES" in cypher_second

    cypher_third = calls[2][0]
    assert "LOCATED_IN" in cypher_third


def test_link_area_contains():
    calls: list[tuple[str, dict]] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731

    link_area_contains(runner, "nps:shen", "ct:old-rag-loop")
    assert len(calls) == 1
    cypher, params = calls[0]
    assert "CONTAINS" in cypher
    assert params["area_id"] == "nps:shen"
    assert params["cid"] == "ct:old-rag-loop"


def test_load_segment_merges_node_and_link():
    calls: list[tuple[str, dict]] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731

    load_segment(
        runner, "seg:ct:1:0", "LINESTRING(0 0, 1 1)", canonical_id="ct:1", lat=0.5, lon=0.5
    )

    assert len(calls) == 2
    assert "MERGE (s:Segment" in calls[0][0]
    assert calls[0][1]["geom_wkt"] == "LINESTRING(0 0, 1 1)"
    assert "HAS_SEGMENT" in calls[1][0]
    assert calls[1][1] == {"cid": "ct:1", "sid": "seg:ct:1:0"}


def test_clear_trail_segments_detaches():
    calls: list[tuple[str, dict]] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731

    clear_trail_segments(runner, "ct:1")
    assert len(calls) == 1
    assert "DETACH DELETE" in calls[0][0] and "HAS_SEGMENT" in calls[0][0]
    assert calls[0][1] == {"cid": "ct:1"}


def test_load_canonical_trail_clears_route_geom_when_none_passed():
    # Passing route_geom_wkt=None explicitly SETs it (to null → Neo4j drops it), so a
    # re-ingest that loses geometry clears the stale route rather than serving it.
    calls: list[tuple[str, dict]] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731
    load_canonical_trail(runner, "ct:1", "T", route_geom_wkt=None)
    cypher, params = calls[0]
    assert "t.route_geom_wkt = $route_geom_wkt" in cypher
    assert "route_geom_wkt" in params and params["route_geom_wkt"] is None


def test_load_canonical_trail_omits_route_geom_when_not_passed():
    # Omitting it (the sentinel default) leaves the property untouched for callers
    # that don't manage geometry.
    calls: list[tuple[str, dict]] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731
    load_canonical_trail(runner, "ct:1", "T")
    _, params = calls[0]
    assert "route_geom_wkt" not in params


def test_idempotency_shape():
    """All writes use MERGE — verify at the Cypher-text level."""
    calls: list[tuple[str, dict]] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731

    load_area(runner, "nps:shen", "Shen")
    load_canonical_trail(runner, "ct:trail-1", "Trail One")
    load_source_record(runner, "OSM:way/1", "OSM")
    merge_same_as(runner, "ct:trail-1", "OSM:way/1", source="OSM")

    for cypher, _ in calls:
        assert "MERGE" in cypher, f"Expected MERGE in: {cypher}"
