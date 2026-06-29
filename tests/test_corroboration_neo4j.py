"""Integration: distinct-origin corroboration against a live Neo4j (CDP-01).

Runs `queries.trail_source_corroboration` over a seeded SAME_AS cluster on the real DB
(the CI `integration (neo4j)` job), proving the count is genuine distinct origins — not
echoed feeds — and that a duplicate source in the cluster collapses to one. No live Aura:
the `clean_graph` fixture seeds a throwaway local graph.
"""

from __future__ import annotations

from typing import Any

import pytest

from graph import queries


@pytest.mark.neo4j
def test_corroboration_counts_distinct_origins_not_echoes(clean_graph: Any) -> None:
    seed = clean_graph.scoped_session("seed")
    # A trail with three SourceRecords but only TWO distinct origins (OSM duplicated) —
    # the duplicate is an echo, not independent corroboration → count must be 2.
    seed.run(("CREATE (:CanonicalTrail {canonical_id: 'ct:multi'})", {}))
    for sr_uid, source in (("sr:osm-a", "OSM"), ("sr:osm-b", "OSM"), ("sr:nps", "NPS")):
        seed.run(
            (
                "MATCH (t:CanonicalTrail {canonical_id: 'ct:multi'}) "
                "CREATE (t)<-[:SAME_AS {source: $source}]-"
                "(:SourceRecord {sr_uid: $sr_uid, source: $source})",
                {"sr_uid": sr_uid, "source": source},
            )
        )
    # A trail with no SourceRecords → count 0 (caller floors to the honest baseline 1).
    seed.run(("CREATE (:CanonicalTrail {canonical_id: 'ct:orphan'})", {}))

    rows = seed.run(queries.trail_source_corroboration(["ct:multi", "ct:orphan"]))
    by_id = {r["canonical_id"]: r for r in rows}

    assert by_id["ct:multi"]["corroboration"] == 2  # OSM echo collapsed; OSM + NPS
    assert sorted(by_id["ct:multi"]["sources"]) == ["NPS", "OSM"]
    assert by_id["ct:orphan"]["corroboration"] == 0
    assert by_id["ct:orphan"]["sources"] == []
