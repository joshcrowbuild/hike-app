"""Belief update pipeline — Stage 6 §4.1–4.3 (Epic 001).

After each Episode ingestion, updates the owner's PhysicalProfile and
associated capability Belief nodes. Decoupled from the ingest path via a
queue: `create_episode()` enqueues a task; a worker drains it.

What this handles:
  - EWMA pace_on_grade (α=0.3, per Stage 5 §3 / decision-log §30)
  - max_distance_m and max_ascent_m empirical maxima
  - pace_on_grade_moderate Belief node with corroboration tracking
  - Provisional → eligible transition at N=3 (confidence floor 0.4)

What this does NOT handle (scoped out of Epic 001):
  - heat_response inference (S6 §4.4 — NWS historical endpoint unconfirmed)
  - preference/taste belief promotion (requires Outcome data — Epic 002)
  - asyncio.Queue worker loop (added in Epic 002 when the full ingest job exists)

All DB operations accept a Runner = Callable[(cypher, params) → rows] so the
logic is testable without a live Neo4j connection.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

# ── Constants (all spec'd in Stage 5 §3 / Stage 6 §4.2) ─────────────────────

EWMA_ALPHA = 0.3
PROMOTION_THRESHOLD = 3  # corroboration_n at which confidence crosses the floor
_CONFIDENCE_PROVISIONAL = 0.3  # below floor (< 0.4) — not injected into context
_CONFIDENCE_PROMOTED = 0.7  # above floor (≥ 0.4) — eligible for context assembly

Runner = Any  # Callable[(str, dict) → list[dict]] — ScopedSession.run or make_runner


# ── Data types ───────────────────────────────────────────────────────────────


@dataclass
class UpdateTask:
    """Payload pushed to the queue after a successful Episode creation."""

    episode_id: str
    owner_id: str
    distance_m: float | None
    ascent_m: float | None
    pace_on_grade: float | None


class BeliefUpdateQueue:
    """Simple in-process queue for belief update tasks.

    Designed to be sync for Phase 1 (single-process ingest). The asyncio.Queue
    upgrade specified in S6 §4.1 is scoped to the full watch_sync.py job
    (Epic 003) when we have a persistent event loop to drain it.
    """

    def __init__(self) -> None:
        self._q: deque[UpdateTask] = deque()

    def enqueue(self, task: UpdateTask) -> None:
        self._q.append(task)

    def _dequeue(self) -> UpdateTask:
        return self._q.popleft()

    def size(self) -> int:
        return len(self._q)

    def drain(self, runner: Runner) -> int:
        """Process all queued tasks. Returns count of tasks processed."""
        count = 0
        while self._q:
            task = self._dequeue()
            try:
                update_beliefs(task, runner)
                count += 1
            except Exception as exc:
                log.error("Belief update failed for episode %s: %s", task.episode_id, exc)
        return count


# ── Pure functions (testable without DB) ─────────────────────────────────────


def ewma_pace(current: float | None, new: float, alpha: float = EWMA_ALPHA) -> float:
    """Exponentially weighted moving average for pace_on_grade."""
    if current is None:
        return new  # first episode — no smoothing needed
    return alpha * new + (1 - alpha) * current


def pace_confidence(corroboration_n: int) -> float:
    """Confidence score for a pace belief given its corroboration count."""
    return (
        _CONFIDENCE_PROMOTED if corroboration_n >= PROMOTION_THRESHOLD else _CONFIDENCE_PROVISIONAL
    )


# ── DB update logic ───────────────────────────────────────────────────────────


def update_beliefs(task: UpdateTask, runner: Runner) -> None:
    """Run all belief updates for one episode. Entry point for queue worker."""
    if task.pace_on_grade is not None:
        _update_pace(task, runner)
    _update_maxima(task, runner)


def _update_pace(task: UpdateTask, runner: Runner) -> None:
    """EWMA update to PhysicalProfile.pace_on_grade + write capability Belief."""
    pace = task.pace_on_grade
    if pace is None:  # caller guards this, but stay self-safe (and narrow for mypy)
        return
    rows = runner(
        (
            "MATCH (pp:PhysicalProfile {owner_id: $owner}) "
            "RETURN pp.pace_on_grade AS pace, pp.episode_count AS count",
            {"owner": task.owner_id},
        )
    )

    if not rows:
        # No profile yet — create it with the first episode's pace.
        new_pace = pace
        runner(
            (
                "MERGE (pp:PhysicalProfile {owner_id: $owner}) "
                "SET pp.pace_on_grade = $pace, "
                "    pp.episode_count  = 1, "
                "    pp.updated_at     = datetime()",
                {"owner": task.owner_id, "pace": new_pace},
            )
        )
    else:
        current_pace = rows[0].get("pace")
        new_pace = ewma_pace(current_pace, pace)
        runner(
            (
                "MATCH (pp:PhysicalProfile {owner_id: $owner}) "
                "SET pp.pace_on_grade = $pace, "
                "    pp.episode_count  = coalesce(pp.episode_count, 0) + 1, "
                "    pp.updated_at     = datetime()",
                {"owner": task.owner_id, "pace": new_pace},
            )
        )

    _write_pace_belief(task, round(new_pace, 1), runner)


def _update_maxima(task: UpdateTask, runner: Runner) -> None:
    """Update max_distance_m and max_ascent_m as empirical maxima."""
    distance_m = task.distance_m
    ascent_m = task.ascent_m
    if distance_m is None and ascent_m is None:
        return

    runner(
        (
            "MERGE (pp:PhysicalProfile {owner_id: $owner}) "
            "ON CREATE SET "  # fix: first-episode maxima would be dropped without ON CREATE
            "    pp.max_distance_m = $distance_m, "
            "    pp.max_ascent_m   = $ascent_m, "
            "    pp.updated_at     = datetime() "
            "ON MATCH SET "
            "    pp.max_distance_m = CASE WHEN $distance_m IS NOT NULL AND "
            "                             $distance_m > coalesce(pp.max_distance_m, 0) "
            "                        THEN $distance_m "
            "                        ELSE pp.max_distance_m END, "
            "    pp.max_ascent_m   = CASE WHEN $ascent_m IS NOT NULL AND "
            "                             $ascent_m > coalesce(pp.max_ascent_m, 0) "
            "                        THEN $ascent_m "
            "                        ELSE pp.max_ascent_m END, "
            "    pp.updated_at     = datetime()",
            {"owner": task.owner_id, "distance_m": distance_m, "ascent_m": ascent_m},
        )
    )


def _write_pace_belief(task: UpdateTask, pace_value: float, runner: Runner) -> None:
    """MERGE Belief node for pace_on_grade_moderate; wire DERIVED_FROM + ABOUT."""
    belief_id = f"belief:{task.owner_id}:pace_on_grade_moderate"

    # MERGE belief node first (so DERIVED_FROM edge exists before we count it)
    runner(
        (
            "MERGE (b:Belief {belief_id: $bid}) "
            "ON CREATE SET "
            "    b.owner_id             = $owner, "
            "    b.subject_id           = $owner, "
            "    b.subject_type         = 'person', "
            "    b.axis                 = 'capability', "
            "    b.type                 = 'inferred', "
            "    b.key                  = 'pace_on_grade_moderate', "
            "    b.value                = $value, "
            "    b.confidence           = 0.3, "
            "    b.corroboration_n      = 0, "
            "    b.decays               = true, "
            "    b.decay_half_life_days = 180, "
            "    b.confirmed_by_user    = false, "
            "    b.created_at           = datetime(), "
            "    b.last_updated_at      = datetime() "
            "ON MATCH SET "
            "    b.value                = $value, "
            "    b.last_updated_at      = datetime()",
            {"bid": belief_id, "owner": task.owner_id, "value": str(pace_value)},
        )
    )

    # Provenance: Belief -[:DERIVED_FROM]-> Episode (idempotent MERGE)
    # Rule #4: episode scoped to owner prevents cross-user edge
    runner(
        (
            "MATCH (b:Belief {belief_id: $bid}) "
            "MATCH (e:Episode {episode_id: $eid, owner_id: $owner}) "
            "MERGE (b)-[:DERIVED_FROM]->(e)",
            {"bid": belief_id, "eid": task.episode_id, "owner": task.owner_id},
        )
    )

    # Recount corroboration_n from actual DERIVED_FROM edges (idempotent)
    runner(
        (
            "MATCH (b:Belief {belief_id: $bid}) "
            "WITH b, size([(b)-[:DERIVED_FROM]->() | 1]) AS n "
            "SET b.corroboration_n = n, "
            "    b.confidence      = CASE WHEN n >= $threshold THEN 0.7 ELSE 0.3 END",
            {"bid": belief_id, "threshold": PROMOTION_THRESHOLD},
        )
    )

    # Ownership: Belief -[:ABOUT]-> Person
    runner(
        (
            "MATCH (b:Belief {belief_id: $bid}) "
            "MATCH (p:Person {member_id: $owner}) "
            "MERGE (b)-[:ABOUT]->(p)",
            {"bid": belief_id, "owner": task.owner_id},
        )
    )


# ── Top-level coordinator ─────────────────────────────────────────────────────


def process_episode(episode_id: str, owner_id: str, runner: Runner) -> None:
    """Convenience wrapper: build an UpdateTask from graph data and run updates.

    Reads the Episode node to get distance/ascent/pace, then calls update_beliefs.
    Use this when you have the episode_id but not the field values in memory.
    """
    rows = runner(
        (
            "MATCH (e:Episode {episode_id: $eid, owner_id: $owner}) "
            "RETURN e.distance_m AS distance_m, e.ascent_m AS ascent_m, "
            "       e.pace_on_grade AS pace_on_grade",
            {"eid": episode_id, "owner": owner_id},
        )
    )
    if not rows:
        log.warning("process_episode: Episode %s not found for owner %s", episode_id, owner_id)
        return
    row = rows[0]
    task = UpdateTask(
        episode_id=episode_id,
        owner_id=owner_id,
        distance_m=row.get("distance_m"),
        ascent_m=row.get("ascent_m"),
        pace_on_grade=row.get("pace_on_grade"),
    )
    update_beliefs(task, runner)
