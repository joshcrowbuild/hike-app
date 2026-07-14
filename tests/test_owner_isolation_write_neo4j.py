"""Epic 015 S4 — write isolation (Rule #4 extended to writes, Epic 011) on a live Neo4j.

A's scoped writes can only create/own A's nodes; a statement that would write an owned
node without an A-scoped owner clause is rejected by `assert_scoped_write` before it ever
reaches the database; and B's scoped session can never read A's newly-written nodes. This
round-trips the real `ScopedSession.run_write` guard + real Cypher, not a Cypher-string
assertion.
"""

from __future__ import annotations

from typing import Any

import pytest

from graph import queries
from graph.queries import UnscopedWriteError

pytestmark = pytest.mark.neo4j

A = "mem:iso-a"
B = "mem:iso-b"


def test_s4_ac1_owned_write_persists_with_viewer_owner(clean_graph: Any) -> None:
    """AC-4.1: A's run_write of an owned node persists with owner_id == A, read back."""
    client = clean_graph
    client.scoped_session(A).run_write(queries.upsert_physical_profile_pace(13.5))

    rows = client.scoped_session(A).run(
        (
            "MATCH (pp:PhysicalProfile) WHERE pp.owner_id = $viewer_id "
            "RETURN pp.owner_id AS owner_id, pp.pace_on_grade AS pace",
            {},
        )
    )
    assert len(rows) == 1 and rows[0]["owner_id"] == A and rows[0]["pace"] == 13.5


def test_s4_ac2_unscoped_owned_write_rejected_before_db(clean_graph: Any) -> None:
    """AC-4.2: a MERGE/SET of an owned label WITHOUT an A-scoped owner clause is rejected by
    assert_scoped_write (raises) before the runner is called — so no cross-owner write reaches
    the DB. Here A tries to mint an Episode owned by B; the guard fires and nothing persists."""
    client = clean_graph
    sneaky = (
        "MERGE (e:Episode {episode_id: 'ep:sneaky'}) SET e.owner_id = $foreign",
        {"foreign": B},
    )
    with pytest.raises(UnscopedWriteError):
        client.scoped_session(A).run_write(sneaky)

    # Verification read scans :Episode across all owners to confirm nothing persisted;
    # it is an intentional unscoped owned read, so it opts through the explicit bypass.
    leftovers = client.scoped_session(A).run(
        ("MATCH (e:Episode {episode_id: 'ep:sneaky'}) RETURN e.owner_id AS owner_id", {}),
        allow_unscoped_owned_read=True,
    )
    assert leftovers == []  # the guard fired before the runner — nothing was written


def test_s4_ac3_other_owner_cannot_read_a_writes(clean_graph: Any) -> None:
    """AC-4.3: after A's writes, B's scoped session cannot see A's newly-written owned nodes."""
    client = clean_graph
    client.scoped_session(A).run_write(queries.upsert_physical_profile_pace(13.5))
    client.scoped_session(A).run_write(queries.upsert_stated_belief(f"belief:{A}:pref", "A only"))

    assert client.scoped_session(B).run(queries.physical_profile_pace_read()) == []
    b_beliefs = client.scoped_session(B).run(
        ("MATCH (b:Belief) WHERE b.owner_id = $viewer_id RETURN b.belief_id AS id", {})
    )
    assert b_beliefs == []  # B sees none of A's beliefs
