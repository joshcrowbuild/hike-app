"""Epic 015 S3 — read isolation (Rule #4) proven end-to-end against a live Neo4j.

Members A and B each own an :Episode / :Belief / :PhysicalProfile (distinct owner_id).
A's owner-scoped reads — authored in `graph.queries` and run through `ScopedSession.run`
— return only A's nodes; an UNSCOPED read of the same label returns BOTH owners' nodes,
proving the scope clause (not the mere absence of B's data) is what provides isolation
(AC-3.3 falsifiability). This is the first test that round-trips a real driver + real
Cypher; the unit suite only asserts on Cypher strings with a fake session.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from graph import queries
from graph.queries import UnscopedReadError

pytestmark = pytest.mark.neo4j

A = "mem:iso-a"
B = "mem:iso-b"


def _seed_owned_nodes(client: Any, owner: str, *, pace: float, eid: str, belief_value: str) -> None:
    """Seed one owner's :Episode + :PhysicalProfile + :Belief through the scoped-write seam."""
    session = client.scoped_session(owner)
    now = datetime.now(timezone.utc).isoformat()
    session.run_write(
        queries.upsert_episode(
            eid,
            watch_activity_id=f"act:{owner}",
            source="test",
            distance_m=10000.0,
            ascent_m=500.0,
            descent_m=500.0,
            moving_min=100.0,
            duration_min=110.0,
            avg_heart_rate=140,
            pace_on_grade=pace,
            now=now,
        )
    )
    session.run_write(queries.upsert_physical_profile_pace(pace))
    session.run_write(queries.upsert_stated_belief(f"belief:{owner}:pref", belief_value))


def test_s3_ac1_scoped_read_returns_owner_nodes(clean_graph: Any) -> None:
    """AC-3.1: A's owner-scoped reads return A's owned nodes."""
    client = clean_graph
    _seed_owned_nodes(client, A, pace=11.0, eid="ep:a:1", belief_value="A loves ridges")
    _seed_owned_nodes(client, B, pace=22.0, eid="ep:b:1", belief_value="B loves valleys")

    a_profile = client.scoped_session(A).run(queries.physical_profile_pace_read())
    assert len(a_profile) == 1 and a_profile[0]["pace"] == 11.0
    a_episode = client.scoped_session(A).run(queries.episode_fields_read("ep:a:1"))
    assert len(a_episode) == 1


def test_s3_ac2_scoped_read_excludes_other_owner(clean_graph: Any) -> None:
    """AC-3.2: A's owner-scoped reads return NONE of B's owned nodes — even when A asks for
    B's exact episode id, the owner_scope WHERE clause filters it out."""
    client = clean_graph
    _seed_owned_nodes(client, A, pace=11.0, eid="ep:a:1", belief_value="A")
    _seed_owned_nodes(client, B, pace=22.0, eid="ep:b:1", belief_value="B")

    a_profile = client.scoped_session(A).run(queries.physical_profile_pace_read())
    assert all(r["pace"] != 22.0 for r in a_profile)  # B's pace never appears

    b_episode_via_a = client.scoped_session(A).run(queries.episode_fields_read("ep:b:1"))
    assert b_episode_via_a == []  # B's episode is invisible to A even by exact id


def test_s3_ac3_unscoped_read_leaks_both_owners(clean_graph: Any) -> None:
    """AC-3.3 (falsifiability): an UNSCOPED read of :PhysicalProfile returns BOTH A's and B's
    nodes — proving the owner-scope clause in the `graph.queries` builder is what provides
    isolation. If owner_scope were removed from `physical_profile_pace_read`, AC-3.2 would
    start returning B's node; this affirms the data is present and only the clause hides it.
    The scoped builder is the only sanctioned reader; this raw query is the deliberate
    counter-example that earns the scope clause its keep.

    The owned-read guard now REFUSES this exact unscoped read (see
    `test_read_guard_refuses_unscoped_owned_read_at_the_seam`), so the counter-example
    must opt out through the explicit `allow_unscoped_owned_read=True` bypass — the
    intended, review-visible escape hatch for a deliberate cross-owner read."""
    client = clean_graph
    _seed_owned_nodes(client, A, pace=11.0, eid="ep:a:1", belief_value="A")
    _seed_owned_nodes(client, B, pace=22.0, eid="ep:b:1", belief_value="B")

    leaked = client.scoped_session(A).run(
        ("MATCH (pp:PhysicalProfile) RETURN pp.owner_id AS owner_id", {}),
        allow_unscoped_owned_read=True,
    )
    assert {r["owner_id"] for r in leaked} == {A, B}  # both owners leak through the unscoped read

    scoped = client.scoped_session(A).run(queries.physical_profile_pace_read())
    assert len(scoped) == 1  # the scoped builder, by contrast, returns only A's


def test_read_guard_refuses_unscoped_owned_read_at_the_seam(clean_graph: Any) -> None:
    """The owned-read guard BITES on a live driver: the same all-owners :PhysicalProfile
    scan that AC-3.3 proves would leak BOTH owners is now REFUSED by `ScopedSession.run` —
    it raises UnscopedReadError before the query reaches Neo4j (fail closed). The explicit
    bypass is the only way through, and with it the read returns both owners — proving the
    data is genuinely present and it is the guard, not empty data, that blocks the leak."""
    client = clean_graph
    _seed_owned_nodes(client, A, pace=11.0, eid="ep:a:1", belief_value="A")
    _seed_owned_nodes(client, B, pace=22.0, eid="ep:b:1", belief_value="B")

    leak = ("MATCH (pp:PhysicalProfile) RETURN pp.owner_id AS owner_id", {})
    with pytest.raises(UnscopedReadError):
        client.scoped_session(A).run(leak)  # no bypass → fail closed, never hits the DB

    leaked = client.scoped_session(A).run(leak, allow_unscoped_owned_read=True)
    assert {r["owner_id"] for r in leaked} == {A, B}  # bypass runs it; data was really there
