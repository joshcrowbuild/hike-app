"""Tests for graph.load — idempotent MERGE upserts via injected runner."""

from __future__ import annotations

from typing import Any

import pytest

from graph.load import (
    clear_trail_segments,
    count_region_facets,
    count_version_facets,
    load_area,
    load_canonical_trail,
    load_segment,
    load_source_record,
    load_trailhead,
    merge_same_as,
    new_ingest_run_id,
    prune_stale_trails,
)


def _make_prune_runner(
    n_cur: int, n_prev: int, *, deleted: int | None = None
) -> tuple[Any, list[tuple[str, dict]]]:
    """A fake `Runner` for `prune_stale_trails`: answers its count queries with canned
    scalars (the `list[dict]` shape — see `_scalar_count`'s docstring) and records
    every other (write) call it's given, so a test can assert on exactly what would
    have hit the database. Pass 1's DETACH DELETE now also returns a scalar (the true
    deleted-node count — `RETURN count(DISTINCT node) AS n`); it defaults to `n_prev`
    (every stale-candidate got deleted, the common case in these fixtures) but a test
    can pass `deleted=` to pin a smaller count (e.g. some candidates were protected)."""
    write_calls: list[tuple[str, dict]] = []
    deleted_n = n_prev if deleted is None else deleted

    def runner(cypher: str, params: dict) -> Any:
        if "RETURN count(cur)" in cypher:
            return [{"n": n_cur}]
        if "count(DISTINCT node)" in cypher:
            write_calls.append((cypher, params))
            return [{"n": deleted_n}]
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


def test_load_canonical_trail_sets_and_clears_outside_boundary():
    # The Phase-2 spatial flag follows the same sentinel pattern: True/False SETs it,
    # an explicit None SETs null (clears a stale flag on re-ingest), omission leaves it.
    calls: list[tuple[str, dict]] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731

    load_canonical_trail(runner, "ct:1", "T", outside_boundary=True)
    cypher, params = calls[-1]
    assert "t.outside_boundary = $outside_boundary" in cypher
    assert params["outside_boundary"] is True

    load_canonical_trail(runner, "ct:1", "T", outside_boundary=None)
    _, params = calls[-1]
    assert "outside_boundary" in params and params["outside_boundary"] is None

    load_canonical_trail(runner, "ct:1", "T")
    _, params = calls[-1]
    assert "outside_boundary" not in params  # omitted → property untouched


def test_load_canonical_trail_sets_and_clears_length_mi():
    # length_mi follows the same sentinel pattern as route_geom_wkt/way_type/
    # outside_boundary: a value SETs it (with its source), an explicit None SETs null
    # (clears a stale length when a re-ingest's geometry no longer yields one — Rule
    # #1), and omission leaves a prior ingest_version's value untouched.
    calls: list[tuple[str, dict]] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731

    load_canonical_trail(runner, "ct:1", "T", length_mi=9.1, length_source="geom-haversine")
    cypher, params = calls[-1]
    assert "t.length_mi = $length_mi" in cypher
    assert params["length_mi"] == 9.1
    assert params["length_source"] == "geom-haversine"

    load_canonical_trail(runner, "ct:1", "T", length_mi=None)
    _, params = calls[-1]
    assert "length_mi" in params and params["length_mi"] is None
    assert params["length_source"] == ""

    load_canonical_trail(runner, "ct:1", "T")
    _, params = calls[-1]
    assert "length_mi" not in params  # omitted → property untouched


def test_load_canonical_trail_sets_and_clears_path_grade():
    # path_grade follows the same sentinel pattern (Epic 026 AC-3.2): a value SETs
    # it, an explicit None SETs null (clears a stale grade on re-ingest), omission
    # leaves it alone.
    calls: list[tuple[str, dict]] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731

    load_canonical_trail(runner, "ct:1", "T", path_grade="expert")
    cypher, params = calls[-1]
    assert "t.path_grade = $path_grade" in cypher
    assert params["path_grade"] == "expert"

    load_canonical_trail(runner, "ct:1", "T", path_grade=None)
    _, params = calls[-1]
    assert "path_grade" in params and params["path_grade"] is None

    load_canonical_trail(runner, "ct:1", "T")
    _, params = calls[-1]
    assert "path_grade" not in params  # omitted → property untouched


