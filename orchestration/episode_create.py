"""Manual episode creation over HTTP — Epic 043 S5.

The first authenticated *write* path: a signed-in user submits a planned or
completed trip and it lands as a real `:Episode` owned by their verified `sub`.
This reuses the batch-only `queries.upsert_episode` builder (Epic 003) behind the
Epic-011 scoped-write seam — NO new write path, no owned-node Cypher authored
outside `graph.queries` (Rule #4). Watch-free by construction: every metric is
optional (this is a manual log, not a FIT parse), so a bare "I did this" still
creates a valid Episode.

`create_manual_episode` is pure orchestration over an injected `ScopedSession`, so
it unit-tests without a live database.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from graph import queries
from orchestration.logsafe import scrub_episode, scrub_viewer

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ManualEpisodeRequest:
    """A manual trip log. Everything but the client-supplied id is optional — a
    planned/completed trip may carry only a trail, or only a date."""

    client_episode_id: str  # caller's stable per-trip key (dedupes re-submits)
    canonical_id: str | None = None  # the trail it was on (world node), if known
    source: str = "manual"  # provenance marker on the Episode
    start_date: str | None = None  # YYYY-MM-DD; drives e.date (recency window)
    distance_m: float | None = None
    ascent_m: float | None = None
    descent_m: float | None = None
    moving_min: float | None = None
    duration_min: float | None = None


@dataclass(frozen=True)
class ManualEpisodeResult:
    episode_id: str
    owner_id: str
    canonical_id: str | None


def create_manual_episode(
    viewer_id: str,
    req: ManualEpisodeRequest,
    scoped,  # ScopedSession
) -> ManualEpisodeResult:
    """Create (or idempotently update) the viewer's manual Episode.

    All owned Cypher comes from `graph.queries`; `scoped.execute_write` guards each
    owned statement, injects `$viewer_id`, and commits the batch atomically. The
    Episode id embeds the owner (`ep:{viewer}:{client_id}`), so `owner_id` is part
    of the MERGE key — a foreign id can never re-own another member's node
    (structural ownership, not a naming convention). Returns the created ids.
    """
    episode_id = f"ep:{viewer_id}:{req.client_episode_id}"
    now = datetime.now(timezone.utc).isoformat()

    writes = [
        # Ensure the Person exists first (a fresh Supabase sub has none) so the
        # DID edge below actually attaches (its MATCH would otherwise no-op).
        queries.ensure_person(now),
        queries.upsert_episode(
            episode_id,
            # A manual log has no watch activity — reuse the client id as the
            # activity key so the Episode still carries a stable non-null handle.
            watch_activity_id=req.client_episode_id,
            source=req.source,
            distance_m=req.distance_m,
            ascent_m=req.ascent_m,
            descent_m=req.descent_m,
            moving_min=req.moving_min,
            duration_min=req.duration_min,
            avg_heart_rate=None,  # watch-free (Rule #6): enrichment, never required
            pace_on_grade=None,
            now=now,
            start_date=req.start_date,
        ),
        queries.wire_person_did_episode(episode_id),
    ]
    if req.canonical_id:
        writes.append(queries.wire_episode_on_trail(episode_id, req.canonical_id))

    scoped.execute_write(writes)  # atomic — all commit or none (Epic 011 seam)

    log.info(
        "manual episode written episode=%s viewer=%s trail=%s",
        scrub_episode(episode_id),
        scrub_viewer(viewer_id),
        req.canonical_id or "-",
    )
    return ManualEpisodeResult(
        episode_id=episode_id,
        owner_id=viewer_id,
        canonical_id=req.canonical_id,
    )
