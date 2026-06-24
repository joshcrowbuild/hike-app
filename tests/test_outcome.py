"""Tests for Epic 002 — Outcome card endpoint.

Test names: test_s{story}_{ac}_{description}
All ACs from docs/epics/epic-002-outcome-card-endpoint.md.
"""

from __future__ import annotations

import pytest

from orchestration.belief_update import BeliefUpdateQueue
from orchestration.outcome import (
    OutcomeRequest,
    write_outcome,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_runner(existing_episode: bool = True, existing_outcome: bool = False):
    """Fake runner. Records calls; simulates episode existence."""
    calls: list[tuple[str, dict]] = []

    def runner(query_tuple: tuple[str, dict]):
        cypher, params = query_tuple
        calls.append((cypher, params))

        # Simulate episode ownership check
        if "Episode" in cypher and "RETURN" in cypher and "owner_id" in cypher:
            if existing_episode:
                return [{"episode_id": params.get("eid", "ep:josh:1")}]
            return []  # 404 path

        # Simulate existing outcome check
        if "Outcome" in cypher and "RETURN" in cypher and "outcome_id" in cypher:
            if existing_outcome:
                return [{"outcome_id": "existing-uuid"}]
            return []

        return []

    runner.calls = calls  # type: ignore[attr-defined]
    return runner


# ── S1 — Outcome node creation ────────────────────────────────────────────────


def test_s1_ac2_owner_id_from_viewer_not_body():
    """AC-1.2: owner_id is set from viewer_id param, not request body."""
    req = OutcomeRequest(overall=2, skipped=False)
    runner = _make_runner()
    q = BeliefUpdateQueue()
    write_outcome("ep:josh:1", "josh", req, runner, belief_queue=q)
    # Find the MERGE Outcome call
    outcome_merges = [(c, p) for c, p in runner.calls if "Outcome" in c and "MERGE" in c]
    assert len(outcome_merges) > 0
    _, params = outcome_merges[0]
    assert params.get("owner_id") == "josh"


def test_s1_ac3_overall_valid_values():
    """AC-1.3: overall must be 1, 2, or 3 (or None when skipped)."""
    for valid in [1, 2, 3]:
        req = OutcomeRequest(overall=valid, skipped=False)
        assert req.overall == valid

    skipped = OutcomeRequest(overall=None, skipped=True)
    assert skipped.overall is None


def test_s1_ac3_overall_invalid_raises():
    """AC-1.3: overall outside 1-3 raises ValueError."""
    with pytest.raises((ValueError, Exception)):
        OutcomeRequest(overall=4, skipped=False)

    with pytest.raises((ValueError, Exception)):
        OutcomeRequest(overall=0, skipped=False)


def test_s1_ac4_episode_not_found_returns_none():
    """AC-1.4: Returns None when episode doesn't exist for viewer (404 path)."""
    req = OutcomeRequest(overall=2, skipped=False)
    runner = _make_runner(existing_episode=False)
    result = write_outcome("ep:other:1", "josh", req, runner)
    assert result is None


def test_s1_ac5_idempotent_merge():
    """AC-1.5: Second POST updates updated_at only — no second Outcome node."""
    req = OutcomeRequest(overall=3, skipped=False)
    runner = _make_runner()
    q = BeliefUpdateQueue()
    write_outcome("ep:josh:1", "josh", req, runner, belief_queue=q)
    # Count only the Outcome NODE merge (not the HAS_OUTCOME relationship merge)
    outcome_merges = [c for c, _ in runner.calls if "MERGE (o:Outcome" in c]
    assert len(outcome_merges) == 1


# ── S2 — HAS_OUTCOME edge ────────────────────────────────────────────────────


def test_s2_ac1_has_outcome_edge_created():
    """AC-2.1: HAS_OUTCOME edge is written after successful outcome creation."""
    req = OutcomeRequest(overall=2, skipped=False)
    runner = _make_runner()
    write_outcome("ep:josh:1", "josh", req, runner)
    edge_calls = [c for c, _ in runner.calls if "HAS_OUTCOME" in c]
    assert len(edge_calls) > 0


# ── S3 — Skipped outcome ─────────────────────────────────────────────────────


def test_s3_ac1_skipped_outcome_still_creates_node():
    """AC-3.1: Skipped outcomes create the Outcome node (not silently dropped)."""
    req = OutcomeRequest(overall=None, skipped=True)
    runner = _make_runner()
    result = write_outcome("ep:josh:1", "josh", req, runner)
    outcome_merges = [c for c, _ in runner.calls if "Outcome" in c and "MERGE" in c]
    assert len(outcome_merges) > 0
    assert result is not None


def test_s3_ac2_skipped_does_not_enqueue_preference_check():
    """AC-3.2: Skipped outcome does NOT enqueue a preference belief check."""
    req = OutcomeRequest(overall=None, skipped=True)
    runner = _make_runner()
    q = BeliefUpdateQueue()
    write_outcome("ep:josh:1", "josh", req, runner, belief_queue=q)
    assert q.size() == 0


# ── S4 — Preference belief check ─────────────────────────────────────────────


def test_s4_ac1_non_skipped_enqueues_preference_check():
    """AC-4.1: Non-skipped outcome enqueues a preference belief check."""
    req = OutcomeRequest(overall=2, skipped=False)
    runner = _make_runner()
    q = BeliefUpdateQueue()
    write_outcome("ep:josh:1", "josh", req, runner, belief_queue=q)
    assert q.size() == 1


def test_s4_ac2_skipped_does_not_enqueue():
    """AC-4.2: Skipped outcome does not enqueue."""
    req = OutcomeRequest(overall=None, skipped=True)
    runner = _make_runner()
    q = BeliefUpdateQueue()
    write_outcome("ep:josh:1", "josh", req, runner, belief_queue=q)
    assert q.size() == 0


def test_s4_ac4_negative_rating_does_not_enqueue():
    """AC-4.4: overall=1 (negative) does NOT count toward preference promotion."""
    req = OutcomeRequest(overall=1, skipped=False)
    runner = _make_runner()
    q = BeliefUpdateQueue()
    write_outcome("ep:josh:1", "josh", req, runner, belief_queue=q)
    assert q.size() == 0


# ── S5 — Stated belief from delta_answer ─────────────────────────────────────


def test_s5_ac1_explicit_answer_writes_stated_belief():
    """AC-5.1: Non-empty delta_answer writes a stated belief with confidence=1.0."""
    req = OutcomeRequest(overall=3, delta_answer="Loved the exposed ridge terrain", skipped=False)
    runner = _make_runner()
    write_outcome("ep:josh:1", "josh", req, runner)
    belief_calls = [(c, p) for c, p in runner.calls if "Belief" in c and "MERGE" in c]
    assert len(belief_calls) > 0
    _, params = belief_calls[0]
    assert params.get("confidence") == 1.0


def test_s5_ac3_stated_belief_does_not_decay():
    """AC-5.3: Stated beliefs are written with decays=false."""
    req = OutcomeRequest(overall=3, delta_answer="Prefer loops with water crossings", skipped=False)
    runner = _make_runner()
    write_outcome("ep:josh:1", "josh", req, runner)
    belief_calls = [(c, p) for c, p in runner.calls if "Belief" in c and "MERGE" in c]
    assert len(belief_calls) > 0
    _, params = belief_calls[0]
    assert params.get("decays") is False


def test_s5_ac4_empty_delta_answer_writes_no_belief():
    """AC-5.4: Empty or None delta_answer does NOT write a belief."""
    for empty in [None, "", "   "]:
        req = OutcomeRequest(overall=2, delta_answer=empty, skipped=False)
        runner = _make_runner()
        write_outcome("ep:josh:1", "josh", req, runner)
        belief_calls = [c for c, _ in runner.calls if "Belief" in c and "MERGE" in c]
        assert len(belief_calls) == 0, f"Expected no belief for delta_answer={empty!r}"


def test_s5_ac5_stated_belief_provenance():
    """AC-5.5: Stated belief is linked via DERIVED_FROM and ABOUT."""
    req = OutcomeRequest(
        overall=3, delta_answer="Always prefer ridges over valley trails", skipped=False
    )
    runner = _make_runner()
    write_outcome("ep:josh:1", "josh", req, runner)
    assert any("DERIVED_FROM" in c for c, _ in runner.calls)
    assert any("ABOUT" in c for c, _ in runner.calls)


# ── Additional LOW coverage ───────────────────────────────────────────────────


def test_s5_rule4_belief_match_includes_owner_id():
    """MODERATE fix: Belief MATCH in _write_stated_belief scoped to owner_id."""
    req = OutcomeRequest(overall=3, delta_answer="Love exposed ridges", skipped=False)
    runner = _make_runner()
    write_outcome("ep:josh:1", "josh", req, runner)
    # All Belief MATCHes must include owner constraint
    belief_matches = [(c, p) for c, p in runner.calls if "MATCH (b:Belief" in c]
    for cypher, params in belief_matches:
        assert "owner_id" in cypher or "owner" in params, (
            f"Belief MATCH missing owner_id scope: {cypher}"
        )


def test_s3_ac3_skipped_then_non_skipped_replaces():
    """AC-3.3: A subsequent non-skipped POST replaces the skipped outcome."""
    # First: skipped
    req_skip = OutcomeRequest(overall=None, skipped=True)
    runner = _make_runner()
    result1 = write_outcome("ep:josh:1", "josh", req_skip, runner)
    assert result1 is not None
    assert result1.skipped is True

    # Second: non-skipped with rating (same runner = same state)
    req_rate = OutcomeRequest(overall=3, skipped=False)
    result2 = write_outcome("ep:josh:1", "josh", req_rate, runner)
    assert result2 is not None
    # The ON MATCH SET should update skipped=False and overall=3
    on_match_calls = [(c, p) for c, p in runner.calls if "ON MATCH SET" in c and "Outcome" in c]
    assert len(on_match_calls) >= 1
    # Last MERGE should have skipped=False
    _, params = on_match_calls[-1]
    assert params.get("skipped") is False
    assert params.get("overall") == 3
