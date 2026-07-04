"""Tests for graph.load — idempotent MERGE upserts via injected runner."""

from __future__ import annotations

from typing import Any

import pytest

from graph.load import (
    clear_trail_segments,
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
