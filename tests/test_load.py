"""Tests for graph.load — idempotent MERGE upserts via injected runner."""

from __future__ import annotations

from graph.load import (
    link_area_contains,
    load_area,
    load_canonical_trail,
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
