"""Tests for orchestration.belief_update — Epic 001.

Test names follow: test_s{story}_{ac}_{description}
All ACs from docs/epics/epic-001-belief-update-pipeline.md must have coverage here.
"""

from __future__ import annotations

import pytest

from orchestration.belief_update import (
    EWMA_ALPHA,
    PROMOTION_THRESHOLD,
    BeliefUpdateQueue,
    UpdateTask,
    ewma_pace,
    pace_confidence,
    update_beliefs,
)

# ── S2 — EWMA formula (pure function, no DB) ─────────────────────────────────


def test_s2_ac1_ewma_formula():
    """AC-2.1: alpha * new + (1-alpha) * current with alpha=0.3."""
    result = ewma_pace(current=15.0, new=12.0)
    assert result == pytest.approx(0.3 * 12.0 + 0.7 * 15.0)


def test_s2_ac2_ewma_first_episode_no_current():
    """AC-2.2: First episode — result equals new_pace directly."""
    assert ewma_pace(current=None, new=14.5) == 14.5


def test_s2_ac1_ewma_alpha_constant():
    """AC-2.1: EWMA_ALPHA module constant is 0.3."""
    assert EWMA_ALPHA == 0.3


# ── S5 — Confidence thresholds (pure function, no DB) ────────────────────────


def test_s5_ac1_confidence_corr1_is_provisional():
    """AC-5.1: confidence = 0.3 when corroboration_n = 1."""
    assert pace_confidence(1) < 0.4


def test_s5_ac2_confidence_corr2_still_provisional():
    """AC-5.2: confidence = 0.3 when corroboration_n = 2."""
    assert pace_confidence(2) < 0.4


def test_s5_ac3_confidence_corr3_crosses_floor():
    """AC-5.3: confidence >= 0.4 when corroboration_n = 3."""
    assert pace_confidence(3) >= 0.4


def test_s5_ac3_promotion_threshold_constant():
    """AC-5.3: PROMOTION_THRESHOLD module constant is 3."""
    assert PROMOTION_THRESHOLD == 3


# ── S1 — Queue mechanics ─────────────────────────────────────────────────────


def test_s1_ac1_enqueue_stores_task():
    """AC-1.1: queue.enqueue() places exactly one task."""
    q = BeliefUpdateQueue()
    task = UpdateTask("ep:josh:1", "josh", 15000.0, 800.0, 14.5)
    q.enqueue(task)
    assert q.size() == 1


def test_s1_ac2_enqueued_task_preserves_fields():
    """AC-1.2: enqueued task has correct owner_id and episode_id."""
    q = BeliefUpdateQueue()
    task = UpdateTask("ep:josh:1", "josh", 15000.0, 800.0, 14.5)
    q.enqueue(task)
    dequeued = q._dequeue()
    assert dequeued.owner_id == "josh"
    assert dequeued.episode_id == "ep:josh:1"


def test_s1_ac3_enqueue_with_none_pace():
    """AC-1.3: Task enqueued even when pace_on_grade is None."""
    q = BeliefUpdateQueue()
    task = UpdateTask("ep:josh:2", "josh", 10000.0, 500.0, None)
    q.enqueue(task)
    assert q.size() == 1


# ── S2–S5 integration via update_beliefs() with a fake ScopedSession ─────────
#
# Epic 011: the runner is now a ScopedSession (run for owner-scoped reads,
# run_write for guarded owned writes), not a bare list-appender (AC-2.5). The
# fake records both surfaces so we can assert routing as well as behaviour.


