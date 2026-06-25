"""Tests for ingestion.ingest_episode — the create_episode transaction (Epic 010
+ Epic 011 S2). create_episode commits the Episode + wires + the de-identified
commons twin in ONE managed transaction via ScopedSession.execute_write, so the
tests drive a real ScopedSession (the owner-scope guard fires on each owned
statement) with a recording tx_runner and assert on the committed batch.

The structural privacy/unlinkability suite + atomic-rollback live in
tests/test_commons_privacy.py.

Test names follow: test_s{story}_{ac}_{description}
"""

from __future__ import annotations

from datetime import datetime

from graph.client import ScopedSession
from ingestion.ingest_episode import FITSummary, compute_pace_on_grade, create_episode
from orchestration.belief_update import BeliefUpdateQueue

_SALT = "test-salt-not-a-real-secret"


def _track(n: int = 30, step_lon: float = 0.0006) -> list[tuple[float, float]]:
    return [(38.5, -78.40 + i * step_lon) for i in range(n)]


def _summary() -> FITSummary:
    return FITSummary(
        watch_activity_id="garmin:act-1",
        total_distance_m=15000.0,
        total_ascent_m=735.0,
        total_descent_m=735.0,
        moving_time_s=10800.0,
        total_time_s=12000.0,
        avg_heart_rate=140,
        start_lat=38.5,
        start_lon=-78.40,
        end_lat=38.5,
        end_lon=-78.40 + 29 * 0.0006,
        sport="hiking",
        start_time=datetime(2026, 6, 24, 9, 0, 0),
        gps_track=_track(),
    )


def _tx_session(owner: str = "mem:josh") -> tuple[ScopedSession, list[list[tuple[str, dict]]]]:
    """A real ScopedSession (guard active) whose tx_runner records each committed
    transaction batch as a list of (cypher, merged_params)."""
    batches: list[list[tuple[str, dict]]] = []

    def runner(cypher: str, params: dict):
        return []

    def tx_runner(merged: list[tuple[str, dict]]):
        batches.append(list(merged))

    return ScopedSession(owner, [], runner, tx_runner), batches


def _cyphers(batch: list[tuple[str, dict]]) -> list[str]:
    return [c for c, _ in batch]


def _stmt(batch: list[tuple[str, dict]], needle: str) -> tuple[str, dict]:
    hits = [(c, p) for c, p in batch if needle in c]
    assert len(hits) == 1, f"expected exactly one statement containing {needle!r}, got {len(hits)}"
    return hits[0]


# ── S2 — one managed transaction: Episode + wires + severed commons twin ──────


def test_s2_ac0_four_writes_in_one_transaction() -> None:
    """AC-2.0: the Episode MERGE, Person-DID, Episode-ON, and the
    :CommonsObservation CREATE commit together in ONE transaction."""
    session, batches = _tx_session()
    eid = create_episode(_summary(), "ct:old-rag-loop", "mem:josh", session, commons_salt=_SALT)
    assert eid == "ep:mem:josh:garmin:act-1"
    assert len(batches) == 1  # exactly one managed transaction, not 4 auto-commits
    batch = batches[0]
    assert len(batch) == 4
    cy = _cyphers(batch)
    assert any("MERGE (e:Episode {episode_id: $eid, owner_id: $viewer_id})" in c for c in cy)
    assert any(":DID]->(e)" in c for c in cy)
    assert any(":ON]->(t)" in c for c in cy)
    assert any("CREATE (co:CommonsObservation" in c for c in cy)


def test_s2_unmatched_trail_skips_on_wire_keeps_fork() -> None:
    """With no matched trail: no Episode-ON wire, but the fork still fires with a
    null trail_id (a contribution is never lost for lack of a trail match)."""
    session, batches = _tx_session()
    create_episode(_summary(), None, "mem:josh", session, commons_salt=_SALT)
    batch = batches[0]
    assert not any(":ON]->(t)" in c for c in _cyphers(batch))
    co_cypher, co_params = _stmt(batch, "CommonsObservation")
    assert co_params["trail_id"] is None  # AC-2.4: null when unmatched


def test_s2_no_salt_skips_commons_fork() -> None:
    """No writer salt → the fork is skipped (degrade); episode writes still commit."""
    session, batches = _tx_session()
    create_episode(_summary(), "ct:x", "mem:josh", session)  # no commons_salt
    batch = batches[0]
    assert not any("CommonsObservation" in c for c in _cyphers(batch))
    assert len(batch) == 3  # Episode + DID + ON


