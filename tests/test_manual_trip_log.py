"""Epic 042 — manual trip log: the backend half (S2 Episode shape, S3 belief rules).

Test names: test_e042_s{story}_ac{n}_{description}; ACs from
docs/epics/epic-042-manual-trip-log.md. The S1 ACs are frontend-only and are proven
in frontend/src/screens/Detail.test.tsx.

Hermetic: fake scoped sessions record reads/writes and run the REAL owned-write guard
(`assert_scoped_write`) on every statement, as tests/test_outcome.py does.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from graph.queries import assert_scoped_write
from orchestration.belief_update import (
    BeliefUpdateQueue,
    UpdateTask,
    process_episode,
    update_beliefs,
)
from orchestration.episode_create import ManualEpisodeRequest, create_manual_episode
from orchestration.outcome import OutcomeRequest, write_outcome

# ── helpers ───────────────────────────────────────────────────────────────────


class _EpisodeWriteSession:
    """Records the manual-episode write batch (guarded like the real seam)."""

    def __init__(self) -> None:
        self.writes: list[tuple[str, dict[str, Any]]] = []

    def execute_write(self, batch: Sequence[tuple[str, dict[str, Any]]]) -> None:
        for cypher, params in batch:
            assert_scoped_write(cypher)
            self.writes.append((cypher, params))


class _OutcomeSession:
    """Fake ScopedSession for write_outcome: the ownership read returns the Episode's
    `source`; writes are guarded and flattened."""

    def __init__(self, episode_source: str | None) -> None:
        self.episode_source = episode_source
        self.writes: list[tuple[str, dict[str, Any]]] = []

    def run(self, query: tuple[str, dict[str, Any]]) -> list[dict[str, Any]]:
        _cypher, params = query
        return [{"episode_id": params["eid"], "source": self.episode_source}]

    def execute_write(self, batch: Sequence[tuple[str, dict[str, Any]]]) -> None:
        for cypher, params in batch:
            assert_scoped_write(cypher)
            self.writes.append((cypher, params))


class _CapabilitySession:
    """Records every read/write a belief update would issue."""

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or []
        self.reads: list[tuple[str, dict[str, Any]]] = []
        self.writes: list[tuple[str, dict[str, Any]]] = []

    def run(self, query: tuple[str, dict[str, Any]]) -> list[dict[str, Any]]:
        self.reads.append(query)
        return self.rows

    def run_write(self, query: tuple[str, dict[str, Any]]) -> list[dict[str, Any]]:
        self.writes.append(query)
        return []


def _manual_episode_params() -> dict[str, Any]:
    session = _EpisodeWriteSession()
    req = ManualEpisodeRequest(
        client_episode_id="manual-20261113-abc",
        canonical_id="stony-man",
        start_date="2026-11-13",
    )
    create_manual_episode("sub-josh", req, session)
    (params,) = [p for c, p in session.writes if "MERGE (e:Episode" in c]
    return params


# ── S2 — Episode created from a manual log ────────────────────────────────────


def test_e042_s2_ac2_1_episode_created_via_upsert_episode_path() -> None:
    """AC-2.1: the Episode is written by the existing `upsert_episode` builder, owner
    pinned in the MERGE key, in the one scoped batch with the Person + trail wiring."""
    session = _EpisodeWriteSession()
    req = ManualEpisodeRequest(client_episode_id="manual-20261113-abc", canonical_id="stony-man")
    create_manual_episode("sub-josh", req, session)
    cyphers = [c for c, _ in session.writes]
    assert any("MERGE (e:Episode {episode_id: $eid, owner_id: $viewer_id})" in c for c in cyphers)
    assert any("MERGE (e)-[:ON]->(t)" in c for c in cyphers)


def test_e042_s2_ac2_2_episode_source_is_manual_with_todays_date() -> None:
    """AC-2.2: source is 'manual' (the default, never 'watch'/'import') and the date the
    client supplied lands as the Episode's start_date."""
    params = _manual_episode_params()
    assert params["source"] == "manual"
    assert params["start_date"] == "2026-11-13"
    assert params["eid"] == "ep:sub-josh:manual-20261113-abc"


def test_e042_s2_ac2_3_measured_fields_are_null_never_fabricated() -> None:
    """AC-2.3: a bare manual log stores NO measured value — null, not 0."""
    params = _manual_episode_params()
    for field in ("distance", "ascent", "descent", "moving_min", "duration_min", "hr", "pace"):
        assert params[field] is None, field


