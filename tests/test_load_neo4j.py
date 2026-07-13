"""Live-Neo4j integration for `graph.load.prune_stale_trails`'s partial-ingest guard
(security review finding M1).

Behind `@pytest.mark.neo4j` (Epic 015 pattern): the fast legs skip these; CI's
integration job runs them against a real database. The hermetic tests in
`test_load.py` prove the Cypher shape and the guard decision against a fake runner;
these prove the guard actually protects (and actually prunes) real nodes.
"""

from __future__ import annotations

from typing import Any

import pytest

from graph.load import (
    count_region_trails,
    count_region_versions,
    load_canonical_trail,
    load_enrichment_facts,
    load_source_record,
    merge_same_as,
    new_ingest_run_id,
    prune_stale_trails,
)
from ingestion.pipeline import IngestVerificationError, verify_before_prune
from ingestion.sources.base import EnrichmentFact, Region


def _runner(sess: Any) -> Any:
    def run(cypher: str, params: dict) -> Any:
        return sess.run((cypher, params))

    return run


def _seed_trails(runner: Any, region_id: str, ingest_version: str, count: int) -> None:
    # canonical_id embeds ingest_version so seeding two versions never MERGE-collides
    # onto the same node (that would silently "upgrade" a stale trail's version and
    # invalidate the test's intended prior/current split).
    for i in range(count):
        load_canonical_trail(
            runner,
            f"ct:{ingest_version}:{i}",
            f"Trail {i}",
            region=region_id,
            ingest_version=ingest_version,
        )


def _seed_prod_trails(runner: Any, region_id: str, ingest_version: str, count: int) -> None:
    # PRODUCTION-STYLE canonical_ids: version-INDEPENDENT (ct:osm:trail-{i}), exactly what
    # `_build_canonical_id` emits. A re-ingest at a new ingest_version MERGE-COLLIDES onto
    # the same nodes and flips their version old→new (the opposite of `_seed_trails`). This
    # is what makes the post-load `n_prev` the run's MISSED trails, not a separate corpus —
    # the precondition for the silent-half-wipe the collapse gate must catch.
    for i in range(count):
        load_canonical_trail(
            runner,
            f"ct:osm:trail-{i}",
            f"Trail {i}",
            region=region_id,
            ingest_version=ingest_version,
        )


def _count_trails(sess: Any) -> int:
    rows = sess.run(("MATCH (t:CanonicalTrail) RETURN count(t) AS c", {}))
    return rows[0]["c"]


@pytest.mark.neo4j
def test_truncated_ingest_does_not_prune(clean_graph):
    sess = clean_graph.scoped_session("ingest")
    runner = _runner(sess)
    region = "shenandoah-gwj"

    # A prior "healthy" ingest left 20 trails.
    _seed_trails(runner, region, f"{region}-v1", 20)
    pre = count_region_trails(runner, region_id=region)
    assert pre == 20
    # The current run is truncated — it only wrote 1 of the ~20 trails.
    _seed_trails(runner, region, f"{region}-v2", 1)

    outcome = prune_stale_trails(runner, f"{region}-v2", region_id=region, pre_load_count=pre)

    assert outcome.pruned is False
    assert "is below 50% of the prior corpus total 20" in outcome.reason
    # Nothing was deleted — all 21 nodes (20 stale + 1 current) survive.
    assert _count_trails(sess) == 21


@pytest.mark.neo4j
def test_healthy_reingest_prunes_stale_trails(clean_graph):
    sess = clean_graph.scoped_session("ingest")
    runner = _runner(sess)
    region = "shenandoah-gwj"

    _seed_trails(runner, region, f"{region}-v1", 20)
    pre = count_region_trails(runner, region_id=region)
    # A healthy re-ingest: 19 of 20 refresh under the new version (one dropped by a
    # tightened filter — the self-healing case the prune exists for).
    _seed_trails(runner, region, f"{region}-v2", 19)

    outcome = prune_stale_trails(runner, f"{region}-v2", region_id=region, pre_load_count=pre)

    assert outcome.pruned is True
    rows = sess.run(
        (
            "MATCH (t:CanonicalTrail) RETURN t.canonical_id AS cid, "
            "t.ingest_version AS iv ORDER BY cid",
            {},
        )
    )
    assert len(rows) == 19
    assert all(r["iv"] == f"{region}-v2" for r in rows)


