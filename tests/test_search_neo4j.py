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


def _seed_old_rag_and_noise(client: Any) -> Any:
    """Reproduces the live MEDIUM UX finding (#219 review): two real Old Rag trails
    plus a handful of unrelated "Old X Road" trails that a naive per-token fuzzy OR
    match pulled in as weak noise ("old" fuzzily/exactly matching every one of them).
    A search for "old rag" must resolve to the two real trails and reject the rest."""
    seed = client.scoped_session("seed")
    real = [
        ("ct:old-rag-loop", "Old Rag Loop", 38.5519, -78.2861),
        ("ct:old-rag-fire-road", "Old Rag Fire Road", 38.5601, -78.2799),
    ]
    noise = [
        ("ct:old-craig-road", "Old Craig Road", 38.61, -78.31),
        ("ct:old-drowning-ford-road", "Old Drowning Ford Road", 38.44, -78.19),
        ("ct:old-shawl-pond-road", "Old Shawl Pond Road", 38.50, -78.22),
        ("ct:rin-ran-farm", "Rin-Ran Farm", 38.02, -78.47),
        ("ct:van-tol-road", "Van Tol Road", 37.98, -78.50),
    ]
    for canonical_id, name, lat, lon in real + noise:
        seed.run(
            (
                "CREATE (:CanonicalTrail {canonical_id: $cid, name: $name, "
                "point: point({latitude: $lat, longitude: $lon})})",
                {"cid": canonical_id, "name": name, "lat": lat, "lon": lon},
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


def test_fulltext_query_old_rag_rejects_weak_fuzzy_noise(clean_graph: Any) -> None:
    # MEDIUM UX finding on #219: "old rag" used to return 10 hits (7 weak-fuzzy
    # noise) against a corpus like this. The relevance floor + AND-required tokens
    # must now return exactly the real Old Rag trails and reject the noise trails —
    # including the ones that only fuzzy/partially matched "old" or "rag" alone.
    _seed_old_rag_and_noise(clean_graph)
    seed = clean_graph.scoped_session("reader")

    rows = seed.run(queries.candidate_trails_by_name("old rag", 10))
    ids = {r["canonical_id"] for r in rows}
    assert ids == {"ct:old-rag-loop", "ct:old-rag-fire-road"}


def test_scout_by_name_old_rag_rejects_weak_fuzzy_noise(clean_graph: Any) -> None:
    # Same scenario through the full scout_by_name path (dedupe + Candidate mapping),
    # proving the fix holds at the layer the API actually calls.
    _seed_old_rag_and_noise(clean_graph)
    session = clean_graph.scoped_session("reader")

    out = scout_by_name("old rag", session)
    ids = {c.canonical_id for c in out}
    assert ids == {"ct:old-rag-loop", "ct:old-rag-fire-road"}
    assert "ct:old-craig-road" not in ids
    assert "ct:rin-ran-farm" not in ids


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
