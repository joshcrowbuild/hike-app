"""Integration: /health graph stats run against a live Neo4j (Epic R7 hardening).

The counts use COUNT {} subqueries — Cypher 5 AND Cypher 25 — replacing the old
size([(pattern)|x]) pattern-comprehension form that Aura's Cypher 25 rejects (42I06),
which had left graph=null on every /health. This runs the real `_graph_stats` against
the DB and asserts the counts are correct (the CI `integration (neo4j)` job).
"""

from __future__ import annotations

from typing import Any

import pytest

import api.app as app_mod
from orchestration.config import Settings


@pytest.mark.neo4j
def test_graph_stats_counts_via_count_subquery(clean_graph: Any) -> None:
    seed = clean_graph.scoped_session("seed")
    seed.run(("MERGE (m:Meta {id: 'schema'}) SET m.schema_version = 'stats-test'", {}))
    # ct:a carries a 3DEP profile (total_gain_m) → counted by the elevation gauge.
    seed.run(("CREATE (:CanonicalTrail {canonical_id: 'ct:a', total_gain_m: 120.0})", {}))
    seed.run(("CREATE (:CanonicalTrail {canonical_id: 'ct:b'})", {}))
    seed.run(("CREATE (:SourceRecord {sr_uid: 'sr:1'})", {}))
    seed.run(("CREATE (:Trailhead {trailhead_id: 'th:1'})", {}))
    # One more trail + source record joined by a SAME_AS edge.
    seed.run(
        (
            "CREATE (:CanonicalTrail {canonical_id: 'ct:c'})"
            "<-[:SAME_AS]-(:SourceRecord {sr_uid: 'sr:2'})",
            {},
        )
    )
    # ct:d is corroborated by two distinct-source SAME_AS edges → counted by the
    # corroboration gauge; ct:c above has only one source, so it stays below the floor.
    seed.run(
        (
            "CREATE (t:CanonicalTrail {canonical_id: 'ct:d'})"
            "<-[:SAME_AS]-(:SourceRecord {sr_uid: 'sr:3', source: 'osm'})\n"
            "WITH t "
            "CREATE (t)<-[:SAME_AS]-(:SourceRecord {sr_uid: 'sr:4', source: 'nps'})",
            {},
        )
    )

    app_mod._graph_client = clean_graph
    app_mod._settings = Settings.from_env({})
    try:
        stats = app_mod._graph_stats()
    finally:
        app_mod._graph_client = None
        app_mod._settings = None

    # COUNT {} executed cleanly on the live DB (no 42I06) and counted correctly.
    assert stats is not None
    assert stats.schema_version == "stats-test"
    assert stats.canonical_trails == 4
    assert stats.source_records == 4
    assert stats.trailheads == 1
    assert stats.same_as_edges == 3
    # Elevation gauge: only ct:a has total_gain_m → 1 of 4 (25%).
    assert stats.trails_with_elevation == 1
    assert stats.elevation_coverage_pct == round(1 / 4 * 100, 1)
    # Corroboration gauge: only ct:d has ≥2 distinct SAME_AS sources (osm + nps) →
    # 1 of 4 (25%); ct:c's single un-sourced SourceRecord doesn't clear the floor.
    assert stats.trails_multi_source == 1
    assert stats.corroboration_pct == round(1 / 4 * 100, 1)
