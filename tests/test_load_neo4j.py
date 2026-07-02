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

from graph.load import load_canonical_trail, prune_stale_trails


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
    # The current run is truncated — it only wrote 1 of the ~20 trails.
    _seed_trails(runner, region, f"{region}-v2", 1)

    outcome = prune_stale_trails(runner, f"{region}-v2", region_id=region)

    assert outcome.pruned is False
    assert "count dropped 20->1" in outcome.reason
    # Nothing was deleted — all 21 nodes (20 stale + 1 current) survive.
    assert _count_trails(sess) == 21


@pytest.mark.neo4j
def test_healthy_reingest_prunes_stale_trails(clean_graph):
    sess = clean_graph.scoped_session("ingest")
    runner = _runner(sess)
    region = "shenandoah-gwj"

    _seed_trails(runner, region, f"{region}-v1", 20)
    # A healthy re-ingest: 19 of 20 refresh under the new version (one dropped by a
    # tightened filter — the self-healing case the prune exists for).
    _seed_trails(runner, region, f"{region}-v2", 19)

    outcome = prune_stale_trails(runner, f"{region}-v2", region_id=region)

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
    _seed_trails(runner, "shen", "shen-v2", 10)
    _seed_trails(runner, "shenandoah-gwj", "shenandoah-gwj-v1", 10)

    outcome = prune_stale_trails(runner, "shen-v2", region_id="shen")

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

    outcome = prune_stale_trails(runner, f"{region}-v2", region_id=region)

    assert outcome.pruned is True
    survivors = sess.run(
        (
            "MATCH (n) WHERE n:PhysicalProfile OR n:Person OR n:Episode RETURN labels(n) AS labels",
            {},
        )
    )
    assert len(survivors) == 3  # PhysicalProfile + Person + Episode all untouched
