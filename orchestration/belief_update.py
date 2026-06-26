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

Owned-node reads and writes go through a `ScopedSession` (Epic 011): reads via
`session.run`, writes via `session.run_write` (which refuses an owned write that
forgot its owner-scope clause). All Cypher is authored in `graph.queries`, so
this module holds no inline owned-node Cypher — and is testable without a live
Neo4j connection by passing a fake session that records run/run_write calls.
"""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from graph import queries

log = logging.getLogger(__name__)

# ── Constants (all spec'd in Stage 5 §3 / Stage 6 §4.2) ─────────────────────

EWMA_ALPHA = 0.3
PROMOTION_THRESHOLD = 3  # corroboration_n at which confidence crosses the floor
_CONFIDENCE_PROVISIONAL = 0.3  # below floor (< 0.4) — not injected into context
_CONFIDENCE_PROMOTED = 0.7  # above floor (≥ 0.4) — eligible for context assembly


class ScopedWriter(Protocol):
    """The owned-node access surface this module needs — `ScopedSession` satisfies
    it (`run` for owner-scoped reads, `run_write` for guarded owned writes)."""

    def run(self, query: tuple[str, dict[str, Any]]) -> list[dict[str, Any]]: ...
    def run_write(self, query: tuple[str, dict[str, Any]]) -> list[dict[str, Any]]: ...


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

    def drain(self, session_factory: Callable[[str], ScopedWriter]) -> int:
        """Process all queued tasks. Returns count of tasks processed.

        `session_factory(owner_id) -> ScopedWriter` yields a session scoped to
        each task's owner, so every write is owner-scoped to the right member
        (rule #4). In production this is `GraphClient.scoped_session`."""
        count = 0
        while self._q:
            task = self._dequeue()
            try:
                update_beliefs(task, session_factory(task.owner_id))
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


def update_beliefs(task: UpdateTask, session: ScopedWriter) -> None:
    """Run all belief updates for one episode. Entry point for queue worker."""
    if task.pace_on_grade is not None:
        _update_pace(task, session)
    _update_maxima(task, session)


def _update_pace(task: UpdateTask, session: ScopedWriter) -> None:
    """EWMA update to PhysicalProfile.pace_on_grade + write capability Belief."""
    pace = task.pace_on_grade
    if pace is None:  # caller guards this, but stay self-safe (and narrow for mypy)
        return
    rows = session.run(queries.physical_profile_pace_read())
    current_pace = rows[0].get("pace") if rows else None
    # ewma_pace returns `pace` unchanged on the first episode (current None).
    new_pace = ewma_pace(current_pace, pace)
    session.run_write(queries.upsert_physical_profile_pace(new_pace))
    _write_pace_belief(task, round(new_pace, 1), session)


def _update_maxima(task: UpdateTask, session: ScopedWriter) -> None:
    """Update max_distance_m and max_ascent_m as empirical maxima."""
    distance_m = task.distance_m
    ascent_m = task.ascent_m
    if distance_m is None and ascent_m is None:
        return
    session.run_write(queries.upsert_physical_profile_maxima(distance_m, ascent_m))


def _write_pace_belief(task: UpdateTask, pace_value: float, session: ScopedWriter) -> None:
    """MERGE Belief node for pace_on_grade_moderate; wire DERIVED_FROM + ABOUT.

    The corroboration recount is owner-scoped (gap-audit M8): it counts only the
    owner's DERIVED_FROM episodes, so another member's hikes can never push the
    belief across the confidence floor."""
    belief_id = f"belief:{task.owner_id}:pace_on_grade_moderate"

    # MERGE belief node first (so DERIVED_FROM edge exists before we count it)
    session.run_write(queries.upsert_pace_belief(belief_id, str(pace_value)))
    session.run_write(queries.wire_belief_derived_from_episode(belief_id, task.episode_id))
    session.run_write(queries.recount_belief_corroboration(belief_id, PROMOTION_THRESHOLD))
    session.run_write(queries.wire_belief_about_person(belief_id))


# ── Top-level coordinator ─────────────────────────────────────────────────────


def process_episode(episode_id: str, owner_id: str, session: ScopedWriter) -> None:
    """Convenience wrapper: build an UpdateTask from graph data and run updates.

    Reads the Episode node (owner-scoped — gap-audit C2) to get
    distance/ascent/pace, then calls update_beliefs. Use this when you have the
    episode_id but not the field values in memory.
    """
    rows = session.run(queries.episode_fields_read(episode_id))
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
    update_beliefs(task, session)