def test_load_canonical_trail_sets_and_clears_psurface():
    calls: list[tuple[str, dict]] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731

    load_canonical_trail(runner, "ct:1", "T", psurface="paved_good")
    cypher, params = calls[-1]
    assert "t.psurface = $psurface" in cypher
    assert params["psurface"] == "paved_good"

    load_canonical_trail(runner, "ct:1", "T", psurface=None)
    _, params = calls[-1]
    assert "psurface" in params and params["psurface"] is None

    load_canonical_trail(runner, "ct:1", "T")
    _, params = calls[-1]
    assert "psurface" not in params


def test_load_canonical_trail_sets_and_clears_foot_access():
    calls: list[tuple[str, dict]] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731

    load_canonical_trail(runner, "ct:1", "T", foot_access="no")
    cypher, params = calls[-1]
    assert "t.foot_access = $foot_access" in cypher
    assert params["foot_access"] == "no"

    load_canonical_trail(runner, "ct:1", "T", foot_access=None)
    _, params = calls[-1]
    assert "foot_access" in params and params["foot_access"] is None

    load_canonical_trail(runner, "ct:1", "T")
    _, params = calls[-1]
    assert "foot_access" not in params


def test_prune_stale_trails_query_shape():
    # Healthy re-ingest: current count (1400) is well within ratio of the prior corpus
    # total (1500), so both guards clear and the two delete passes fire.
    runner, calls = _make_prune_runner(n_cur=1400, n_prev=1500)

    outcome = prune_stale_trails(
        runner, "shenandoah-gwj-v11", region_id="shenandoah-gwj", pre_load_count=1500
    )

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
        if "count(DISTINCT node)" in cypher:  # pass 1's DETACH DELETE, true deleted count
            return [{"n": 98}]
        if "(node)<-[:ON]-(:Episode)" in cypher:  # the owned-ref protected count query
            return [{"n": 2}]
        if "RETURN count(node)" in cypher:
            return [{"n": 100}]
        return None  # pass 2's DETACH DELETE (SourceRecords)

    outcome = prune_stale_trails(runner, "r-v2", region_id="r")
    assert outcome.pruned is True
    assert outcome.protected == 2
    assert outcome.deleted == 98


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
    # DETACH DELETE the other 1499 as "stale". The ratio guard — comparing against the
    # PRE-LOAD corpus total (1500), not the post-load n_prev — must abort instead.
    runner, calls = _make_prune_runner(n_cur=1, n_prev=1499)

    outcome = prune_stale_trails(
        runner, "shenandoah-gwj-v12", region_id="shenandoah-gwj", pre_load_count=1500
    )

    assert outcome.pruned is False
    assert outcome.n_cur == 1 and outcome.n_prev == 1499
    assert outcome.reason is not None
    assert "is below 50% of the prior corpus total 1500" in outcome.reason
    # Nothing hit the database — no DETACH DELETE fired at all.
    assert calls == []


def test_prune_stale_trails_half_partial_aborts_against_pre_load_total():
    # The collapse-gate correction: a 50% partial makes n_cur == n_prev (complementary
    # halves of one total). The OLD formula `n_cur < 0.5*n_prev` (750 < 375) would PASS
    # and prune the 750 stragglers — a silent half-wipe. Comparing against the pre-load
    # total (750 < 0.5*1500 = 750 is a boundary; a genuine truncation lands below it):
    # here 700 refreshed of a prior 1500 → 700 < 750 → abort.
    runner, calls = _make_prune_runner(n_cur=700, n_prev=800)

    outcome = prune_stale_trails(
        runner, "shenandoah-gwj-v12", region_id="shenandoah-gwj", pre_load_count=1500
    )

    assert outcome.pruned is False
    assert calls == []


def test_prune_stale_trails_ratio_guard_skipped_without_pre_load_count():
    # Belt-and-suspenders: guard 2 needs the caller's pre-load snapshot (post-load counts
    # can't recover the prior total). With pre_load_count omitted it is skipped — the
    # pipeline's verify_before_prune gate is the primary protection — so a lone guard-1
    # pass proceeds to prune. (The pipeline always supplies pre_load_count.)
    runner, calls = _make_prune_runner(n_cur=1, n_prev=1499)

    outcome = prune_stale_trails(runner, "shenandoah-gwj-v12", region_id="shenandoah-gwj")

    assert outcome.pruned is True
    assert len(calls) == 2


