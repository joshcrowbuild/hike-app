"""Outcome card — Epic 002.

`write_outcome()` persists an Outcome node after a hike, wires the HAS_OUTCOME
edge, optionally promotes an explicit delta_answer to a `stated` Belief, and
enqueues a preference belief check for non-negative non-skipped outcomes.

Every owned write (Outcome + HAS_OUTCOME + stated Belief + provenance) is authored
by `graph.queries` builders and committed together through the scoped-write seam
(`ScopedSession.execute_write`) — one atomic transaction, owner-scoped to the viewer
(rule #4 / Epic 011), so no statement can write around the owner-clause guard. The
episode-ownership check that gates the write is a scoped read (`ScopedSession.run`).

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
from typing import Any

from graph import queries
from orchestration.logsafe import scrub_episode, scrub_viewer

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
    scoped,  # ScopedSession
    *,
    belief_queue=None,  # BeliefUpdateQueue | None
) -> OutcomeResult | None:
    """Persist an Outcome node. Returns None if the episode is not the viewer's (404).

    `scoped` is a `ScopedSession`: `.run` for the ownership read, `.execute_write` for
    the owned writes. The Outcome MERGE + HAS_OUTCOME edge and — when an explicit
    delta_answer is given — the stated Belief + its DERIVED_FROM/ABOUT provenance are
    built by `graph.queries` and committed in ONE managed transaction, so they are
    atomic and pass the owned-write guard (rule #4 / Epic 011).
    """
    # AC-1.4: verify episode belongs to viewer before any write (Rule #4). Read path —
    # the ScopedSession injects $viewer_id; the strict owner-key (not owner_scope) keeps
    # an outcome a self-write, never recordable against a granted member's episode.
    rows = scoped.run(
        (
            "MATCH (e:Episode {episode_id: $eid})\n"
            "WHERE e.owner_id = $viewer_id\n"
            "RETURN e.episode_id AS episode_id",
            {"eid": episode_id},
        )
    )
    if not rows:
        # Neither identifier is logged in the clear (rule #5): the viewer digest keeps
        # a session's log lines correlatable, and the episode id embeds the owner id
        # so it gets the same treatment.
        log.warning(
            "Outcome rejected: episode %s not found for viewer %s",
            scrub_episode(episode_id),
            scrub_viewer(viewer_id),
        )
        return None

    outcome_id_key = f"outcome:{viewer_id}:{episode_id}"

    # AC-1.5 / AC-2.1: idempotent Outcome MERGE + HAS_OUTCOME edge, both owner-scoped.
    writes: list[tuple[str, dict[str, Any]]] = [
        queries.upsert_outcome(
            episode_id,
            outcome_id=outcome_id_key,
            overall=req.overall,
            delta_question=req.delta_question,
            delta_answer=req.delta_answer,
            skipped=req.skipped,
        ),
        queries.wire_episode_has_outcome(episode_id),
    ]

    # AC-5: explicit delta_answer → stated belief + provenance (no LLM in Phase 1).
    delta = (req.delta_answer or "").strip()
    if delta and not req.skipped:
        belief_id = f"belief:{viewer_id}:stated_preference:{episode_id}"
        writes.append(queries.upsert_stated_belief(belief_id, delta))
        writes.append(queries.wire_belief_derived_from_episode(belief_id, episode_id))
        writes.append(queries.wire_belief_about_person(belief_id))

    # All owned writes commit together through the scoped-write seam (atomic, guarded).
    scoped.execute_write(writes)

    # AC-4.1 / AC-4.4: enqueue preference check for positive non-skipped outcomes.
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
