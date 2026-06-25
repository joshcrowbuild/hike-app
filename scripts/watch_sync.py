"""Watch sync poller — Epic 004 S4.

Iterates the enabled device adapters and feeds each activity's FIT bytes to the
EXISTING `ingestion/ingest_episode.py` pipeline (parse → Episode → belief queue),
unchanged. Per-adapter failure isolation (rule #6): one vendor down never stops
the others. Idempotent: MERGE on the namespaced `watch_activity_id` (AC-4.3).

Collaborators are injected so the poller is testable with fakes — no live device
call in the test suite. `main()` wires the real registry, the real
parse_fit/match_trail/create_episode, and a real scoped session.

Run (manual / cron):  python -m scripts.watch_sync --owner josh
Always-on host is deferred (S6-12); Phase 1 syncs on machine wake / manual trigger.
"""

from __future__ import annotations

import argparse
import logging
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ingestion.watch.base import AdapterHealth, DeviceAdapter

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

# Injected collaborator types — all default to the real ingest_episode functions
# in main(); tests pass fakes. None of this is new parse/Episode/belief code (AC-4.4).
ParseFn = Callable[[bytes], Any]  # bytes -> FITSummary
MatchFn = Callable[[Any, Any], str | None]  # (summary, session) -> canonical_id | None
CreateFn = Callable[..., str]  # create_episode(summary, cid, owner, session, *, belief_queue)


@dataclass
class SyncResult:
    adapter: str
    health: str
    episodes: int = 0
    error: str | None = None


@dataclass
class SyncReport:
    results: list[SyncResult] = field(default_factory=list)

    @property
    def total_episodes(self) -> int:
        return sum(r.episodes for r in self.results)


def sync_adapter(
    adapter: DeviceAdapter,
    owner_id: str,
    since: datetime | None,
    *,
    parse: ParseFn,
    match: MatchFn,
    create: CreateFn,
    session: Any,
    belief_queue: Any,
) -> SyncResult:
    """Sync ONE adapter into the existing pipeline. Returns a result; never raises
    for a non-OK health state (degrade-and-disclose). Hard exceptions are caught by
    run_sync so a crash in one vendor cannot stop the others (rule #6)."""
    health = adapter.health()
    if health is not AdapterHealth.OK:
        log.warning("%s health=%s — skipping this cycle", adapter.name, health.value)
        return SyncResult(adapter=adapter.name, health=health.value)

    count = 0
    for raw in adapter.fetch_new_activities(since):
        # Per-activity isolation: a poison activity must not strand its siblings.
        # Without this, an exception here unwinds the whole adapter and (for vendors
        # that honour `since`) the watermark advances past never-ingested activities,
        # silently losing them. Mirrors base.fetch_new_activities' skip-on-failure.
        try:
            summary = parse(raw.fit_bytes)
            # Inject the namespaced id so Episode MERGE keys are vendor-unique (AC-1.2/4.3).
            summary.watch_activity_id = raw.id
            canonical_id = match(summary, session)
            create(summary, canonical_id, owner_id, session, belief_queue=belief_queue)
            count += 1
        except Exception as exc:
            log.warning("%s: activity %s failed, skipping: %s", adapter.name, raw.id, exc)
            continue

    return SyncResult(adapter=adapter.name, health=health.value, episodes=count)


def run_sync(
    adapters: list[DeviceAdapter],
    owner_id: str,
    *,
    since: datetime | None,
    parse: ParseFn,
    match: MatchFn,
    create: CreateFn,
    session: Any,
    belief_queue: Any,
    drain: Callable[[Any], int] | None = None,
) -> SyncReport:
    """Iterate enabled adapters with per-adapter isolation (rule #6). One adapter
    raising or reporting non-OK health is logged and does not stop the others."""
    report = SyncReport()
    for adapter in adapters:
        try:
            result = sync_adapter(
                adapter,
                owner_id,
                since,
                parse=parse,
                match=match,
                create=create,
                session=session,
                belief_queue=belief_queue,
            )
        except Exception as exc:  # rule #6: isolate — one vendor crash ≠ pipeline down
            log.error("%s sync failed: %s", adapter.name, exc)
            report.results.append(SyncResult(adapter=adapter.name, health="error", error=str(exc)))
            continue
        report.results.append(result)

    if drain is not None:
        drained = drain(belief_queue)
        log.info("Belief queue drained: %d tasks", drained)
    return report