def test_prune_stale_trails_healthy_reingest_prunes_normally():
    # A normal monthly re-run: counts move a little (1500 -> 1490) but stay well
    # within the default 0.5 ratio of the prior total. Pruning must proceed as before.
    runner, calls = _make_prune_runner(n_cur=1490, n_prev=10)

    outcome = prune_stale_trails(
        runner, "shenandoah-gwj-v12", region_id="shenandoah-gwj", pre_load_count=1500
    )

    assert outcome.pruned is True
    assert outcome.n_cur == 1490 and outcome.n_prev == 10
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
    # pre_load_count == 0 means nothing existed before this run (first ingest of a
    # region) — the ratio guard has no denominator and must not block a first prune.
    runner, calls = _make_prune_runner(n_cur=3, n_prev=0)

    outcome = prune_stale_trails(runner, "new-region-v1", region_id="new-region", pre_load_count=0)

    assert outcome.pruned is True
    assert len(calls) == 2


def test_prune_stale_trails_ratio_is_env_configurable(monkeypatch: pytest.MonkeyPatch):
    # 200/1500 = 0.133, below the default 0.5 ratio (would abort) but above a
    # relaxed 0.1 ratio set via ADVENTURE_PRUNE_MIN_RATIO (should prune).
    runner, calls = _make_prune_runner(n_cur=200, n_prev=1300)
    default_outcome = prune_stale_trails(runner, "r-v2", region_id="r", pre_load_count=1500)
    assert default_outcome.pruned is False

    runner2, calls2 = _make_prune_runner(n_cur=200, n_prev=1300)
    monkeypatch.setenv("ADVENTURE_PRUNE_MIN_RATIO", "0.1")
    relaxed_outcome = prune_stale_trails(runner2, "r-v2", region_id="r", pre_load_count=1500)
    assert relaxed_outcome.pruned is True
    assert len(calls2) == 2
    assert calls == []  # the first (default-ratio) call never wrote anything


def test_prune_stale_trails_min_ratio_kwarg_overrides_env(monkeypatch: pytest.MonkeyPatch):
    # An explicit min_ratio= argument wins over the env var.
    monkeypatch.setenv("ADVENTURE_PRUNE_MIN_RATIO", "0.9")  # would abort at 200/1500
    runner, calls = _make_prune_runner(n_cur=200, n_prev=1300)

    outcome = prune_stale_trails(runner, "r-v2", region_id="r", min_ratio=0.1, pre_load_count=1500)

    assert outcome.pruned is True
    assert len(calls) == 2


def test_prune_stale_trails_bad_env_ratio_falls_back_to_safe_default(
    monkeypatch: pytest.MonkeyPatch,
):
    # An unparseable override must fail SAFE (fall back to the blocking-capable
    # default), never fail open (e.g. to 0, which would disable the guard).
    monkeypatch.setenv("ADVENTURE_PRUNE_MIN_RATIO", "not-a-number")
    runner, calls = _make_prune_runner(n_cur=1, n_prev=1499)

    outcome = prune_stale_trails(runner, "r-v2", region_id="r", pre_load_count=1500)

    assert outcome.pruned is False
    assert calls == []


# ── Filter-drift prune: the per-run marker (`ingest_run_id`) ───────────────────────
#
# The structural gap (twice-bitten, the "prune-doesn't-self-heal-constant-iv" gotcha):
# `ingest_version` for a region is a CONSTANT string (no region geojson sets the optional
# suffix), so a node a *tightened* filter newly excludes is simply never re-written — its
# `ingest_version` still equals the current one, the version-keyed stale predicate
# (`ingest_version <> $iv`) matches nothing (`verify_n_prev: 0` on every region, every
# run), and the junk node lives forever. The fix keys the prune on a per-run marker
# instead: every node the run touches is stamped `ingest_run_id`, and "not stamped by
# this run" = stale candidate. These tests falsify the OLD mechanism (a constant-iv
# node untouched by the run MUST be a candidate) and pin the preserved safety
# semantics (ratio guard, min_current, owned-ref skip, anchored region scope).