def test_e042_s2_ac2_1_same_client_id_is_the_same_episode() -> None:
    """The idempotency the UI relies on: re-submitting the same client_episode_id (trail +
    local date) addresses the same Episode id, so the MERGE dedupes instead of doubling."""
    a = _manual_episode_params()
    b = _manual_episode_params()
    assert a["eid"] == b["eid"]


# ── S3 — manual outcomes and the belief pipeline ──────────────────────────────


def test_e042_s3_ac3_1_manual_outcome_feeds_preference_pipeline_like_watch() -> None:
    """AC-3.1: a positive manual outcome enqueues the same preference check a watch
    outcome does, and writes the same stated preference belief when a statement is given."""
    answer = "Loved the long views"
    results = {}
    for source in ("manual", "watch"):
        session = _OutcomeSession(source)
        queue = BeliefUpdateQueue()
        req = OutcomeRequest(overall=3, delta_answer=answer, skipped=False)
        write_outcome("ep:sub-josh:e1", "sub-josh", req, session, belief_queue=queue)
        beliefs = [(c, p) for c, p in session.writes if "MERGE (b:Belief" in c]
        assert len(beliefs) == 1, source
        assert "'stated_preference'" in beliefs[0][0]
        assert beliefs[0][1]["value"] == answer
        assert queue.size() == 1, source  # the preference check is queued either way
        results[source] = beliefs[0][1]["bid"]
    assert results["manual"] == results["watch"]  # same belief identity, same pipeline


def test_e042_s3_ac3_2_manual_outcome_does_not_update_capability_beliefs() -> None:
    """AC-3.2: draining a manual outcome's queued task issues no read or write at all —
    no pace belief, no PhysicalProfile maxima."""
    session = _OutcomeSession("manual")
    queue = BeliefUpdateQueue()
    write_outcome(
        "ep:sub-josh:e1", "sub-josh", OutcomeRequest(overall=3), session, belief_queue=queue
    )
    assert queue.size() == 1
    cap = _CapabilitySession()
    assert queue.drain(lambda _owner: cap) == 1
    assert cap.reads == [] and cap.writes == []


def test_e042_s3_ac3_2_manual_task_never_touches_capability_even_with_numbers() -> None:
    """AC-3.2 hardened: even if a manual Episode carries a distance/ascent/pace (the
    POST /episode body allows them), update_beliefs refuses every capability write."""
    task = UpdateTask("ep:j:1", "j", 15000.0, 800.0, 14.5, source="manual")
    cap = _CapabilitySession()
    update_beliefs(task, cap)
    assert cap.writes == []
    assert cap.reads == []


def test_e042_s3_ac3_2_process_episode_reads_source_and_skips_manual() -> None:
    """AC-3.2 on the re-derive path: process_episode takes `source` from the Episode row,
    so a manual Episode read back from the graph is also capability-inert."""
    cap = _CapabilitySession(
        [{"distance_m": 9000.0, "ascent_m": 400.0, "pace_on_grade": 11.0, "source": "manual"}]
    )
    process_episode("ep:j:1", "j", cap)
    assert cap.writes == []


def test_e042_s3_ac3_2_watch_episode_still_updates_capability() -> None:
    """Regression guard for the suppression: a watch Episode is unaffected."""
    task = UpdateTask("ep:j:2", "j", 15000.0, 800.0, 14.5, source="watch")
    cap = _CapabilitySession()
    update_beliefs(task, cap)
    assert any("Belief" in c for c, _ in cap.writes)


def test_e042_s3_ac3_3_manual_belief_carries_manual_outcome_provenance() -> None:
    """AC-3.3: the belief a manual outcome yields carries provenance 'manual_outcome'."""
    session = _OutcomeSession("manual")
    req = OutcomeRequest(overall=3, delta_answer="Prefer ridgelines", skipped=False)
    write_outcome("ep:sub-josh:e1", "sub-josh", req, session)
    ((cypher, params),) = [(c, p) for c, p in session.writes if "MERGE (b:Belief" in c]
    assert params["provenance"] == "manual_outcome"
    assert "b.provenance" in cypher


def test_e042_s3_ac3_3_watch_belief_is_not_labelled_manual() -> None:
    """The label is earned by the Episode's source, never applied to a watch outcome."""
    session = _OutcomeSession("watch")
    req = OutcomeRequest(overall=3, delta_answer="Prefer ridgelines", skipped=False)
    write_outcome("ep:sub-josh:e1", "sub-josh", req, session)
    ((_cypher, params),) = [(c, p) for c, p in session.writes if "MERGE (b:Belief" in c]
    assert params["provenance"] is None
