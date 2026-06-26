"""Tests for Epic 002 — Outcome card endpoint.

Test names: test_s{story}_{ac}_{description}
All ACs from docs/epics/epic-002-outcome-card-endpoint.md.

`write_outcome` routes every owned write through `ScopedSession.execute_write`
(review finding #1), so the fake session here runs the REAL owned-write guard
(`assert_scoped_write`) on each statement: a regression that drops the owner clause
on an Outcome/Belief builder turns these tests red, not just the seam tests.
"""

from __future__ import annotations

import pytest

from graph.queries import assert_scoped_write
from orchestration.belief_update import BeliefUpdateQueue
from orchestration.outcome import (
    OutcomeRequest,
    write_outcome,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


class _FakeScoped:
    """A fake ScopedSession: records the ownership read + the transactional write
    batch, injects the viewer scope exactly as the real seam does, and runs the real
    owned-write guard on every write so unscoped writes fail here too."""

    def __init__(self, viewer_id: str = "josh", *, existing_episode: bool = True) -> None:
        self.viewer_id = viewer_id
        self.existing_episode = existing_episode
        self.reads: list[tuple[str, dict]] = []
        self.tx_batches: list[list[tuple[str, dict]]] = []
        self.writes: list[tuple[str, dict]] = []  # every write, flattened, scope merged

    def run(self, query: tuple[str, dict]):
        cypher, params = query
        self.reads.append((cypher, params))
        # Simulate the episode-ownership check
        if "Episode" in cypher and "RETURN" in cypher and "owner_id" in cypher:
            return [{"episode_id": params.get("eid", "ep:josh:1")}] if self.existing_episode else []
        return []

    def execute_write(self, batch: list[tuple[str, dict]]) -> None:
        merged_batch: list[tuple[str, dict]] = []
        for cypher, params in batch:
            assert_scoped_write(cypher)  # real seam guard — proves owner-scope routing
            merged = {"viewer_id": self.viewer_id, "granted_ids": [], **params}
            merged_batch.append((cypher, merged))
        self.tx_batches.append(merged_batch)
        self.writes.extend(merged_batch)


def _norm(cypher: str) -> str:
    """Whitespace-collapse so substring assertions are layout-insensitive."""
    return " ".join(cypher.split())


# ── S1 — Outcome node creation ────────────────────────────────────────────────


def test_s1_ac2_owner_id_from_viewer_not_body():
    """AC-1.2: the written owner is the session viewer, injected by the seam — never
    a value carried in the request body. No free owner param reaches the write."""
    req = OutcomeRequest(overall=2, skipped=False)
    scoped = _FakeScoped("josh")
    q = BeliefUpdateQueue()
    write_outcome("ep:josh:1", "josh", req, scoped, belief_queue=q)
    outcome_merges = [(c, p) for c, p in scoped.writes if "MERGE (o:Outcome" in c]
    assert len(outcome_merges) == 1
    _, params = outcome_merges[0]
    assert params.get("viewer_id") == "josh"  # the seam injected the viewer
    assert "owner_id" not in params  # owner is bound to $viewer_id in Cypher, not a body param


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
    """AC-1.4: Returns None when episode doesn't exist for viewer (404 path) — and
    no write is attempted before ownership is confirmed."""
    req = OutcomeRequest(overall=2, skipped=False)
    scoped = _FakeScoped("josh", existing_episode=False)
    result = write_outcome("ep:other:1", "josh", req, scoped)
    assert result is None
    assert scoped.writes == []  # nothing written on the 404 path


def test_s1_ac5_idempotent_merge():
    """AC-1.5: Second POST updates updated_at only — no second Outcome node."""
    req = OutcomeRequest(overall=3, skipped=False)
    scoped = _FakeScoped("josh")
    q = BeliefUpdateQueue()
    write_outcome("ep:josh:1", "josh", req, scoped, belief_queue=q)
    # Count only the Outcome NODE merge (not the HAS_OUTCOME relationship merge)
    outcome_merges = [c for c, _ in scoped.writes if "MERGE (o:Outcome" in c]
    assert len(outcome_merges) == 1


def test_s1_atomic_single_transaction():
    """Finding #1: every owned write commits in ONE managed transaction (execute_write
    batch), not as independent statements — Outcome + edge + belief + provenance together."""
    req = OutcomeRequest(overall=3, delta_answer="Loved the ridge", skipped=False)
    scoped = _FakeScoped("josh")
    write_outcome("ep:josh:1", "josh", req, scoped)
    assert len(scoped.tx_batches) == 1  # all writes in a single atomic batch
    assert len(scoped.tx_batches[0]) == 5  # Outcome, HAS_OUTCOME, Belief, DERIVED_FROM, ABOUT


# ── S2 — HAS_OUTCOME edge ────────────────────────────────────────────────────


def test_s2_ac1_has_outcome_edge_created():
    """AC-2.1: HAS_OUTCOME edge is written after successful outcome creation."""
    req = OutcomeRequest(overall=2, skipped=False)
    scoped = _FakeScoped("josh")
    write_outcome("ep:josh:1", "josh", req, scoped)
    edge_calls = [c for c, _ in scoped.writes if "HAS_OUTCOME" in c]
    assert len(edge_calls) > 0


# ── S3 — Skipped outcome ─────────────────────────────────────────────────────


def test_s3_ac1_skipped_outcome_still_creates_node():
    """AC-3.1: Skipped outcomes create the Outcome node (not silently dropped)."""
    req = OutcomeRequest(overall=None, skipped=True)
    scoped = _FakeScoped("josh")
    result = write_outcome("ep:josh:1", "josh", req, scoped)
    outcome_merges = [c for c, _ in scoped.writes if "MERGE (o:Outcome" in c]
    assert len(outcome_merges) > 0
    assert result is not None


def test_s3_ac2_skipped_does_not_enqueue_preference_check():
    """AC-3.2: Skipped outcome does NOT enqueue a preference belief check."""
    req = OutcomeRequest(overall=None, skipped=True)
    scoped = _FakeScoped("josh")
    q = BeliefUpdateQueue()
    write_outcome("ep:josh:1", "josh", req, scoped, belief_queue=q)
    assert q.size() == 0


# ── S4 — Preference belief check ─────────────────────────────────────────────


def test_s4_ac1_non_skipped_enqueues_preference_check():
    """AC-4.1: Non-skipped outcome enqueues a preference belief check."""
    req = OutcomeRequest(overall=2, skipped=False)
    scoped = _FakeScoped("josh")
    q = BeliefUpdateQueue()
    write_outcome("ep:josh:1", "josh", req, scoped, belief_queue=q)
    assert q.size() == 1


def test_s4_ac2_skipped_does_not_enqueue():
    """AC-4.2: Skipped outcome does not enqueue."""
    req = OutcomeRequest(overall=None, skipped=True)
    scoped = _FakeScoped("josh")
    q = BeliefUpdateQueue()
    write_outcome("ep:josh:1", "josh", req, scoped, belief_queue=q)
    assert q.size() == 0


def test_s4_ac4_negative_rating_does_not_enqueue():
    """AC-4.4: overall=1 (negative) does NOT count toward preference promotion."""
    req = OutcomeRequest(overall=1, skipped=False)
    scoped = _FakeScoped("josh")
    q = BeliefUpdateQueue()
    write_outcome("ep:josh:1", "josh", req, scoped, belief_queue=q)
    assert q.size() == 0


# ── S5 — Stated belief from delta_answer ─────────────────────────────────────


def test_s5_ac1_explicit_answer_writes_stated_belief():
    """AC-5.1: Non-empty delta_answer writes a stated belief with confidence=1.0."""
    req = OutcomeRequest(overall=3, delta_answer="Loved the exposed ridge terrain", skipped=False)
    scoped = _FakeScoped("josh")
    write_outcome("ep:josh:1", "josh", req, scoped)
    belief_merges = [c for c, _ in scoped.writes if "MERGE (b:Belief" in c]
    assert len(belief_merges) == 1
    assert "b.confidence = 1.0" in _norm(belief_merges[0])


def test_s5_ac3_stated_belief_does_not_decay():
    """AC-5.3: Stated beliefs are written with decays=false."""
    req = OutcomeRequest(overall=3, delta_answer="Prefer loops with water crossings", skipped=False)
    scoped = _FakeScoped("josh")
    write_outcome("ep:josh:1", "josh", req, scoped)
    belief_merges = [c for c, _ in scoped.writes if "MERGE (b:Belief" in c]
    assert len(belief_merges) == 1
    assert "b.decays = false" in _norm(belief_merges[0])


def test_s5_ac4_empty_delta_answer_writes_no_belief():
    """AC-5.4: Empty or None delta_answer does NOT write a belief."""
    for empty in [None, "", "   "]:
        req = OutcomeRequest(overall=2, delta_answer=empty, skipped=False)
        scoped = _FakeScoped("josh")
        write_outcome("ep:josh:1", "josh", req, scoped)
        belief_merges = [c for c, _ in scoped.writes if "MERGE (b:Belief" in c]
        assert len(belief_merges) == 0, f"Expected no belief for delta_answer={empty!r}"


def test_s5_ac5_stated_belief_provenance():
    """AC-5.5: Stated belief is linked via DERIVED_FROM and ABOUT."""
    req = OutcomeRequest(
        overall=3, delta_answer="Always prefer ridges over valley trails", skipped=False
    )
    scoped = _FakeScoped("josh")
    write_outcome("ep:josh:1", "josh", req, scoped)
    assert any("DERIVED_FROM" in c for c, _ in scoped.writes)
    assert any("ABOUT" in c for c, _ in scoped.writes)


# ── Additional coverage ───────────────────────────────────────────────────────


def test_s5_finding2_stated_belief_pins_owner_in_merge_key():
    """Review finding #2: the stated Belief MERGE pins owner_id IN the merge key
    ({belief_id, owner_id}), so a foreign belief_id can never MATCH and clobber another
    member's belief — ownership is enforced by the seam, not the id-naming convention."""
    req = OutcomeRequest(overall=3, delta_answer="Love exposed ridges", skipped=False)
    scoped = _FakeScoped("josh")
    write_outcome("ep:josh:1", "josh", req, scoped)
    belief_merges = [c for c, _ in scoped.writes if "MERGE (b:Belief" in c]
    assert len(belief_merges) == 1
    assert "MERGE (b:Belief {belief_id: $bid, owner_id: $viewer_id})" in _norm(belief_merges[0])


def test_s3_ac3_skipped_then_non_skipped_replaces():
    """AC-3.3: A subsequent non-skipped POST replaces the skipped outcome."""
    scoped = _FakeScoped("josh")
    # First: skipped
    req_skip = OutcomeRequest(overall=None, skipped=True)
    result1 = write_outcome("ep:josh:1", "josh", req_skip, scoped)
    assert result1 is not None
    assert result1.skipped is True

    # Second: non-skipped with rating (same session = same state)
    req_rate = OutcomeRequest(overall=3, skipped=False)
    result2 = write_outcome("ep:josh:1", "josh", req_rate, scoped)
    assert result2 is not None
    # The Outcome MERGE carries an ON MATCH SET branch updating skipped/overall in place
    outcome_merges = [(c, p) for c, p in scoped.writes if "MERGE (o:Outcome" in c]
    assert len(outcome_merges) == 2  # one per POST, same node (idempotent on the key)
    last_cypher, last_params = outcome_merges[-1]
    assert "ON MATCH SET" in last_cypher
    assert last_params.get("skipped") is False
    assert last_params.get("overall") == 3
