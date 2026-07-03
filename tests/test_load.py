"""Tests for graph.load — idempotent MERGE upserts via injected runner."""

from __future__ import annotations

from typing import Any

import pytest

from graph.load import (
    clear_trail_segments,
    link_area_contains,
    load_area,
    load_canonical_trail,
    load_segment,
    load_source_record,
    load_trailhead,
    merge_same_as,
    prune_stale_trails,
)


def _make_prune_runner(n_cur: int, n_prev: int) -> tuple[Any, list[tuple[str, dict]]]:
    """A fake `Runner` for `prune_stale_trails`: answers its two count queries with
    canned scalars (the `list[dict]` shape — see `_scalar_count`'s docstring) and
    records every other (write) call it's given, so a test can assert on exactly what
    would have hit the database."""
    write_calls: list[tuple[str, dict]] = []

    def runner(cypher: str, params: dict) -> Any:
        if "RETURN count(cur)" in cypher:
            return [{"n": n_cur}]
        if "RETURN count(node)" in cypher:
            return [{"n": n_prev}]
        write_calls.append((cypher, params))
        return None

    return runner, write_calls


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
    assert "way_type" not in params  # same sentinel discipline as route geometry


def test_load_canonical_trail_sets_and_clears_way_type():
    # way_type follows the route-geom sentinel pattern: a value SETs it, an explicit
    # None SETs null (clears a stale type on re-ingest), and omission leaves it alone.
    calls: list[tuple[str, dict]] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731

    load_canonical_trail(runner, "ct:1", "T", way_type="track")
    cypher, params = calls[-1]
    assert "t.way_type = $way_type" in cypher
    assert params["way_type"] == "track"

    load_canonical_trail(runner, "ct:1", "T", way_type=None)
    _, params = calls[-1]
    assert "way_type" in params and params["way_type"] is None


def test_prune_stale_trails_query_shape():
    # Healthy re-ingest: current count (1400) is well within ratio of the prior
    # count (1500), so both guards clear and the two delete passes fire.
    runner, calls = _make_prune_runner(n_cur=1400, n_prev=1500)

    outcome = prune_stale_trails(runner, "shenandoah-gwj-v11", region_id="shenandoah-gwj")

    assert outcome.pruned is True
    # Two passes: stale trails+segments, then orphaned SourceRecords.
    assert len(calls) == 2
    trail_cypher, params = calls[0]
    sr_cypher, _ = calls[1]

    # Both passes carry the (unchanged) empty-ingest guard + separator-anchored scope.
    for cypher in (trail_cypher, sr_cypher):
        assert "count(cur)" in cypher and "n_cur >= $min_current" in cypher
        assert "DETACH DELETE" in cypher
        # Region scope is separator-anchored (no bare STARTS WITH region_id).
        assert (
            "node.ingest_version = $region_id OR node.ingest_version STARTS WITH $prefix" in cypher
        )
        assert "node.ingest_version <> $iv" in cypher

    # Pass 1 removes the trail + its private segments, EXCEPT owned-referenced ones:
    # the only owned label it may name is `:Episode`, and only in the protective NOT
    # guard (never as a DELETE target) — the owned-ref safety that fixes the severed
    # personal→world reference (viewer-path 500).
    assert "CanonicalTrail" in trail_cypher and "HAS_SEGMENT" in trail_cypher
    assert "AND NOT (node)<-[:ON]-(:Episode)" in trail_cypher
    for personal_label in ("Belief", "Outcome", "Person", "PhysicalProfile"):
        assert personal_label not in trail_cypher

    # Pass 2 deletes only SourceRecords with no surviving SAME_AS to a trail, and never
    # names any owned/personal label (rule #4).
    assert "SourceRecord" in sr_cypher
    assert "NOT (node)-[:SAME_AS]->(:CanonicalTrail)" in sr_cypher
    for personal_label in ("Episode", "Belief", "Outcome", "Person", "PhysicalProfile"):
        assert personal_label not in sr_cypher

    assert params["iv"] == "shenandoah-gwj-v11"
    assert params["region_id"] == "shenandoah-gwj"
    assert params["prefix"] == "shenandoah-gwj-"
    assert params["min_current"] == 1


def test_prune_reports_owned_ref_protected_count():
    # Owned-ref safety (2c): stale trails a live Episode still references are counted
    # into PruneOutcome.protected and excluded from the delete. A runner that answers the
    # protected-count query (the Episode-guarded one) with 2.
    def runner(cypher: str, params: dict) -> Any:
        if "RETURN count(cur)" in cypher:
            return [{"n": 100}]
        if "(node)<-[:ON]-(:Episode)" in cypher:  # the owned-ref protected count query
            return [{"n": 2}]
        if "RETURN count(node)" in cypher:
            return [{"n": 100}]
        return None  # the two DETACH DELETE passes

    outcome = prune_stale_trails(runner, "r-v2", region_id="r")
    assert outcome.pruned is True
    assert outcome.protected == 2


def test_count_region_versions_returns_cur_and_prev():
    from graph.load import count_region_versions

    def runner(cypher: str, params: dict) -> Any:
        if "RETURN count(cur)" in cypher:
            return [{"n": 42}]
        if "RETURN count(node)" in cypher:
            return [{"n": 99}]
        return None

    assert count_region_versions(runner, "r-v2", region_id="r") == (42, 99)


