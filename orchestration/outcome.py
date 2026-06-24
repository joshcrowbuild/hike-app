"""Outcome card — Epic 002.

`write_outcome()` persists an Outcome node after a hike, wires the HAS_OUTCOME
edge, optionally promotes an explicit delta_answer to a `stated` Belief, and
enqueues a preference belief check for non-negative non-skipped outcomes.

Phase 1 scoping:
  - Preference belief promotion check is QUEUED (not run synchronously in the
    HTTP request path per AC-4.3 / S6 §4.1 queue discipline).
  - The queue holds UpdateTask objects (same type as capability belief updates);
    Epic 003 will wire the preference check when context assembly exists.
  - No LLM call for delta_answer classification in Phase 1 (AC-5, spec note).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

_VALID_RATINGS = frozenset({1, 2, 3})
_POSITIVE_THRESHOLD = 2  # overall >= 2 counts toward preference corroboration


# ── Request / result types ────────────────────────────────────────────────────


@dataclass
class OutcomeRequest:
    overall: int | None = None  # 1 | 2 | 3 | None (skipped)
    delta_question: str | None = None  # the question that was shown
    delta_answer: str | None = None  # user's free-text answer (or None)
    skipped: bool = False

    def __post_init__(self) -> None:
        if not self.skipped and self.overall is not None:
            if self.overall not in _VALID_RATINGS:
                raise ValueError(
                    f"overall must be one of {sorted(_VALID_RATINGS)}, got {self.overall!r}"
                )
        if self.skipped and self.overall is not None:
            raise ValueError("overall must be None when skipped=True")


@dataclass(frozen=True)
class OutcomeResult:
    outcome_id: str
    episode_id: str
    owner_id: str
    skipped: bool
    overall: int | None


# ── Core write logic ─────────────────────────────────────────────────────────


def write_outcome(
    episode_id: str,
    viewer_id: str,
    req: OutcomeRequest,
    runner,
    *,
    belief_queue=None,  # BeliefUpdateQueue | None
) -> OutcomeResult | None:
    """Persist an Outcome node. Returns None if episode not found for viewer (404 path).

    Atomic: Outcome MERGE + HAS_OUTCOME edge in sequential queries (Community Edition
    safe — no multi-statement transactions via Runner). The runner is the caller's
    responsibility to wrap in a real transaction if needed.
    """
    # AC-1.4: verify episode belongs to viewer (Rule #4)
    rows = runner(
        (
            "MATCH (e:Episode {episode_id: $eid}) "
            "WHERE e.owner_id = $owner_id "
            "RETURN e.episode_id AS episode_id",
            {"eid": episode_id, "owner_id": viewer_id},
        )
    )
    if not rows:
        log.warning("Outcome rejected: episode %s not found for viewer %s", episode_id, viewer_id)
        return None

    outcome_id_key = f"outcome:{viewer_id}:{episode_id}"

    # AC-1.5: idempotent MERGE keyed on (episode_id, owner_id)
    runner(
        (
            "MERGE (o:Outcome {episode_id: $episode_id, owner_id: $owner_id}) "
            "ON CREATE SET "
            "    o.outcome_id     = $oid, "
            "    o.overall        = $overall, "
            "    o.delta_question = $delta_q, "
            "    o.delta_answer   = $delta_a, "
            "    o.skipped        = $skipped, "
            "    o.surfaces_at    = datetime(), "
            "    o.completed_at   = CASE WHEN NOT $skipped THEN datetime() ELSE null END, "
            "    o.created_at     = datetime() "
            "ON MATCH SET "
            "    o.overall        = $overall, "
            "    o.delta_answer   = $delta_a, "
            "    o.skipped        = $skipped, "
            "    o.updated_at     = datetime()",
            {
                "episode_id": episode_id,
                "owner_id": viewer_id,
                "oid": outcome_id_key,
                "overall": req.overall,
                "delta_q": req.delta_question,
                "delta_a": req.delta_answer,
                "skipped": req.skipped,
            },
        )
    )

    # AC-2.1: HAS_OUTCOME edge
    runner(
        (
            "MATCH (e:Episode {episode_id: $eid, owner_id: $owner_id}) "
            "MATCH (o:Outcome {episode_id: $eid, owner_id: $owner_id}) "
            "MERGE (e)-[:HAS_OUTCOME]->(o)",
            {"eid": episode_id, "owner_id": viewer_id},
        )
    )

    # AC-5: explicit delta_answer → stated belief (no LLM classification in Phase 1)
    delta = (req.delta_answer or "").strip()
    if delta and not req.skipped:
        _write_stated_belief(episode_id, viewer_id, delta, runner)

    # AC-4.1 / AC-4.4: enqueue preference check for positive non-skipped outcomes
    if not req.skipped and req.overall is not None and req.overall >= _POSITIVE_THRESHOLD:
        if belief_queue is not None:
            from orchestration.belief_update import UpdateTask

            # Reuse UpdateTask; preference promotion logic will extend in Epic 006.
            # For now, enqueue a sentinel task that marks "outcome available for preference check".
            belief_queue.enqueue(
                UpdateTask(
                    episode_id=episode_id,
                    owner_id=viewer_id,
                    distance_m=None,
                    ascent_m=None,
                    pace_on_grade=None,  # not a capability update — preference check marker
                )
            )

    return OutcomeResult(
        outcome_id=outcome_id_key,
        episode_id=episode_id,
        owner_id=viewer_id,
        skipped=req.skipped,
        overall=req.overall,
    )


def _write_stated_belief(episode_id: str, owner_id: str, statement: str, runner) -> None:
    """Promote an explicit user statement to a `stated` Belief immediately.

    AC-5.1: confidence=1.0  AC-5.3: decays=false  AC-5.5: provenance edges
    No LLM call — raw statement stored as-is. Phase 1 simplification; Phase 3+
    can add extraction/normalisation.
    """
    belief_id = f"belief:{owner_id}:stated_preference:{episode_id}"
    runner(
        (
            "MERGE (b:Belief {belief_id: $bid}) "
            "ON CREATE SET "
            "    b.owner_id           = $owner, "
            "    b.subject_id         = $owner, "
            "    b.subject_type       = 'person', "
            "    b.axis               = 'preference', "
            "    b.type               = 'stated', "
            "    b.key                = 'stated_preference', "
            "    b.value              = $value, "
            "    b.confidence         = $confidence, "
            "    b.corroboration_n    = 1, "
            "    b.decays             = $decays, "
            "    b.confirmed_by_user  = true, "
            "    b.created_at         = datetime(), "
            "    b.last_updated_at    = datetime() "
            "ON MATCH SET "
            "    b.value              = $value, "
            "    b.last_updated_at    = datetime()",
            {
                "bid": belief_id,
                "owner": owner_id,
                "value": statement,
                "confidence": 1.0,
                "decays": False,
            },
        )
    )
    # Provenance: DERIVED_FROM episode + ABOUT person (both scoped to owner — Rule #4)
    runner(
        (
            "MATCH (b:Belief {belief_id: $bid, owner_id: $owner}) "
            "MATCH (e:Episode {episode_id: $eid, owner_id: $owner}) "
            "MERGE (b)-[:DERIVED_FROM]->(e)",
            {"bid": belief_id, "eid": episode_id, "owner": owner_id},
        )
    )
    runner(
        (
            "MATCH (b:Belief {belief_id: $bid, owner_id: $owner}) "
            "MATCH (p:Person {member_id: $owner}) "
            "MERGE (b)-[:ABOUT]->(p)",
            {"bid": belief_id, "owner": owner_id},
        )
    )