@pytest.mark.neo4j
def test_empty_ingest_still_noops(clean_graph):
    sess = clean_graph.scoped_session("ingest")
    runner = _runner(sess)
    region = "shenandoah-gwj"

    _seed_trails(runner, region, f"{region}-v1", 20)

    outcome = prune_stale_trails(runner, f"{region}-v2", region_id=region)

    assert outcome.pruned is False
    assert _count_trails(sess) == 20


@pytest.mark.neo4j
def test_region_scope_protects_other_regions(clean_graph):
    sess = clean_graph.scoped_session("ingest")
    runner = _runner(sess)

    _seed_trails(runner, "shen", "shen-v1", 10)
    pre = count_region_trails(runner, region_id="shen")
    _seed_trails(runner, "shen", "shen-v2", 10)
    _seed_trails(runner, "shenandoah-gwj", "shenandoah-gwj-v1", 10)

    outcome = prune_stale_trails(runner, "shen-v2", region_id="shen", pre_load_count=pre)

    assert outcome.pruned is True
    rows = sess.run(("MATCH (t:CanonicalTrail) RETURN t.region AS region", {}))
    regions = [r["region"] for r in rows]
    assert regions.count("shen") == 10
    # A bare (non-anchored) prefix match would have let "shen" prune
    # "shenandoah-gwj" too — it must not.
    assert regions.count("shenandoah-gwj") == 10


@pytest.mark.neo4j
def test_personal_nodes_survive_prune(clean_graph):
    sess = clean_graph.scoped_session("ingest")
    runner = _runner(sess)
    region = "shenandoah-gwj"

    _seed_trails(runner, region, f"{region}-v1", 20)
    pre = count_region_trails(runner, region_id=region)
    _seed_trails(runner, region, f"{region}-v2", 19)
    sess.run(
        (
            "MERGE (pp:PhysicalProfile {owner_id: 'mem:test'}) SET pp.pace_on_grade = 12.0",
            {},
        )
    )
    sess.run(
        (
            "MERGE (p:Person {owner_id: 'mem:test'}) "
            "MERGE (e:Episode {episode_id: 'ep:test', owner_id: 'mem:test'}) "
            "MERGE (p)-[:DID]->(e)",
            {},
        )
    )

    outcome = prune_stale_trails(runner, f"{region}-v2", region_id=region, pre_load_count=pre)

    assert outcome.pruned is True
    survivors = sess.run(
        (
            "MATCH (n) WHERE n:PhysicalProfile OR n:Person OR n:Episode RETURN labels(n) AS labels",
            {},
        )
    )
    assert len(survivors) == 3  # PhysicalProfile + Person + Episode all untouched


@pytest.mark.neo4j
def test_owned_referenced_trail_survives_prune(clean_graph):
    # Owned-ref safety (2c): a STALE world trail a live Episode still references must NOT
    # be DETACH-deleted (that severs the personal→world ref — the viewer-path 500). It is
    # kept and counted into PruneOutcome.protected; every other stale trail still prunes.
    sess = clean_graph.scoped_session("ingest")
    runner = _runner(sess)
    region = "shenandoah-gwj"

    _seed_trails(runner, region, f"{region}-v1", 20)
    pre = count_region_trails(runner, region_id=region)
    _seed_trails(runner, region, f"{region}-v2", 19)  # healthy re-ingest
    stale_cid = f"ct:{region}-v1:0"  # one now-stale v1 trail is personally referenced
    sess.run(
        (
            "MATCH (t:CanonicalTrail {canonical_id: $cid}) "
            "MERGE (p:Person {owner_id: 'mem:test'}) "
            "MERGE (e:Episode {episode_id: 'ep:test', owner_id: 'mem:test'}) "
            "MERGE (p)-[:DID]->(e) MERGE (e)-[:ON]->(t)",
            {"cid": stale_cid},
        )
    )

    outcome = prune_stale_trails(runner, f"{region}-v2", region_id=region, pre_load_count=pre)

    assert outcome.pruned is True
    assert outcome.protected == 1  # the Episode-referenced stale trail was kept
    # 19 (v2) + 1 (protected v1) survive; the other 19 stale v1 trails are pruned.
    assert _count_trails(sess) == 20
    survivor = sess.run(
        (
            "MATCH (t:CanonicalTrail {canonical_id: $cid}) RETURN t.canonical_id AS cid",
            {"cid": stale_cid},
        )
    )
    assert [r["cid"] for r in survivor] == [stale_cid]
    # The read path still resolves Episode -> its world trail (no severed ref → no 500).
    linked = sess.run(
        (
            "MATCH (:Episode {episode_id: 'ep:test'})-[:ON]->(t:CanonicalTrail) "
            "RETURN t.canonical_id AS cid",
            {},
        )
    )
    assert [r["cid"] for r in linked] == [stale_cid]