def test_new_ingest_run_id_embeds_version_and_is_unique():
    a = new_ingest_run_id("shenandoah-gwj")
    b = new_ingest_run_id("shenandoah-gwj")
    # Embeds the ingest_version for human debuggability ("which region/run stamped
    # this node?"), separated by a char that can't appear in a region id.
    assert a.startswith("shenandoah-gwj@")
    assert b.startswith("shenandoah-gwj@")
    # Unique per call — a constant marker is the exact bug this mechanism replaces.
    assert a != b


def test_load_canonical_trail_stamps_ingest_run_id():
    calls: list[tuple[str, dict]] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731

    load_canonical_trail(
        runner, "ct:x", "X", ingest_version="r", ingest_run_id="r@20260713T000000Z-abc"
    )

    cypher, params = calls[0]
    assert "t.ingest_run_id = $run_id" in cypher
    assert params["run_id"] == "r@20260713T000000Z-abc"

    # Omitting the arg leaves the property untouched (no clause, no param) — legacy
    # callers keep writing exactly what they wrote before.
    calls.clear()
    load_canonical_trail(runner, "ct:x", "X", ingest_version="r")
    cypher, params = calls[0]
    assert "ingest_run_id" not in cypher
    assert "run_id" not in params


def test_load_source_record_stamps_ingest_run_id():
    calls: list[tuple[str, dict]] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731

    load_source_record(
        runner, "OSM:way/1", "OSM", ingest_version="r", ingest_run_id="r@20260713T000000Z-abc"
    )

    cypher, params = calls[0]
    assert "r.ingest_run_id = $run_id" in cypher
    assert params["run_id"] == "r@20260713T000000Z-abc"

    calls.clear()
    load_source_record(runner, "OSM:way/1", "OSM", ingest_version="r")
    cypher, params = calls[0]
    assert "ingest_run_id" not in cypher
    assert "run_id" not in params


def test_prune_run_marker_targets_untouched_nodes_not_version():
    # THE falsification of the old mechanism: with a constant per-region
    # `ingest_version`, the version-keyed predicate (`ingest_version <> $iv`) can never
    # see a filter-drift victim. In run-marker mode the stale predicate must key on
    # `ingest_run_id` — "not stamped by this run" — and must NOT exclude candidates by
    # current version (a drift victim's version EQUALS the current one).
    runner, calls = _make_prune_runner(n_cur=1400, n_prev=10)

    outcome = prune_stale_trails(
        runner,
        "shenandoah-gwj",
        region_id="shenandoah-gwj",
        pre_load_count=1410,
        run_id="shenandoah-gwj@20260713T000000Z-abc",
    )

    assert outcome.pruned is True
    assert len(calls) == 2
    for cypher, params in calls:
        # Stale = region member NOT stamped by this run (legacy unstamped nodes — the
        # pre-marker corpus — are candidates too, so drift heals without a backfill).
        assert "(node.ingest_run_id IS NULL OR node.ingest_run_id <> $run_id)" in cypher
        # The version-keyed exclusion must be GONE: a drift victim carries the CURRENT
        # ingest_version, so this clause would exempt it forever (the bug).
        assert "node.ingest_version <> $iv" not in cypher
        # Region scope unchanged: anchored membership predicate, never bare STARTS WITH.
        assert (
            "node.ingest_version = $region_id OR node.ingest_version STARTS WITH $prefix" in cypher
        )
        # The in-query empty-run belt counts THIS RUN's stamps, not a version.
        assert "cur.ingest_run_id = $run_id" in cypher
        assert "n_cur >= $min_current" in cypher
        assert params["run_id"] == "shenandoah-gwj@20260713T000000Z-abc"
        assert params["prefix"] == "shenandoah-gwj-"

    # Owned-ref safety unchanged: pass 1 still excludes Episode-referenced trails.
    assert "AND NOT (node)<-[:ON]-(:Episode)" in calls[0][0]
    # Pass 2 still only deletes orphaned SourceRecords.
    assert "NOT (node)-[:SAME_AS]->(:CanonicalTrail)" in calls[1][0]


def test_prune_run_marker_count_and_delete_share_one_stale_predicate():
    # Idempotency/no-self-wipe hinges on the guards counting EXACTLY the set the delete
    # passes act on. Pin that the module builds both from one shared predicate constant
    # rather than two strings that could drift apart.
    import graph.load as gl

    assert gl._REGION_RUN_STALE_PRED.startswith(gl._REGION_PRED)
    assert "(node.ingest_run_id IS NULL OR node.ingest_run_id <> $run_id)" in (
        gl._REGION_RUN_STALE_PRED
    )


