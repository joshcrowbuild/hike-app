"""Integration: trail-name search against a live Neo4j (Epic 038 / B001 Problem A).

Seeds two `CanonicalTrail` nodes with distinct names and proves the FULLTEXT index
(`trail_name_fts`) resolves a name query to the RIGHT trail — including a fuzzy typo
match — then proves the same holds through `scout_by_name` and `search_trails` (the
function `POST /search` calls). No live Aura: the `clean_graph` fixture seeds a
throwaway local graph, matching `test_corroboration_neo4j.py`'s pattern.

Fulltext indexes populate asynchronously in Neo4j — `CALL db.awaitIndexes()` after
seeding blocks until `trail_name_fts` (created by `schema.cypher`, applied by the
`neo4j_client` fixture) is online, so a query immediately after a write can't race
the index build.
"""

from __future__ import annotations

from typing import Any

import pytest

from graph import queries
from orchestration.engine import search_trails
from orchestration.scout import scout_by_name

pytestmark = pytest.mark.neo4j


def _seed_two_trails(client: Any) -> Any:
    seed = client.scoped_session("seed")
    seed.run(
        (
            "CREATE (:CanonicalTrail {canonical_id: 'ct:old-rag-loop', name: 'Old Rag Loop', "
            "point: point({latitude: 38.5519, longitude: -78.2861})})",
            {},
        )
    )
    seed.run(
        (
            "CREATE (:CanonicalTrail {canonical_id: 'ct:rivanna-trail', name: 'Rivanna Trail', "
            "point: point({latitude: 38.0293, longitude: -78.4767})})",
            {},
        )
    )
    seed.run(("CALL db.awaitIndexes()", {}))
    return seed


def test_fulltext_query_resolves_to_the_named_trail(clean_graph: Any) -> None:
    _seed_two_trails(clean_graph)
    seed = clean_graph.scoped_session("reader")

    rows = seed.run(queries.candidate_trails_by_name("Old Rag", 10))
    ids = [r["canonical_id"] for r in rows]
    assert "ct:old-rag-loop" in ids
    assert "ct:rivanna-trail" not in ids


def test_fulltext_query_fuzzy_typo_still_matches(clean_graph: Any) -> None:
    _seed_two_trails(clean_graph)
    seed = clean_graph.scoped_session("reader")

    # "Rivana" (missing an 'n') — the fuzzy `~` suffix must still resolve this to
    # "Rivanna Trail" (edit-distance-1 tolerance).
    rows = seed.run(queries.candidate_trails_by_name("Rivana", 10))
    ids = [r["canonical_id"] for r in rows]
    assert "ct:rivanna-trail" in ids


def test_fulltext_query_gibberish_returns_no_rows(clean_graph: Any) -> None:
    _seed_two_trails(clean_graph)
    seed = clean_graph.scoped_session("reader")

    rows = seed.run(queries.candidate_trails_by_name("zzqxw-nonexistent-9999", 10))
    assert rows == []


def test_scout_by_name_resolves_the_named_trail_live(clean_graph: Any) -> None:
    _seed_two_trails(clean_graph)
    session = clean_graph.scoped_session("reader")

    out = scout_by_name("Old Rag", session)
    assert [c.canonical_id for c in out] == ["ct:old-rag-loop"]


def test_search_trails_returns_cards_for_a_known_name(clean_graph: Any) -> None:
    _seed_two_trails(clean_graph)
    session = clean_graph.scoped_session("reader")

    batch = search_trails("Old Rag", session, {})  # no live probes wired -> verify is a no-op
    assert [p.candidate.canonical_id for p in batch.trails] == ["ct:old-rag-loop"]


def test_search_trails_empty_feed_for_gibberish(clean_graph: Any) -> None:
    _seed_two_trails(clean_graph)
    session = clean_graph.scoped_session("reader")

    batch = search_trails("zzqxw-nonexistent-9999", session, {})
    assert batch.trails == []
    assert batch.set_aside == ()


def test_search_trails_blank_query_is_empty_never_a_lucene_error(clean_graph: Any) -> None:
    # A blank query sanitizes to an empty Lucene query string — Neo4j's fulltext index
    # rejects that at query time, so this must short-circuit before ever reaching
    # Cypher (see scout.scout_by_name) rather than surface a runtime query error.
    _seed_two_trails(clean_graph)
    session = clean_graph.scoped_session("reader")

    batch = search_trails("   ", session, {})
    assert batch.trails == []