# ── Elevation survives a re-ingest (root-cause fix: usgs-3dep default + degrade) ─
#
# The bug: a region re-ingest that ran without `usgs-3dep` in ADVENTURE_CORPUS_SOURCES
# silently wiped every trail's elevation. `load_canonical_trail`'s MERGE+SET only ever
# touches the properties it's given (never `elev_source`/`total_gain_m`/etc.), and
# `load_enrichment_facts` is purely additive — so a re-ingest that simply doesn't run
# 3DEP this time must never clear elevation a prior run wrote. This proves that against
# a real Neo4j.


@pytest.mark.neo4j
def test_reingest_without_enrichment_preserves_existing_elevation(clean_graph):
    sess = clean_graph.scoped_session("ingest")
    runner = _runner(sess)
    cid = "ct:osm:test-trail"

    load_canonical_trail(runner, cid, "Test Trail", region="shenandoah-gwj", ingest_version="v1")
    load_enrichment_facts(
        runner,
        [
            EnrichmentFact(
                source="usgs-3dep", attribute="elev_source", value="usgs-3dep", canonical_id=cid
            ),
            EnrichmentFact(
                source="usgs-3dep", attribute="total_gain_m", value=123.4, canonical_id=cid
            ),
        ],
    )

    # A later re-ingest of the same node refreshes it under a new ingest_version but
    # runs with no enrichment source this time (e.g. a DEM-less region) — it must not
    # touch elevation it didn't recompute.
    load_canonical_trail(runner, cid, "Test Trail", region="shenandoah-gwj", ingest_version="v2")

    rows = sess.run(
        (
            "MATCH (t:CanonicalTrail {canonical_id: $cid}) "
            "RETURN t.elev_source AS es, t.total_gain_m AS gain, t.ingest_version AS iv",
            {"cid": cid},
        )
    )
    assert rows[0]["es"] == "usgs-3dep"
    assert rows[0]["gain"] == 123.4
    assert rows[0]["iv"] == "v2"  # the node did refresh — just not its elevation


# ── The regression lock: a 50% partial re-ingest must NOT wipe the corpus ─────────
#
# THE reason this PR exists. With PRODUCTION-STYLE version-independent canonical_ids, a
# re-ingest MERGE-collides onto existing nodes and flips their version, so a 50% partial
# leaves n_cur ≈ n_prev (complementary halves of one total). The OLD gate compared n_cur
# against n_prev (`n_cur < 0.5*n_prev`) — which a 50% partial PASSES — then pruned the
# stragglers: a silent half-wipe. The corrected gate compares n_cur against the PRE-LOAD
# corpus total, so the same partial ABORTS and the whole prior corpus is preserved.


@pytest.mark.neo4j
def test_partial_reingest_with_prod_ids_preserves_corpus(clean_graph):
    sess = clean_graph.scoped_session("ingest")
    runner = _runner(sess)
    region = "shenandoah-gwj"

    # Prior healthy corpus: 10 trails under v1, production-style version-independent ids.
    _seed_prod_trails(runner, region, f"{region}-v1", 10)
    pre = count_region_trails(runner, region_id=region)  # snapshot BEFORE the re-ingest
    assert pre == 10

    # A truncated re-ingest: only 4 of the 10 trails come back this run. Because the ids
    # are version-independent, those 4 MERGE onto their existing nodes and flip v1→v2; the
    # other 6 stay at v1 — they're the MISSED trails, not a separate corpus.
    _seed_prod_trails(runner, region, f"{region}-v2", 4)
    assert _count_trails(sess) == 10  # still one corpus of 10 (4 collided, 6 untouched)

    n_cur, n_prev = count_region_versions(runner, f"{region}-v2", region_id=region)
    # Complementary halves of one total — the exact shape that fooled the old gate.
    assert (n_cur, n_prev) == (4, 6)
    # Documented: the OLD formula (n_cur < 0.5 * n_prev = 3) would PASS (4 !< 3) → it would
    # have pruned the 6 stragglers, a silent 60% wipe. The corrected gate compares against
    # `pre` (10): 4 < 0.5 * 10 = 5 → abort.
    assert not (n_cur < 0.5 * n_prev)  # old gate: green-lights the wipe

    props = {"region_id": region, "bbox": (37.8, -79.4, 39.1, -78.0)}
    verify_region = Region(region_id=region, bbox=(37.8, -79.4, 39.1, -78.0), props=props)

    # (a) The pipeline's primary gate ABORTS on the partial re-ingest.
    with pytest.raises(IngestVerificationError, match="collapsed"):
        verify_before_prune(
            verify_region,
            {},
            runner,
            iv=f"{region}-v2",
            elevation_expected=False,
            pre_load_count=pre,
        )

    # (b) Because it raised, prune is SKIPPED. Prove the belt too: even called directly, the
    # prune declines (guard 2) with the pre-load total — nothing is deleted.
    outcome = prune_stale_trails(runner, f"{region}-v2", region_id=region, pre_load_count=pre)
    assert outcome.pruned is False
    assert (outcome.n_cur, outcome.n_prev) == (4, 6)

    # The full prior corpus is preserved — no straggler was wiped.
    assert _count_trails(sess) == 10