def test_prune_run_marker_truncated_ingest_trips_ratio_guard():
    # The guard interaction the design must prove: under the run marker, a truncated
    # fetch stamps FEWER nodes, so n_cur (touched-this-run) collapses against the
    # pre-load total and MORE nodes look stale — which is exactly when the ratio guard
    # must abort. (Under the constant-iv scheme this guard could never trip: n_cur
    # counted the whole region regardless of what the run touched.)
    runner, calls = _make_prune_runner(n_cur=100, n_prev=1400)

    outcome = prune_stale_trails(
        runner,
        "shenandoah-gwj",
        region_id="shenandoah-gwj",
        pre_load_count=1500,
        run_id="shenandoah-gwj@20260713T000000Z-abc",
    )

    assert outcome.pruned is False
    assert outcome.reason is not None
    assert "is below 50% of the prior corpus total 1500" in outcome.reason
    assert calls == []  # nothing hit the database


def test_prune_run_marker_empty_run_trips_min_current():
    # A run that stamped nothing (fetch failed entirely) must no-op via guard 1 — with
    # the run marker EVERY region node looks stale, the exact case the guard exists for.
    runner, calls = _make_prune_runner(n_cur=0, n_prev=1500)

    outcome = prune_stale_trails(
        runner, "r", region_id="r", run_id="r@20260713T000000Z-abc", pre_load_count=1500
    )

    assert outcome.pruned is False
    assert "below min_current" in outcome.reason
    assert calls == []


def test_prune_run_marker_owned_ref_protected_count():
    # Owned-ref safety is orthogonal to the marker change: a run-stale trail a live
    # Episode references is counted into `protected` and excluded from the delete.
    def runner(cypher: str, params: dict) -> Any:
        if "RETURN count(cur)" in cypher:
            return [{"n": 100}]
        if "count(DISTINCT node)" in cypher:  # pass 1's DETACH DELETE, true deleted count
            return [{"n": 7}]
        if "(node)<-[:ON]-(:Episode)" in cypher:
            return [{"n": 3}]
        if "RETURN count(node)" in cypher:
            return [{"n": 10}]
        return None

    outcome = prune_stale_trails(
        runner, "r", region_id="r", run_id="r@20260713T000000Z-abc", pre_load_count=100
    )
    assert outcome.pruned is True
    assert outcome.protected == 3
    assert outcome.deleted == 7


def test_count_region_versions_run_mode_keys_on_marker():
    # Run mode: n_cur = region members stamped by this run; n_prev = region members NOT
    # stamped (NULL counts — legacy corpus). Both stay region-scoped by the anchored
    # ingest_version membership predicate, so a marker collision can never leak a count
    # (or a prune) across regions.
    from graph.load import count_region_versions

    seen: list[tuple[str, dict]] = []

    def runner(cypher: str, params: dict) -> Any:
        seen.append((cypher, params))
        if "count(cur)" in cypher:
            return [{"n": 7}]
        return [{"n": 2}]

    n_cur, n_prev = count_region_versions(
        runner, "r", region_id="r", run_id="r@20260713T000000Z-abc"
    )

    assert (n_cur, n_prev) == (7, 2)
    cur_cypher, cur_params = seen[0]
    prev_cypher, prev_params = seen[1]
    assert "cur.ingest_run_id = $run_id" in cur_cypher
    assert "cur.ingest_version = $region_id OR cur.ingest_version STARTS WITH $prefix" in cur_cypher
    assert cur_params["run_id"] == "r@20260713T000000Z-abc"
    assert "(node.ingest_run_id IS NULL OR node.ingest_run_id <> $run_id)" in prev_cypher
    assert (
        "node.ingest_version = $region_id OR node.ingest_version STARTS WITH $prefix" in prev_cypher
    )
    assert prev_params["prefix"] == "r-"


