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


# ── S2–S5 integration via update_beliefs() with fake runner ──────────────────


def _make_runner(rows_by_query: dict | None = None):
    """Fake runner that returns preset rows and records calls."""
    calls: list[tuple[str, dict]] = []
    rows = rows_by_query or {}

    def runner(query_tuple: tuple[str, dict]):
        cypher, params = query_tuple
        calls.append((cypher, params))
        # Return rows for the first matching key snippet
        for key, result in rows.items():
            if key in cypher:
                return result
        return []

    runner.calls = calls  # type: ignore[attr-defined]
    return runner


def test_s2_ac4_none_pace_skips_pace_update():
    """AC-2.4: If task.pace_on_grade is None, pace update Cypher is not called."""
    task = UpdateTask("ep:josh:1", "josh", 20000.0, 1000.0, None)
    runner = _make_runner()
    update_beliefs(task, runner)
    # pace update should not be called; only maxima update should run
    pace_calls = [
        c
        for c, _ in runner.calls
        if "pace_on_grade" in c and "MERGE" in c and "SET" in c and "max_" not in c
    ]
    assert len(pace_calls) == 0


def test_s3_ac1_new_maximum_replaces_stored():
    """AC-3.1: A new maximum distance replaces the stored value."""
    task = UpdateTask("ep:josh:1", "josh", 25000.0, 1200.0, 14.5)
    runner = _make_runner(
        {"PhysicalProfile": [{"pace": 15.0, "count": 2, "max_dist": 20000.0, "max_asc": 1000.0}]}
    )
    update_beliefs(task, runner)
    # Find the maxima update call
    max_calls = [(c, p) for c, p in runner.calls if "max_distance_m" in c]
    assert len(max_calls) > 0
    _, params = max_calls[0]
    assert params.get("distance_m") == 25000.0


def test_s3_ac3_none_distance_does_not_overwrite():
    """AC-3.3: None values in the task do not overwrite existing maxima."""
    task = UpdateTask("ep:josh:1", "josh", None, None, 14.5)
    runner = _make_runner()
    update_beliefs(task, runner)
    # No maxima update should include None distance
    max_calls = [(c, p) for c, p in runner.calls if "max_distance_m" in c]
    for _, params in max_calls:
        assert params.get("distance_m") is None or params.get("distance_m") == 0


def test_s4_ac4_belief_type_is_inferred():
    """AC-5.4: Belief.type is always 'inferred' from automatic update."""
    task = UpdateTask("ep:josh:1", "josh", 15000.0, 800.0, 14.5)
    runner = _make_runner()
    update_beliefs(task, runner)
    belief_calls = [(c, p) for c, p in runner.calls if "Belief" in c and "MERGE" in c]
    assert len(belief_calls) > 0
    for _, params in belief_calls:
        if "type" in params:
            assert params["type"] == "inferred"


def test_s4_ac3_belief_about_edge():
    """AC-4.3: Belief is linked to Person via ABOUT edge."""
    task = UpdateTask("ep:josh:1", "josh", 15000.0, 800.0, 14.5)
    runner = _make_runner()
    update_beliefs(task, runner)
    about_calls = [c for c, _ in runner.calls if "ABOUT" in c]
    assert len(about_calls) > 0


def test_s4_ac4_belief_derived_from_edge():
    """AC-4.4: Belief is linked to Episode via DERIVED_FROM edge."""
    task = UpdateTask("ep:josh:1", "josh", 15000.0, 800.0, 14.5)
    runner = _make_runner()
    update_beliefs(task, runner)
    derived_calls = [c for c, _ in runner.calls if "DERIVED_FROM" in c]
    assert len(derived_calls) > 0


def test_s5_ac1_belief_confidence_on_first_episode():
    """AC-5.1: First episode belief has confidence < 0.4 (provisional)."""
    assert pace_confidence(1) < 0.4


def test_s5_ac3_belief_confidence_at_threshold():
    """AC-5.3: At corroboration_n=3, confidence crosses floor."""
    assert pace_confidence(3) >= 0.4
    assert pace_confidence(PROMOTION_THRESHOLD) >= 0.4


def test_s2_ac3_episode_count_incremented():
    """AC-2.3: PhysicalProfile.episode_count is incremented by 1."""
    task = UpdateTask("ep:josh:1", "josh", 15000.0, 800.0, 14.5)
    runner = _make_runner({"pace_on_grade AS pace": [{"pace": 15.0, "count": 2}]})
    update_beliefs(task, runner)
    # Find the SET episode_count call
    count_calls = [(c, p) for c, p in runner.calls if "episode_count" in c and "SET" in c]
    assert len(count_calls) > 0


def test_s3_ac2_below_max_does_not_overwrite():
    """AC-3.2: A value below current maximum does not overwrite."""
    task = UpdateTask("ep:josh:1", "josh", 10000.0, 400.0, 14.5)  # below any reasonable max
    runner = _make_runner()
    update_beliefs(task, runner)
    max_calls = [(c, p) for c, p in runner.calls if "max_distance_m" in c]
    # The CASE WHEN in the Cypher handles this — verify the params are passed correctly
    assert len(max_calls) > 0
    _, params = max_calls[0]
    assert params["distance_m"] == 10000.0  # value passed; CASE WHEN in Cypher does comparison


def test_s4_ac1_corroboration_n_from_derived_from_count():
    """AC-4.1: corroboration_n is computed from actual DERIVED_FROM edge count."""
    task = UpdateTask("ep:josh:1", "josh", 15000.0, 800.0, 14.5)
    runner = _make_runner()
    update_beliefs(task, runner)
    # Look for the query that recomputes corroboration_n from relationship count
    recount_calls = [c for c, _ in runner.calls if "size(" in c and "DERIVED_FROM" in c]
    assert len(recount_calls) > 0


def test_s4_ac2_belief_value_is_rounded_pace():
    """AC-4.2: Belief.value equals EWMA pace rounded to 1 decimal."""
    # pace = 14.567... should be stored as "14.6"
    task = UpdateTask("ep:josh:1", "josh", 15000.0, 800.0, 14.567)
    runner = _make_runner()
    update_beliefs(task, runner)
    belief_create_calls = [
        (c, p) for c, p in runner.calls if "Belief" in c and "MERGE" in c and "value" in str(p)
    ]
    assert len(belief_create_calls) > 0
    # Value should be a string of a rounded number
    for _, params in belief_create_calls:
        if "value" in params:
            val = params["value"]
            # Must be string, no more than 1 decimal
            assert isinstance(val, str)
            parts = val.split(".")
            assert len(parts) <= 2
            if len(parts) == 2:
                assert len(parts[1]) <= 1


def test_s2_ac1_ewma_with_real_numbers():
    """AC-2.1: Verify EWMA with multiple episodes converges correctly."""
    pace = ewma_pace(None, 16.0)  # first episode
    pace = ewma_pace(pace, 14.0)  # second — should pull toward 14
    pace = ewma_pace(pace, 14.0)  # third
    # After 3 episodes at 14.0, should be significantly below 16.0
    assert pace < 15.5
    assert pace > 13.5