# ── Filter-drift healing: the per-run marker (`ingest_run_id`) ─────────────────────
#
# The production reality these tests model: `ingest_version` is a CONSTANT per region
# (the region id — no region geojson sets the optional suffix), so the version-keyed
# stale predicate can never see a node a tightened filter newly excludes. The run
# marker keys "stale" on "not stamped by THIS run" instead. Every test seeds with the
# CONSTANT iv (`ingest_version=region`) — the exact shape the old mechanism was blind
# to — and production-style version-independent canonical ids.


def _seed_stamped_trails(
    runner: Any, region_id: str, count: int, *, run_id: str | None, start: int = 0
) -> None:
    for i in range(start, start + count):
        load_canonical_trail(
            runner,
            f"ct:osm:trail-{i}",
            f"Trail {i}",
            region=region_id,
            ingest_version=region_id,  # constant per region — the drift-blind shape
            ingest_run_id=run_id,
        )


@pytest.mark.neo4j
def test_run_marker_prunes_filter_drift_victim(clean_graph):
    """THE falsification pair. (a) Old mechanism: with a constant iv, a node the
    tightened filter dropped shows ZERO stale candidates (`n_prev == 0`) — the junk
    lives forever (tonight's manual-delete incident). (b) New mechanism: the same node,
    untouched by the current run, IS a candidate and gets pruned; its now-orphaned
    SourceRecord goes with it, while a stale-but-still-corroborating SourceRecord and
    every restamped node survive."""
    sess = clean_graph.scoped_session("ingest")
    runner = _runner(sess)
    region = "shenandoah-gwj"

    # Run A: 10 trails, all constant-iv, all stamped with run A's marker. Two
    # SourceRecords: one on the future victim, one on a survivor.
    run_a = new_ingest_run_id(region)
    _seed_stamped_trails(runner, region, 10, run_id=run_a)
    load_source_record(runner, "OSM:way/keep", "OSM", ingest_version=region, ingest_run_id=run_a)
    merge_same_as(runner, "ct:osm:trail-0", "OSM:way/keep", source="OSM")
    load_source_record(runner, "OSM:way/victim", "OSM", ingest_version=region, ingest_run_id=run_a)
    merge_same_as(runner, "ct:osm:trail-9", "OSM:way/victim", source="OSM")

    # (a) The confirmed gap, reproduced: version-keyed counting sees NOTHING stale —
    # every node's ingest_version equals the current one (the constant region id).
    n_cur_legacy, n_prev_legacy = count_region_versions(runner, region, region_id=region)
    assert (n_cur_legacy, n_prev_legacy) == (10, 0)

    # Run B: the tightened filter drops trail-9; the other 9 are re-loaded (MERGE onto
    # the same nodes, same constant iv) and restamped — including trail-0's SR. The
    # victim's SR is NOT restamped (its way no longer passes the filter).
    pre = count_region_trails(runner, region_id=region)
    assert pre == 10
    run_b = new_ingest_run_id(region)
    _seed_stamped_trails(runner, region, 9, run_id=run_b)
    load_source_record(runner, "OSM:way/keep", "OSM", ingest_version=region, ingest_run_id=run_b)

    outcome = prune_stale_trails(runner, region, region_id=region, pre_load_count=pre, run_id=run_b)

    assert outcome.pruned is True
    assert (outcome.n_cur, outcome.n_prev) == (9, 1)
    assert _count_trails(sess) == 9
    gone = sess.run(("MATCH (t:CanonicalTrail {canonical_id: 'ct:osm:trail-9'}) RETURN t", {}))
    assert gone == []
    # Pass 2: the victim's orphaned SourceRecord is gone; the survivor's remains.
    srs = sess.run(("MATCH (r:SourceRecord) RETURN r.sr_uid AS uid", {}))
    assert [r["uid"] for r in srs] == ["OSM:way/keep"]


