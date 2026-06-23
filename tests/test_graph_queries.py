"""Tests for the scoped query builders (pure; no database)."""

from __future__ import annotations

from graph import queries


def test_candidate_query_shape() -> None:
    cypher, params = queries.candidate_trails_near(38.5, -78.4, 40_000, 5)
    assert "ACCESSES" in cypher
    assert "point.distance" in cypher
    assert "LIMIT $k" in cypher
    assert params["origin"] == {"latitude": 38.5, "longitude": -78.4}
    assert params["radius_m"] == 40_000
    assert params["k"] == 5


def test_personal_query_is_owner_scoped() -> None:
    # The access-control-at-query-layer invariant (#4): owned reads carry the scope.
    cypher, params = queries.episodes_on_trail("ct:old-rag-loop")
    assert "e.owner_id" in cypher
    assert "$viewer_id" in cypher
    assert "$granted_ids" in cypher
    assert params["canonical_id"] == "ct:old-rag-loop"


def test_owner_scope_clause() -> None:
    clause = queries.owner_scope("x")
    assert clause == "(x.owner_id = $viewer_id OR x.owner_id IN $granted_ids)"
