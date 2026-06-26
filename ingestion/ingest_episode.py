"""Stage 6 — Episode ingestion from a FIT file (stub / Phase-1 start).

Parses a Garmin/Coros FIT file, extracts the session summary fields, matches
to a CanonicalTrail via GPS overlap or activity title, creates an Episode node,
and queues a capability belief update.

Usage:
    python -m ingestion.ingest_episode --fit path/to/activity.fit --owner josh
    python -m ingestion.ingest_episode --fit path/to/activity.fit --owner josh --dry-run

Requires: pip install fitdecode
FIT parsing is local-only (raw biometric data never leaves the machine — Rule #10).

Stage 6 design: docs/research/stage-6-watch-integration.md
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from graph import queries

if TYPE_CHECKING:
    from graph.client import ScopedSession

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

_FIT_REQUIRED = "fitdecode"


@dataclass
class FITSummary:
    """Extracted fields from a FIT session message.

    `gps_track` (the full polyline) and `start_time` are captured for the
    commons de-id transform (Epic 010) — the full track is consumed in-transform
    to produce the endpoint-trimmed commons twin and is NEVER written to the
    :Episode (Rule #3 / §35: raw biometrics + full geometry stay off the graph).
    """

    watch_activity_id: str  # derived from filename; real ID comes from Garmin Connect
    total_distance_m: float | None
    total_ascent_m: float | None
    total_descent_m: float | None
    moving_time_s: float | None
    total_time_s: float | None
    avg_heart_rate: int | None
    start_lat: float | None
    start_lon: float | None
    end_lat: float | None
    end_lon: float | None
    sport: str | None
    # Commons-fork inputs (Epic 010); consumed in-transform, never on the Episode.
    start_time: datetime | None = None
    gps_track: list[tuple[float, float]] = field(default_factory=list)


def parse_fit(path: Path) -> FITSummary:
    """Parse a FIT file and return session summary. Requires fitdecode."""
    try:
        import fitdecode  # type: ignore[import]
    except ImportError:
        log.error("fitdecode not installed. Run: pip install fitdecode")
        sys.exit(1)

    summary = FITSummary(
        watch_activity_id=f"file:{path.stem}",
        total_distance_m=None,
        total_ascent_m=None,
        total_descent_m=None,
        moving_time_s=None,
        total_time_s=None,
        avg_heart_rate=None,
        start_lat=None,
        start_lon=None,
        end_lat=None,
        end_lon=None,
        sport=None,
    )

    # GPS track points for start/end extraction
    gps_points: list[tuple[float, float]] = []

    with fitdecode.FitReader(path) as fit:
        for frame in fit:
            if not isinstance(frame, fitdecode.FitDataMessage):
                continue

            if frame.name == "session":

                def _get(name: str):
                    return frame.get_value(name, fallback=None)

                summary.total_distance_m = _get("total_distance")
                summary.total_ascent_m = _get("total_ascent")
                summary.total_descent_m = _get("total_descent")
                summary.moving_time_s = _get("total_moving_time") or _get("total_timer_time")
                summary.total_time_s = _get("total_elapsed_time")
                summary.avg_heart_rate = _get("avg_heart_rate")
                summary.sport = _get("sport")
                summary.start_time = _get("start_time")  # commons month bucket (Epic 010)

            elif frame.name == "record":
                lat_raw = frame.get_value("position_lat", fallback=None)
                lon_raw = frame.get_value("position_long", fallback=None)
                if lat_raw is not None and lon_raw is not None:
                    # FIT stores lat/lon as semicircles; convert to degrees
                    lat = lat_raw * (180 / 2**31)
                    lon = lon_raw * (180 / 2**31)
                    gps_points.append((lat, lon))

    if gps_points:
        summary.start_lat, summary.start_lon = gps_points[0]
        summary.end_lat, summary.end_lon = gps_points[-1]
        # Full polyline retained ONLY for the commons de-id transform (Epic 010);
        # it is endpoint-trimmed for the commons twin and never reaches the Episode.
        summary.gps_track = gps_points

    return summary


def compute_pace_on_grade(summary: FITSummary) -> float | None:
    """Naismith-normalised pace: (distance_m + ascent_m * 10) / moving_time_s → min/km."""
    if not summary.total_distance_m or not summary.moving_time_s:
        return None
    ascent = summary.total_ascent_m or 0.0
    effective_m = summary.total_distance_m + ascent * 10
    if effective_m <= 0:
        return None
    pace_s_per_m = summary.moving_time_s / effective_m
    return round(pace_s_per_m * 1000 / 60, 2)  # min/km


def match_trail(summary: FITSummary, session) -> str | None:
    """Find nearest CanonicalTrail to activity start point. Returns canonical_id or None."""
    if summary.start_lat is None or summary.start_lon is None:
        return None
    rows = session.run(
        (
            """
        MATCH (t:CanonicalTrail)
        WHERE t.point IS NOT NULL
        RETURN t.canonical_id AS canonical_id, t.name AS name,
               point.distance(t.point, point({latitude: $lat, longitude: $lon})) AS dist_m
        ORDER BY dist_m ASC
        LIMIT 1
        """,
            {"lat": summary.start_lat, "lon": summary.start_lon},
        )
    )
    if not rows:
        return None
    row = rows[0]
    dist_m = row.get("dist_m") or 9999
    if dist_m > 2000:  # more than 2km from nearest trail centroid → no match
        log.warning("Nearest trail '%s' is %.0fm away — no match", row.get("name"), dist_m)
        return None
    log.info("Matched to '%s' (%.0fm away)", row.get("name"), dist_m)
    return row["canonical_id"]


def create_episode(
    summary: FITSummary,
    canonical_id: str | None,
    owner_id: str,
    session: ScopedSession,
    *,
    belief_queue=None,  # BeliefUpdateQueue | None — enqueues update after write
    commons_salt: str | None = None,
) -> str:
    """Write the Episode + wires + the de-identified commons twin in ONE managed
    transaction (Epic 011 seam + Epic 010 fork). Returns episode_id.

    All owned-node Cypher is authored in `graph.queries`; `session.execute_write`
    guards each owned statement, injects `$viewer_id`, and commits the batch
    atomically — so the Episode and its born-severed `:CommonsObservation` either
    both persist or neither does (Stage 9 §2.1). The session is scoped to
    `owner_id`, so `$viewer_id` resolves to the owner the episode is created for.
    """
    episode_id = f"ep:{owner_id}:{summary.watch_activity_id}"
    _pace = compute_pace_on_grade(summary)  # compute once; reused for Episode + UpdateTask
    now = datetime.now(timezone.utc).isoformat()
    # The FIT activity's calendar date drives e.date — the field context assembly's
    # 18-month retrieval window filters on (Epic 003 AC-3.2). Null-safe if unparsed.
    start_date = summary.start_time.date().isoformat() if summary.start_time else None

    writes: list[tuple[str, dict]] = [
        queries.upsert_episode(
            episode_id,
            watch_activity_id=summary.watch_activity_id,
            source="fit_file",
            distance_m=summary.total_distance_m,
            ascent_m=summary.total_ascent_m,
            descent_m=summary.total_descent_m,
            moving_min=round(summary.moving_time_s / 60, 1) if summary.moving_time_s else None,
            duration_min=round(summary.total_time_s / 60, 1) if summary.total_time_s else None,
            avg_heart_rate=summary.avg_heart_rate,
            pace_on_grade=_pace,
            now=now,
            start_date=start_date,
        ),
        queries.wire_person_did_episode(episode_id),
    ]
    if canonical_id:
        writes.append(queries.wire_episode_on_trail(episode_id, canonical_id))

    # Commons fork (Epic 010): a born-severed, de-identified :CommonsObservation,
    # committed in the SAME transaction as the Episode (Stage 9 §2.1). It fires
    # regardless of Person.commons_opt_in — the write is unlinkable, so accretion
    # is not a contribution of identifiable data; consent gates Stage-9 *exposure*,
    # not the write (§8.2 / S9-17). Skipped only when no writer salt is configured.
    if commons_salt:
        from ingestion.commons_fork import build_observation

        obs = build_observation(
            member_id=owner_id,
            salt=commons_salt,
            trail_id=canonical_id,  # FK-by-value scalar; null when unmatched (no edge)
            pace_on_grade=_pace,
            distance_m=summary.total_distance_m,
            ascent_m=summary.total_ascent_m,
            start_time=summary.start_time,
            gps_track=summary.gps_track,  # full track consumed here; never on the Episode
        )
        writes.append(queries.create_commons_observation(obs))
    else:
        log.warning("Commons fork skipped for %s: no writer salt configured", episode_id)

    session.execute_write(writes)  # atomic — all commit or none (AC-2.0 / AC-2.5)

    # Stamp the profile's last-episode date (Epic 003). A separate owner-scoped write,
    # not folded into the commons-fork transaction above, so the Epic-010 atomic batch
    # stays exactly Episode + wires + the severed twin. Runs only with a parsed date;
    # the running-maximum builder ignores an older backfill.
    if start_date:
        session.run_write(queries.upsert_physical_profile_last_episode(start_date))

    # Enqueue belief update (S1: AC-1.1, AC-1.2, AC-1.3)
    if belief_queue is not None:
        from orchestration.belief_update import UpdateTask

        belief_queue.enqueue(
            UpdateTask(
                episode_id=episode_id,
                owner_id=owner_id,
                distance_m=summary.total_distance_m,
                ascent_m=summary.total_ascent_m,
                pace_on_grade=_pace,  # reuse already-computed value, avoid drift
            )
        )

    return episode_id


def ingest_episode(fit_path: Path, owner_id: str, *, dry_run: bool = False) -> dict:
    log.info("Parsing FIT file: %s", fit_path)
    summary = parse_fit(fit_path)
    pace = compute_pace_on_grade(summary)

    log.info(
        "FIT summary: dist=%.1fkm ascent=%.0fm moving=%.0fmin pace=%.1f min/km hr=%s",
        (summary.total_distance_m or 0) / 1000,
        summary.total_ascent_m or 0,
        (summary.moving_time_s or 0) / 60,
        pace or 0,
        summary.avg_heart_rate or "n/a",
    )

    if dry_run:
        log.info("DRY-RUN — would create Episode for owner=%s", owner_id)
        return {"watch_activity_id": summary.watch_activity_id, "pace_on_grade": pace}

    from graph.client import GraphClient
    from orchestration.config import Settings

    settings = Settings.from_env()
    gc = GraphClient(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)

    try:
        from orchestration.belief_update import BeliefUpdateQueue

        belief_queue = BeliefUpdateQueue()
        scoped = gc.scoped_session(owner_id)
        trail_id = match_trail(summary, scoped)
        episode_id = create_episode(
            summary,
            trail_id,
            owner_id,
            scoped,
            belief_queue=belief_queue,
            commons_salt=settings.commons_writer_salt,
        )
        # Drain synchronously through the scoped-write seam (Epic 011), scoped per
        # task owner (Phase 1; async in Phase 2). Replaces the bare make_runner drain.
        belief_queue.drain(gc.scoped_session)
        log.info("Created Episode %s (trail=%s)", episode_id, trail_id or "unmatched")
        return {"episode_id": episode_id, "canonical_id": trail_id, "pace_on_grade": pace}
    finally:
        gc.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a FIT file as an Episode")
    parser.add_argument("--fit", required=True, help="Path to .fit file")
    parser.add_argument("--owner", required=True, help="member_id of the Person (e.g. 'josh')")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    fit_path = Path(args.fit)
    if not fit_path.exists():
        log.error("FIT file not found: %s", fit_path)
        sys.exit(1)

    result = ingest_episode(fit_path, args.owner, dry_run=args.dry_run)
    print("\nEpisode ingest result:")
    for k, v in result.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