@pytest.mark.neo4j
def test_run_marker_stale_but_corroborating_source_record_survives(clean_graph):
    # A SourceRecord NOT restamped this run but still SAME_AS-linked to a SURVIVING
    # trail must be kept (rule #1 source-or-silence / rule #7 provenance): pass 2 only
    # deletes stale AND orphaned records.
    sess = clean_graph.scoped_session("ingest")
    runner = _runner(sess)
    region = "shenandoah-gwj"

    run_a = new_ingest_run_id(region)
    _seed_stamped_trails(runner, region, 2, run_id=run_a)
    load_source_record(runner, "NPS:old-survey", "NPS", ingest_version=region, ingest_run_id=run_a)
    merge_same_as(runner, "ct:osm:trail-0", "NPS:old-survey", source="NPS")

    run_b = new_ingest_run_id(region)
    _seed_stamped_trails(runner, region, 2, run_id=run_b)  # both trails survive
    # NPS source didn't run this time — its record is stale-by-marker but corroborating.

    outcome = prune_stale_trails(runner, region, region_id=region, pre_load_count=2, run_id=run_b)

    assert outcome.pruned is True
    srs = sess.run(("MATCH (r:SourceRecord) RETURN r.sr_uid AS uid", {}))
    assert [r["uid"] for r in srs] == ["NPS:old-survey"]


@pytest.mark.neo4j
def test_run_marker_truncated_ingest_aborts_via_ratio_guard(clean_graph):
    """The guard interaction, proven end-to-end: a truncated run restamps only 4 of 20
    constant-iv nodes, which makes the OTHER 16 look stale — exactly when the ratio
    guard must trip. (Under constant-iv counting this could never fire: n_cur read the
    whole region.) Both the pipeline gate and the prune's own belt abort; nothing is
    deleted."""
    sess = clean_graph.scoped_session("ingest")
    runner = _runner(sess)
    region = "shenandoah-gwj"

    run_a = new_ingest_run_id(region)
    _seed_stamped_trails(runner, region, 20, run_id=run_a)
    pre = count_region_trails(runner, region_id=region)
    assert pre == 20

    run_b = new_ingest_run_id(region)
    _seed_stamped_trails(runner, region, 4, run_id=run_b)  # truncated: 4 of 20

    props = {"region_id": region, "bbox": (37.8, -79.4, 39.1, -78.0)}
    verify_region = Region(region_id=region, bbox=(37.8, -79.4, 39.1, -78.0), props=props)
    with pytest.raises(IngestVerificationError, match="collapsed"):
        verify_before_prune(
            verify_region,
            {},
            runner,
            iv=region,
            elevation_expected=False,
            pre_load_count=pre,
            run_id=run_b,
        )

    outcome = prune_stale_trails(runner, region, region_id=region, pre_load_count=pre, run_id=run_b)
    assert outcome.pruned is False
    assert (outcome.n_cur, outcome.n_prev) == (4, 16)
    assert _count_trails(sess) == 20  # the last-good corpus is intact


@pytest.mark.neo4j
def test_run_marker_back_to_back_identical_runs_prune_nothing(clean_graph):
    # Idempotency: two identical runs back-to-back must not prune the world. Run B
    # restamps every node run A wrote, so B's stale-candidate set is empty.
    sess = clean_graph.scoped_session("ingest")
    runner = _runner(sess)
    region = "shenandoah-gwj"

    run_a = new_ingest_run_id(region)
    _seed_stamped_trails(runner, region, 10, run_id=run_a)
    outcome_a = prune_stale_trails(runner, region, region_id=region, pre_load_count=0, run_id=run_a)
    assert outcome_a.pruned is True  # first-ever ingest: delete passes ran…
    assert _count_trails(sess) == 10  # …but found no candidates

    run_b = new_ingest_run_id(region)
    _seed_stamped_trails(runner, region, 10, run_id=run_b)
    outcome_b = prune_stale_trails(
        runner, region, region_id=region, pre_load_count=10, run_id=run_b
    )
    assert outcome_b.pruned is True
    assert outcome_b.n_prev == 0
    assert _count_trails(sess) == 10


