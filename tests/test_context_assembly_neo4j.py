"""Epic 003 AC-3.2 — the 18-month retrieval window proven end-to-end on a live Neo4j.

Persists two Episodes via the real write builders (one recent, one >18 months old) with
e.date set, wires them to a trail under the viewer's Person, then asserts
fetch_relevant_episodes returns only the recent one. This is the E2E that was impossible
before Episode.date was written (R6/M1): the date filter matched nothing. Reuses the
live-Neo4j fixtures from Epic 015 (tests/conftest.py).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest

from graph import queries
from orchestration.context_assembly import fetch_relevant_episodes

pytestmark = pytest.mark.neo4j

VIEWER = "mem:ctx-josh"
TRAIL = "ct:ctx-trail"


def _seed_episode(client: Any, eid: str, episode_date: str) -> None:
    session = client.scoped_session(VIEWER)
    session.run_write(
        queries.upsert_episode(
            eid,
            watch_activity_id=f"act:{eid}",
            source="test",
            distance_m=12000.0,
            ascent_m=600.0,
            descent_m=600.0,
            moving_min=120.0,
            duration_min=130.0,
            avg_heart_rate=140,
            pace_on_grade=14.0,
            now="2026-06-26T00:00:00+00:00",
            start_date=episode_date,
        )
    )
    session.run_write(queries.wire_person_did_episode(eid))
    session.run_write(queries.wire_episode_on_trail(eid, TRAIL))


def test_s3_ac2_date_window_returns_recent_excludes_old(clean_graph: Any) -> None:
    """AC-3.2 end-to-end: a 30-day-old episode is returned; a 700-day-old one (>18 months)
    is excluded — proving e.date is written and the `e.date >= $cutoff` filter works against
    a real Neo4j."""
    client = clean_graph
    # the (p:Person)-[:DID]->(e:Episode)-[:ON]->(t:CanonicalTrail) anchors must exist
    client.scoped_session(VIEWER).run(
        ("MERGE (t:CanonicalTrail {canonical_id: $cid}) SET t.name = 'Ctx Trail'", {"cid": TRAIL})
    )
    client.scoped_session(VIEWER).run(("MERGE (p:Person {member_id: $viewer_id})", {}))

    recent = (date.today() - timedelta(days=30)).isoformat()
    old = (date.today() - timedelta(days=700)).isoformat()  # beyond the 18-month window
    _seed_episode(client, "ep:recent", recent)
    _seed_episode(client, "ep:old", old)

    rows = fetch_relevant_episodes(VIEWER, [TRAIL], client.scoped_session(VIEWER).run)
    assert len(rows) == 1, [(r.get("trail_name"), str(r.get("date"))) for r in rows]
    assert str(rows[0]["date"]) == recent  # only the in-window episode survives the filter


def test_s3_ac2_undated_episode_is_excluded_from_window(clean_graph: Any) -> None:
    """An episode written with no start_date (e.date null) is simply absent from the recency
    window — null-safe, no crash."""
    client = clean_graph
    client.scoped_session(VIEWER).run(
        ("MERGE (t:CanonicalTrail {canonical_id: $cid}) SET t.name = 'Ctx Trail'", {"cid": TRAIL})
    )
    client.scoped_session(VIEWER).run(("MERGE (p:Person {member_id: $viewer_id})", {}))
    _seed_episode(client, "ep:undated", None)  # type: ignore[arg-type]

    rows = fetch_relevant_episodes(VIEWER, [TRAIL], client.scoped_session(VIEWER).run)
    assert rows == []  # null e.date never satisfies e.date >= $cutoff