def test_prune_legacy_mode_without_run_id_is_unchanged():
    # Back-compat seam: a caller that passes no run_id gets the version-keyed behavior
    # byte-for-byte (the existing shape tests above pin its details; this pins that the
    # new marker predicate does NOT leak into legacy mode).
    runner, calls = _make_prune_runner(n_cur=1400, n_prev=100)

    outcome = prune_stale_trails(
        runner, "shenandoah-gwj-v11", region_id="shenandoah-gwj", pre_load_count=1500
    )

    assert outcome.pruned is True
    for cypher, params in calls:
        assert "node.ingest_version <> $iv" in cypher
        assert "ingest_run_id" not in cypher
        assert "run_id" not in params


# ── Schema-drift guard: owned→CanonicalTrail edges vs. the prune skip predicate ───
#
# `prune_stale_trails` DETACH-DELETEs stale world trails, but SKIPS any a live owned node
# still references (`_OWNED_REF_PRED` — the fix for the viewer-path 500). That predicate
# hard-codes the ONE owned→CanonicalTrail edge that exists today (Episode-[:ON]->trail).
# If a future feature (a saved/bookmarked trail, a Belief-[:ABOUT]->CanonicalTrail) adds a
# NEW owned→CanonicalTrail edge without widening the predicate, prune would silently sever
# it — reopening the 500 class. This test scans the sanctioned owned-Cypher author
# (`graph.queries`) and FAILS if it creates any owned→CanonicalTrail edge the predicate's
# manifest (`_OWNED_TRAIL_REF_RELS`) doesn't cover.


def _owned_trail_edges_in_queries() -> set[tuple[str, str]]:
    """Every (owned-label, rel-type) edge `graph.queries` MERGEs/CREATEs between an owned
    node and a CanonicalTrail, discovered from each builder's source (variable→label
    bindings correlated with its MERGE/CREATE edge clauses, both `->` and `<-`)."""
    import inspect
    import re

    from graph import queries as q
    from graph.queries import OWNED_LABELS

    bind_re = re.compile(r"\(\s*(\w+)\s*:\s*(\w+)")
    edge_fwd = re.compile(r"(?:MERGE|CREATE)\s*\(\s*(\w+)\s*\)\s*-\[:(\w+)\]->\s*\(\s*(\w+)\s*\)")
    edge_bwd = re.compile(r"(?:MERGE|CREATE)\s*\(\s*(\w+)\s*\)\s*<-\[:(\w+)\]-\s*\(\s*(\w+)\s*\)")

    found: set[tuple[str, str]] = set()
    for obj in vars(q).values():
        if not (inspect.isfunction(obj) and obj.__module__ == q.__name__):
            continue
        src = inspect.getsource(obj)
        bindings = dict(bind_re.findall(src))  # var -> label
        for a, rel, b in edge_fwd.findall(src) + edge_bwd.findall(src):
            labels = {bindings.get(a), bindings.get(b)}
            if "CanonicalTrail" in labels:
                owned = labels & OWNED_LABELS
                for lbl in owned:
                    found.add((lbl, rel))
    return found


def test_owned_ref_predicate_covers_all_owned_trail_edges():
    import re

    from graph.load import _OWNED_REF_PRED, _OWNED_TRAIL_REF_RELS

    # The manifest and the Cypher predicate must stay in lock-step: parse the predicate's
    # `(node)<-[:REL]-(:Label)` clause back into (Label, REL) pairs.
    pred_pairs = {
        (lbl, rel) for rel, lbl in re.findall(r"<-\[:(\w+)\]-\(:(\w+)\)", _OWNED_REF_PRED)
    }
    assert pred_pairs == set(_OWNED_TRAIL_REF_RELS), (
        "_OWNED_REF_PRED and _OWNED_TRAIL_REF_RELS drifted apart — update both together."
    )

    # Sanity: the scanner actually finds the known Episode-[:ON]->CanonicalTrail edge.
    discovered = _owned_trail_edges_in_queries()
    assert ("Episode", "ON") in discovered

    # The regression lock: every owned→CanonicalTrail edge a query builder creates MUST be
    # covered by the prune skip predicate. A new one (e.g. a saved-trail Belief-[:ABOUT]->
    # CanonicalTrail) fails here until _OWNED_REF_PRED + _OWNED_TRAIL_REF_RELS are widened.
    uncovered = discovered - set(_OWNED_TRAIL_REF_RELS)
    assert not uncovered, (
        f"owned→CanonicalTrail edge(s) {sorted(uncovered)} are created by graph.queries but "
        "NOT protected by prune_stale_trails' _OWNED_REF_PRED — a stale-trail prune would "
        "sever them (the viewer-path 500 class). Widen _OWNED_REF_PRED and "
        "_OWNED_TRAIL_REF_RELS to cover them."
    )


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