@pytest.mark.neo4j
def test_run_marker_legacy_unstamped_corpus_heals_without_backfill(clean_graph):
    # Migration: the live corpus predates the marker (no node carries ingest_run_id).
    # The first marker-aware run restamps what it fetches; the unstamped leftovers are
    # stale candidates by construction (IS NULL) — accumulated drift heals with no
    # backfill and no wipe.
    sess = clean_graph.scoped_session("ingest")
    runner = _runner(sess)
    region = "shenandoah-gwj"

    _seed_stamped_trails(runner, region, 10, run_id=None)  # legacy: unstamped
    pre = count_region_trails(runner, region_id=region)

    run_b = new_ingest_run_id(region)
    _seed_stamped_trails(runner, region, 9, run_id=run_b)  # filter now drops trail-9

    outcome = prune_stale_trails(runner, region, region_id=region, pre_load_count=pre, run_id=run_b)

    assert outcome.pruned is True
    assert _count_trails(sess) == 9
    gone = sess.run(("MATCH (t:CanonicalTrail {canonical_id: 'ct:osm:trail-9'}) RETURN t", {}))
    assert gone == []


@pytest.mark.neo4j
def test_run_marker_owned_referenced_trail_survives(clean_graph):
    # Owned-ref safety is preserved under the marker: a run-stale trail a live Episode
    # references is kept (protected=1), never DETACH-deleted (the viewer-path 500).
    sess = clean_graph.scoped_session("ingest")
    runner = _runner(sess)
    region = "shenandoah-gwj"

    run_a = new_ingest_run_id(region)
    _seed_stamped_trails(runner, region, 10, run_id=run_a)
    sess.run(
        (
            "MATCH (t:CanonicalTrail {canonical_id: 'ct:osm:trail-9'}) "
            "MERGE (p:Person {owner_id: 'mem:test'}) "
            "MERGE (e:Episode {episode_id: 'ep:test', owner_id: 'mem:test'}) "
            "MERGE (p)-[:DID]->(e) MERGE (e)-[:ON]->(t)",
            {},
        )
    )

    run_b = new_ingest_run_id(region)
    _seed_stamped_trails(runner, region, 9, run_id=run_b)  # trail-9 dropped by filter

    outcome = prune_stale_trails(runner, region, region_id=region, pre_load_count=10, run_id=run_b)

    assert outcome.pruned is True
    assert outcome.protected == 1
    assert _count_trails(sess) == 10  # the referenced trail was kept
    linked = sess.run(
        (
            "MATCH (:Episode {episode_id: 'ep:test'})-[:ON]->(t:CanonicalTrail) "
            "RETURN t.canonical_id AS cid",
            {},
        )
    )
    assert [r["cid"] for r in linked] == ["ct:osm:trail-9"]


@pytest.mark.neo4j
def test_run_marker_region_scope_protects_other_regions(clean_graph):
    # Cross-region safety under the marker: region B's nodes carry NO marker (maximally
    # stale-looking — `IS NULL` matches them), so ONLY the anchored region predicate
    # protects them. A region-A prune must not touch them.
    sess = clean_graph.scoped_session("ingest")
    runner = _runner(sess)

    run_b = new_ingest_run_id("shen")
    for i in range(5):
        load_canonical_trail(
            runner,
            f"ct:osm:shen-{i}",
            f"Shen {i}",
            region="shen",
            ingest_version="shen",
            ingest_run_id=run_b,
        )
    # The other region: constant iv, never stamped — and a prefix-overlapping id.
    for i in range(5):
        load_canonical_trail(
            runner,
            f"ct:osm:gwj-{i}",
            f"GWJ {i}",
            region="shenandoah-gwj",
            ingest_version="shenandoah-gwj",
            ingest_run_id=None,
        )

    outcome = prune_stale_trails(runner, "shen", region_id="shen", pre_load_count=5, run_id=run_b)

    assert outcome.pruned is True
    rows = sess.run(("MATCH (t:CanonicalTrail) RETURN t.region AS region", {}))
    regions = [r["region"] for r in rows]
    assert regions.count("shen") == 5
    assert regions.count("shenandoah-gwj") == 5
