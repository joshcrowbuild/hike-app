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