# ── Epic 027 S2 — per-facet count queries ──────────────────────────────────────
#
# A dedicated grouped fake Runner: `_make_prune_runner` above matches on
# `RETURN count(cur)`/`RETURN count(node)` and returns a single-row scalar shape
# (`[{"n": ...}]`), which does NOT match these queries' grouped
# `... AS value, count(...) AS n` shape (AC-2.2's note) — reusing it would silently
# return the wrong shape, so these tests get their own fake.


def _make_facet_runner(
    *,
    source_rows: list[dict],
    way_type_rows: list[dict],
    elev_rows: list[dict],
    named_rows: list[dict],
) -> tuple[Any, list[dict]]:
    """Dispatches on a distinctive Cypher substring per dimension and returns canned
    multi-row grouped results (the `list[dict]` shape `_grouped_counts` accepts).
    Records every call (cypher + params) so a test can assert on the query text and
    the `$prefix`/`$iv` params actually sent."""
    calls: list[dict] = []

    def runner(cypher: str, params: dict) -> Any:
        calls.append({"cypher": cypher, "params": params})
        if "SAME_AS" in cypher:
            return source_rows
        if "total_gain_m" in cypher:
            return elev_rows
        if "trim(node.name)" in cypher:
            return named_rows
        if "way_type" in cypher:
            return way_type_rows
        raise AssertionError(f"unexpected facet query: {cypher}")

    return runner, calls


def test_count_region_facets_bucket_keys():
    runner, _ = _make_facet_runner(
        source_rows=[{"value": "osm", "n": 100}, {"value": "usfs", "n": 40}],
        way_type_rows=[{"value": "path", "n": 90}, {"value": "", "n": 10}],
        elev_rows=[{"value": True, "n": 80}, {"value": False, "n": 20}],
        named_rows=[{"value": True, "n": 100}],
    )
    buckets = count_region_facets(runner, region_id="shen")
    assert buckets == {
        "source=osm": 100,
        "source=usfs": 40,
        "way_type=path": 90,
        "way_type=": 10,
        "has_elevation=true": 80,
        "has_elevation=false": 20,
        "named=true": 100,
    }


def test_count_region_facets_uses_anchored_region_pred_and_prefix_param():
    runner, calls = _make_facet_runner(
        source_rows=[{"value": "osm", "n": 1}],
        way_type_rows=[{"value": "path", "n": 1}],
        elev_rows=[{"value": True, "n": 1}],
        named_rows=[{"value": True, "n": 1}],
    )
    count_region_facets(runner, region_id="shenandoah-gwj")
    assert calls, "expected the facet queries to run"
    for call in calls:
        assert call["params"]["prefix"] == "shenandoah-gwj-"
        assert "STARTS WITH $prefix" in call["cypher"]


def test_count_version_facets_bucket_keys_and_iv_param():
    runner, calls = _make_facet_runner(
        source_rows=[{"value": "osm", "n": 5}],
        way_type_rows=[{"value": "footway", "n": 5}],
        elev_rows=[{"value": False, "n": 5}],
        named_rows=[{"value": True, "n": 5}],
    )
    buckets = count_version_facets(runner, "shen-2026-07", region_id="shen")
    assert buckets == {
        "source=osm": 5,
        "way_type=footway": 5,
        "has_elevation=false": 5,
        "named=true": 5,
    }
    assert calls, "expected the facet queries to run"
    for call in calls:
        assert call["params"]["iv"] == "shen-2026-07"


def test_source_facet_is_multi_valued():
    # A trail joined to two distinct sources contributes independently to both
    # buckets — the signal that catches "one corroborating source returns half".
    runner, _ = _make_facet_runner(
        source_rows=[{"value": "osm", "n": 30}, {"value": "usfs", "n": 30}],
        way_type_rows=[],
        elev_rows=[],
        named_rows=[],
    )
    buckets = count_region_facets(runner, region_id="shen")
    assert buckets["source=osm"] == 30
    assert buckets["source=usfs"] == 30