class _FakeSession:
    """Duck-typed ScopedSession: records run (reads) and run_write (writes)."""

    def __init__(self, rows_by_query: dict | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []  # everything, in order
        self.reads: list[tuple[str, dict]] = []
        self.writes: list[tuple[str, dict]] = []
        self._rows = rows_by_query or {}

    def _rows_for(self, cypher: str):
        for key, result in self._rows.items():
            if key in cypher:
                return result
        return []

    def run(self, query: tuple[str, dict]):
        cypher, params = query
        self.calls.append((cypher, params))
        self.reads.append((cypher, params))
        return self._rows_for(cypher)

    def run_write(self, query: tuple[str, dict]):
        cypher, params = query
        self.calls.append((cypher, params))
        self.writes.append((cypher, params))
        return self._rows_for(cypher)


def test_s2_ac4_none_pace_skips_pace_update():
    """AC-2.4: If task.pace_on_grade is None, no pace write is issued."""
    task = UpdateTask("ep:josh:1", "josh", 20000.0, 1000.0, None)
    session = _FakeSession()
    update_beliefs(task, session)
    pace_writes = [
        c
        for c, _ in session.writes
        if "pace_on_grade" in c and "MERGE" in c and "SET" in c and "max_" not in c
    ]
    assert len(pace_writes) == 0


def test_s2_ac1_pace_read_routes_through_run_not_run_write():
    """AC-2.1: the PhysicalProfile pace read goes through ScopedSession.run; the
    profile/belief writes go through run_write — reads and writes are separated."""
    task = UpdateTask("ep:josh:1", "josh", 15000.0, 800.0, 14.5)
    session = _FakeSession()
    update_beliefs(task, session)
    assert any("PhysicalProfile" in c and "RETURN" in c for c, _ in session.reads)
    assert not any("RETURN" in c for c, _ in session.writes)  # no reads on the write path
    assert any("MERGE (pp:PhysicalProfile" in c for c, _ in session.writes)


def test_s3_ac1_new_maximum_replaces_stored():
    """AC-3.1: A new maximum distance is passed to the maxima upsert."""
    task = UpdateTask("ep:josh:1", "josh", 25000.0, 1200.0, 14.5)
    session = _FakeSession({"pace_on_grade AS pace": [{"pace": 15.0, "count": 2}]})
    update_beliefs(task, session)
    max_calls = [(c, p) for c, p in session.writes if "max_distance_m" in c]
    assert len(max_calls) > 0
    _, params = max_calls[0]
    assert params.get("distance_m") == 25000.0


def test_s3_ac3_none_distance_does_not_overwrite():
    """AC-3.3: None values in the task do not overwrite existing maxima."""
    task = UpdateTask("ep:josh:1", "josh", None, None, 14.5)
    session = _FakeSession()
    update_beliefs(task, session)
    max_calls = [(c, p) for c, p in session.writes if "max_distance_m" in c]
    for _, params in max_calls:
        assert params.get("distance_m") is None or params.get("distance_m") == 0


def test_s4_ac4_belief_type_is_inferred():
    """AC-5.4: Belief.type is 'inferred' from an automatic update (in the Cypher)."""
    task = UpdateTask("ep:josh:1", "josh", 15000.0, 800.0, 14.5)
    session = _FakeSession()
    update_beliefs(task, session)
    belief_writes = [c for c, _ in session.writes if "MERGE (b:Belief" in c]
    assert len(belief_writes) > 0
    assert any("'inferred'" in c for c in belief_writes)


def test_s4_ac3_belief_about_edge():
    """AC-4.3: Belief is linked to Person via ABOUT edge."""
    task = UpdateTask("ep:josh:1", "josh", 15000.0, 800.0, 14.5)
    session = _FakeSession()
    update_beliefs(task, session)
    assert any("ABOUT" in c for c, _ in session.writes)


def test_s4_ac4_belief_derived_from_edge():
    """AC-4.4: Belief is linked to Episode via DERIVED_FROM edge."""
    task = UpdateTask("ep:josh:1", "josh", 15000.0, 800.0, 14.5)
    session = _FakeSession()
    update_beliefs(task, session)
    assert any("DERIVED_FROM" in c for c, _ in session.writes)


def test_m8_corroboration_recount_is_owner_scoped():
    """gap-audit M8: the corroboration recount counts only owner-scoped episodes
    (owner_scope on the DERIVED_FROM Episode), not every edge on the belief."""
    task = UpdateTask("ep:josh:1", "josh", 15000.0, 800.0, 14.5)
    session = _FakeSession()
    update_beliefs(task, session)
    recount = [c for c, _ in session.writes if "corroboration_n" in c and "count(e)" in c]
    assert len(recount) == 1
    assert "e.owner_id = $viewer_id" in recount[0]  # the M8 owner-scope


def test_s5_ac1_belief_confidence_on_first_episode():
    """AC-5.1: First episode belief has confidence < 0.4 (provisional)."""
    assert pace_confidence(1) < 0.4


def test_s5_ac3_belief_confidence_at_threshold():
    """AC-5.3: At corroboration_n=3, confidence crosses floor."""
    assert pace_confidence(3) >= 0.4
    assert pace_confidence(PROMOTION_THRESHOLD) >= 0.4


def test_s2_ac3_episode_count_incremented():
    """AC-2.3: PhysicalProfile.episode_count is incremented on the pace upsert."""
    task = UpdateTask("ep:josh:1", "josh", 15000.0, 800.0, 14.5)
    session = _FakeSession({"pace_on_grade AS pace": [{"pace": 15.0, "count": 2}]})
    update_beliefs(task, session)
    count_writes = [(c, p) for c, p in session.writes if "episode_count" in c and "SET" in c]
    assert len(count_writes) > 0


def test_s3_ac2_below_max_does_not_overwrite():
    """AC-3.2: A value below current maximum still passes (CASE WHEN guards it)."""
    task = UpdateTask("ep:josh:1", "josh", 10000.0, 400.0, 14.5)  # below any reasonable max
    session = _FakeSession()
    update_beliefs(task, session)
    max_calls = [(c, p) for c, p in session.writes if "max_distance_m" in c]
    assert len(max_calls) > 0
    _, params = max_calls[0]
    assert params["distance_m"] == 10000.0  # value passed; CASE WHEN in Cypher does comparison


def test_s4_ac1_corroboration_n_from_derived_from_count():
    """AC-4.1: corroboration_n is recomputed from the DERIVED_FROM edge count."""
    task = UpdateTask("ep:josh:1", "josh", 15000.0, 800.0, 14.5)
    session = _FakeSession()
    update_beliefs(task, session)
    recount = [c for c, _ in session.writes if "count(e)" in c and "DERIVED_FROM" in c]
    assert len(recount) > 0


def test_s4_ac2_belief_value_is_rounded_pace():
    """AC-4.2: Belief.value equals EWMA pace rounded to 1 decimal."""
    # pace = 14.567... should be stored as "14.6"
    task = UpdateTask("ep:josh:1", "josh", 15000.0, 800.0, 14.567)
    session = _FakeSession()
    update_beliefs(task, session)
    belief_writes = [(c, p) for c, p in session.writes if "MERGE (b:Belief" in c and "value" in p]
    assert len(belief_writes) > 0
    for _, params in belief_writes:
        val = params["value"]
        assert isinstance(val, str)
        parts = val.split(".")
        assert len(parts) <= 2
        if len(parts) == 2:
            assert len(parts[1]) <= 1


def test_s2_ac2_belief_id_namespaced_to_owner():
    """The belief_id (and thus all owned writes) is namespaced to the task owner,
    so a per-owner scoped session writes a consistently-owned node."""
    task = UpdateTask("ep:carter:9", "carter", 15000.0, 800.0, 14.5)
    session = _FakeSession()
    update_beliefs(task, session)
    belief_writes = [p for c, p in session.writes if "Belief" in c]
    assert belief_writes
    assert all(p.get("bid", "").startswith("belief:carter:") for p in belief_writes if "bid" in p)


def test_s2_ac1_ewma_with_real_numbers():
    """AC-2.1: Verify EWMA with multiple episodes converges correctly."""
    pace = ewma_pace(None, 16.0)  # first episode
    pace = ewma_pace(pace, 14.0)  # second — should pull toward 14
    pace = ewma_pace(pace, 14.0)  # third
    # After 3 episodes at 14.0, should be significantly below 16.0
    assert pace < 15.5
    assert pace > 13.5