def test_s2_ac2_commons_observation_is_unowned_and_severed() -> None:
    """AC-2.2/2.3: the commons CREATE has no owner_id, no $viewer_id reference, and
    no relationship syntax — born severed, unowned by construction."""
    session, batches = _tx_session()
    create_episode(_summary(), "ct:old-rag-loop", "mem:josh", session, commons_salt=_SALT)
    co_cypher, _ = _stmt(batches[0], "CommonsObservation")
    assert "owner_id" not in co_cypher
    assert "$viewer_id" not in co_cypher  # the injected viewer is never written onto it
    for edge in ("-[", "]->", "<-[", "]-(", ")-(", ")<-"):
        assert edge not in co_cypher  # zero relationships of any kind


def test_s2_ac4_trail_id_is_scalar_equal_to_matched_canonical_id() -> None:
    """AC-2.4: trail_id equals the matched canonical_id, stored as a scalar (the
    same value passed to the Episode-ON wire), with no CommonsObservation→trail
    edge created."""
    session, batches = _tx_session()
    create_episode(_summary(), "ct:old-rag-loop", "mem:josh", session, commons_salt=_SALT)
    _, co_params = _stmt(batches[0], "CommonsObservation")
    assert co_params["trail_id"] == "ct:old-rag-loop"
    co_cypher, _ = _stmt(batches[0], "CommonsObservation")
    assert "CanonicalTrail" not in co_cypher  # no edge/match to the trail node


# ── S3 — the full track never reaches the Episode; only the trimmed twin ──────


def test_s3_ac0_full_track_never_on_the_episode() -> None:
    """AC-3.0: the Episode carries no full polyline (Rule #3); only the commons
    twin gets the endpoint-trimmed track."""
    session, batches = _tx_session()
    create_episode(_summary(), "ct:old-rag-loop", "mem:josh", session, commons_salt=_SALT)
    batch = batches[0]
    _, ep_params = _stmt(batch, "MERGE (e:Episode")
    assert "gps_track" not in ep_params
    # no polyline among the Episode's domain params (granted_ids is injected scope)
    domain = {k: v for k, v in ep_params.items() if k not in ("viewer_id", "granted_ids")}
    assert not any(isinstance(v, list) for v in domain.values())
    _, co_params = _stmt(batch, "CommonsObservation")
    assert co_params["trimmed_track"].startswith("LINESTRING(")
    # the trim fired: the raw start coordinate is not in the trimmed linestring
    assert "-78.4 38.5" not in co_params["trimmed_track"]


# ── S6 — the write fires regardless of commons_opt_in ─────────────────────────


def test_s6_ac2_fork_fires_regardless_of_opt_in() -> None:
    """AC-6.2: create_episode never reads commons_opt_in — the unlinkable write
    fires for every episode; opt-in gates Stage-9 exposure, not the write."""
    session, batches = _tx_session()
    create_episode(_summary(), "ct:x", "mem:josh", session, commons_salt=_SALT)
    all_cypher = " ".join(_cyphers(batches[0]))
    assert "commons_opt_in" not in all_cypher  # the write path never consults the flag
    assert any("CommonsObservation" in c for c in _cyphers(batches[0]))


# ── S2 — end-to-end enqueue → drain reproduces the Epic-001 belief state ───────


def test_s2_ac5_end_to_end_ingest_then_drain() -> None:
    """AC-2.5: create_episode enqueues; the queue drains through a per-owner
    scoped-session factory; the resulting belief writes reproduce the Epic-001
    pace/belief/maxima state."""
    session, _ = _tx_session()
    queue = BeliefUpdateQueue()
    create_episode(_summary(), "ct:x", "mem:josh", session, belief_queue=queue, commons_salt=_SALT)
    assert queue.size() == 1

    drain_writes: list[tuple[str, dict]] = []

    def factory(owner: str) -> ScopedSession:
        def runner(cypher: str, params: dict):
            drain_writes.append((cypher, params))
            return []  # first episode → no existing profile

        return ScopedSession(owner, [], runner)  # belief writes use run_write only

    assert queue.drain(factory) == 1

    expected_pace = compute_pace_on_grade(_summary())
    assert expected_pace is not None
    pace = [p for c, p in drain_writes if "MERGE (pp:PhysicalProfile" in c and "pace_on_grade" in c]
    assert pace and pace[0]["pace"] == expected_pace
    belief = [p for c, p in drain_writes if "MERGE (b:Belief" in c]
    assert belief and belief[0]["value"] == str(round(expected_pace, 1))
    assert belief[0]["bid"] == "belief:mem:josh:pace_on_grade_moderate"
    assert any("max_distance_m" in c for c, _ in drain_writes)