# ── Production wiring ─────────────────────────────────────────────────────────


def _parse_fit_bytes(fit_bytes: bytes) -> Any:
    """Bridge bytes → the EXISTING path-based parse_fit (ingest_episode unchanged).

    Writes to a temp file and calls parse_fit. This is plumbing, not FIT-parsing
    logic — AC-4.4 holds (no new parse/Episode/belief code)."""
    from ingestion.ingest_episode import parse_fit

    with tempfile.NamedTemporaryFile(suffix=".fit", delete=True) as tmp:
        tmp.write(fit_bytes)
        tmp.flush()
        return parse_fit(Path(tmp.name))


def most_recent_episode_time(owner_id: str, session: Any) -> datetime | None:
    """AC-4.2: bound the API window to activities newer than the latest Episode."""
    rows = session.run(
        (
            "MATCH (e:Episode {owner_id: $owner}) RETURN max(e.created_at) AS latest",
            {"owner": owner_id},
        )
    )
    if rows and rows[0].get("latest"):
        latest = rows[0]["latest"]
        # create_episode stores created_at as an ISO STRING (ingest_episode.py),
        # so the watermark comes back as a str — coerce to an aware datetime or the
        # adapters that call since.timestamp() (Coros) crash every cycle.
        if isinstance(latest, str):
            try:
                return datetime.fromisoformat(latest)
            except ValueError:
                return None
        return latest.to_native() if hasattr(latest, "to_native") else latest
    return None


def assert_local_sensitivity_routing(settings: Any) -> None:
    """AC-4.5: enforce at the entrypoint that any LLM call in the watch-ingest path
    routes to the LOCAL provider (watch data is the most-sensitive overlay class —
    S6-9). The current pipeline makes no LLM call, but establishing the invariant
    here means any future addition (e.g. conditions_note extraction) is forced local."""
    from orchestration.providers.registry import resolve

    resolution = resolve("normalize", settings, touches_private_overlay=True)
    if resolution.provider_name != "local":
        raise RuntimeError(
            "Watch ingest must route LLM calls to the local provider (S6-9); "
            f"sensitivity routing resolved to {resolution.provider_name!r}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync hiking activities from enabled devices")
    parser.add_argument("--owner", required=True, help="member_id of the Person (e.g. 'josh')")
    args = parser.parse_args()

    from graph.client import GraphClient
    from ingestion.ingest_episode import create_episode, match_trail
    from ingestion.watch.registry import enabled_adapters
    from orchestration.belief_update import BeliefUpdateQueue
    from orchestration.config import Settings

    settings = Settings.from_env()
    assert_local_sensitivity_routing(settings)  # AC-4.5 — fail loudly at the boundary

    adapters = enabled_adapters(settings)
    if not adapters:
        log.info("No watch adapters enabled (ADVENTURE_WATCH_ADAPTERS empty) — nothing to sync")
        return

    gc = GraphClient(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
    try:
        scoped = gc.scoped_session(args.owner)
        since = most_recent_episode_time(args.owner, scoped)
        queue = BeliefUpdateQueue()
        report = run_sync(
            adapters,
            args.owner,
            since=since,
            parse=_parse_fit_bytes,
            match=match_trail,
            create=create_episode,
            session=scoped,
            belief_queue=queue,
            # Drain through the per-owner scoped-write seam (Epic 011). The old
            # make_runner(neo_session) drain passed a 2-arg runner the belief
            # writers never matched (it silently failed) and is incompatible with
            # the session-factory drain contract.
            drain=lambda q: q.drain(gc.scoped_session),
        )
    finally:
        gc.close()

    print("\nWatch sync report:")
    for r in report.results:
        print(
            f"  {r.adapter}: health={r.health} episodes={r.episodes}"
            + (f" error={r.error}" if r.error else "")
        )
    print(f"  total episodes: {report.total_episodes}")


if __name__ == "__main__":
    main()
