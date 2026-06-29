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
    seed.run(("CREATE (:CanonicalTrail {canonical_id: 'ct:a'})", {}))
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
    assert stats.canonical_trails == 3
    assert stats.source_records == 2
    assert stats.trailheads == 1
    assert stats.same_as_edges == 1