def test_prune_stale_trails_prefix_is_separator_anchored():
    # The prefix param must end on the '-' boundary so region "shen" can't prune
    # region "shenandoah-gwj" (cross-region wipe guard).
    runner, calls = _make_prune_runner(n_cur=100, n_prev=100)
    outcome = prune_stale_trails(runner, "shen-v3", region_id="shen")
    assert outcome.pruned is True
    assert calls[0][1]["prefix"] == "shen-"


def test_prune_stale_trails_respects_min_current_override():
    runner, calls = _make_prune_runner(n_cur=100, n_prev=100)

    outcome = prune_stale_trails(
        runner, "shenandoah-gwj", region_id="shenandoah-gwj", min_current=50
    )
    assert outcome.pruned is True
    assert calls[0][1]["min_current"] == 50


def test_prune_stale_trails_truncated_ingest_aborts_via_ratio_guard():
    # Finding M1: Overpass times out and the run loads 1 of ~1500 trails. n_cur=1
    # clears the old min_current=1 belt, so without the ratio guard this would
    # DETACH DELETE the other 1499 as "stale". The ratio guard must abort instead.
    runner, calls = _make_prune_runner(n_cur=1, n_prev=1500)

    outcome = prune_stale_trails(runner, "shenandoah-gwj-v12", region_id="shenandoah-gwj")

    assert outcome.pruned is False
    assert outcome.n_cur == 1 and outcome.n_prev == 1500
    assert outcome.reason is not None
    assert "prune skipped: count dropped 1500->1" in outcome.reason
    # Nothing hit the database — no DETACH DELETE fired at all.
    assert calls == []


def test_prune_stale_trails_healthy_reingest_prunes_normally():
    # A normal monthly re-run: counts move a little (1500 -> 1490) but stay well
    # within the default 0.5 ratio. Pruning must proceed exactly as before.
    runner, calls = _make_prune_runner(n_cur=1490, n_prev=1500)

    outcome = prune_stale_trails(runner, "shenandoah-gwj-v12", region_id="shenandoah-gwj")

    assert outcome.pruned is True
    assert outcome.n_cur == 1490 and outcome.n_prev == 1500
    assert outcome.reason is None
    assert len(calls) == 2
    assert all("DETACH DELETE" in cypher for cypher, _ in calls)


def test_prune_stale_trails_empty_ingest_still_noops():
    # The original empty-ingest guard (min_current) must still fire — before the
    # ratio guard is even consulted — and still block prune entirely.
    runner, calls = _make_prune_runner(n_cur=0, n_prev=1500)

    outcome = prune_stale_trails(runner, "shenandoah-gwj-v12", region_id="shenandoah-gwj")

    assert outcome.pruned is False
    assert "below min_current" in outcome.reason
    assert calls == []


def test_prune_stale_trails_ratio_guard_skipped_on_first_ever_ingest():
    # n_prev == 0 means nothing stale exists yet (first ingest of a region) — the
    # ratio guard has no denominator and must not block a legitimate first prune.
    runner, calls = _make_prune_runner(n_cur=3, n_prev=0)

    outcome = prune_stale_trails(runner, "new-region-v1", region_id="new-region")

    assert outcome.pruned is True
    assert len(calls) == 2


def test_prune_stale_trails_ratio_is_env_configurable(monkeypatch: pytest.MonkeyPatch):
    # 200/1500 = 0.133, below the default 0.5 ratio (would abort) but above a
    # relaxed 0.1 ratio set via ADVENTURE_PRUNE_MIN_RATIO (should prune).
    runner, calls = _make_prune_runner(n_cur=200, n_prev=1500)
    default_outcome = prune_stale_trails(runner, "r-v2", region_id="r")
    assert default_outcome.pruned is False

    runner2, calls2 = _make_prune_runner(n_cur=200, n_prev=1500)
    monkeypatch.setenv("ADVENTURE_PRUNE_MIN_RATIO", "0.1")
    relaxed_outcome = prune_stale_trails(runner2, "r-v2", region_id="r")
    assert relaxed_outcome.pruned is True
    assert len(calls2) == 2
    assert calls == []  # the first (default-ratio) call never wrote anything


def test_prune_stale_trails_min_ratio_kwarg_overrides_env(monkeypatch: pytest.MonkeyPatch):
    # An explicit min_ratio= argument wins over the env var.
    monkeypatch.setenv("ADVENTURE_PRUNE_MIN_RATIO", "0.9")  # would abort at 200/1500
    runner, calls = _make_prune_runner(n_cur=200, n_prev=1500)

    outcome = prune_stale_trails(runner, "r-v2", region_id="r", min_ratio=0.1)

    assert outcome.pruned is True
    assert len(calls) == 2


def test_prune_stale_trails_bad_env_ratio_falls_back_to_safe_default(
    monkeypatch: pytest.MonkeyPatch,
):
    # An unparseable override must fail SAFE (fall back to the blocking-capable
    # default), never fail open (e.g. to 0, which would disable the guard).
    monkeypatch.setenv("ADVENTURE_PRUNE_MIN_RATIO", "not-a-number")
    runner, calls = _make_prune_runner(n_cur=1, n_prev=1500)

    outcome = prune_stale_trails(runner, "r-v2", region_id="r")

    assert outcome.pruned is False
    assert calls == []


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
