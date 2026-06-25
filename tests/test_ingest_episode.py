"""Tests for ingestion.ingest_episode — the scoped-write routing (Epic 011 S2).

create_episode + the belief drain go through `ScopedSession.run_write`, so the
tests drive a **real** ScopedSession over a recording runner: the guard actually
fires, proving every owned write create_episode issues carries an owner-scope
clause (AC-2.2), and an end-to-end enqueue→drain reproduces the Epic-001 belief
state (AC-2.5).

Test names follow: test_s{story}_{ac}_{description}
"""

from __future__ import annotations

from graph.client import ScopedSession
from ingestion.ingest_episode import FITSummary, compute_pace_on_grade, create_episode
from orchestration.belief_update import BeliefUpdateQueue


def _summary() -> FITSummary:
    return FITSummary(
        watch_activity_id="garmin:act-1",
        total_distance_m=15000.0,
        total_ascent_m=800.0,
        total_descent_m=800.0,
        moving_time_s=10800.0,  # 180 min
        total_time_s=12000.0,
        avg_heart_rate=140,
        start_lat=38.5,
        start_lon=-78.4,
        end_lat=38.5,
        end_lon=-78.4,
        sport="hiking",
    )


def _recording_session(owner: str) -> tuple[ScopedSession, list[tuple[str, dict]]]:
    """A real ScopedSession (guard active) over a runner that records calls."""
    calls: list[tuple[str, dict]] = []

    def runner(cypher: str, params: dict):
        calls.append((cypher, params))
        return []

    return ScopedSession(owner, [], runner), calls


# ── S2 — create_episode routes owned writes through the scoped-write seam ─────


def test_s2_ac2_create_episode_writes_pass_the_guard() -> None:
    """AC-2.2: the Episode MERGE + Person-DID + Episode-ON wires go through
    run_write — the real ScopedSession guard fires and none raises (each carries
    its owner-scope clause)."""
    session, calls = _recording_session("mem:josh")
    eid = create_episode(_summary(), "ct:old-rag-loop", "mem:josh", session)

    assert eid == "ep:mem:josh:garmin:act-1"  # viewer-namespaced id
    # Episode upsert pins owner in the MERGE key (foreign id can't re-own a node).
    ep_writes = [(c, p) for c, p in calls if "MERGE (e:Episode" in c]
    assert len(ep_writes) == 1
    cypher, merged = ep_writes[0]
    assert "MERGE (e:Episode {episode_id: $eid, owner_id: $viewer_id})" in cypher
    assert merged["viewer_id"] == "mem:josh"
    assert "owner" not in merged  # no caller-supplied owner reaches the runner
    # both wires present
    assert any(":DID]->(e)" in c for c, _ in calls)
    assert any(":ON]->(t)" in c for c, _ in calls)


def test_s2_ac2_unmatched_trail_skips_on_wire() -> None:
    """AC-2.2: with no matched trail, the Episode-ON wire is not issued."""
    session, calls = _recording_session("mem:josh")
    create_episode(_summary(), None, "mem:josh", session)
    assert not any(":ON]->(t)" in c for c, _ in calls)
    assert any(":DID]->(e)" in c for c, _ in calls)  # DID still wired


# ── S2 — end-to-end enqueue → drain reproduces Epic-001 belief state ──────────


def test_s2_ac5_end_to_end_ingest_then_drain() -> None:
    """AC-2.5: create_episode enqueues, the queue drains through a per-owner
    scoped-session factory, and the resulting writes reproduce the Epic-001 state
    (EWMA pace upsert, capability Belief + provenance, maxima)."""
    session, _ = _recording_session("mem:josh")
    queue = BeliefUpdateQueue()
    create_episode(_summary(), "ct:old-rag-loop", "mem:josh", session, belief_queue=queue)
    assert queue.size() == 1

    drain_calls: list[tuple[str, dict]] = []

    def factory(owner: str) -> ScopedSession:
        def runner(cypher: str, params: dict):
            drain_calls.append((cypher, params))
            return []  # no existing profile → first-episode path

        return ScopedSession(owner, [], runner)

    assert queue.drain(factory) == 1

    expected_pace = compute_pace_on_grade(_summary())
    assert expected_pace is not None
    writes = [(c, p) for c, p in drain_calls]
    # pace upsert (first episode → pace passes through EWMA unchanged)
    pace = [p for c, p in writes if "MERGE (pp:PhysicalProfile" in c and "pace_on_grade" in c]
    assert pace and pace[0]["pace"] == expected_pace
    # capability belief written with the rounded pace, namespaced to the owner
    belief = [p for c, p in writes if "MERGE (b:Belief" in c]
    assert belief and belief[0]["value"] == str(round(expected_pace, 1))
    assert belief[0]["bid"] == "belief:mem:josh:pace_on_grade_moderate"
    # provenance + owner-scoped recount + ownership edge + maxima all fired
    assert any("DERIVED_FROM" in c for c, _ in writes)
    assert any("corroboration_n" in c and "count(e)" in c for c, _ in writes)
    assert any("ABOUT" in c for c, _ in writes)
    assert any("max_distance_m" in c for c, _ in writes)
