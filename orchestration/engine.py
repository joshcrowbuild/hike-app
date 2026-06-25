"""The Phase-0 engine: Scout -> Verifier -> Curator (code-orchestrated workflow).

A fixed, authored DAG — not an autonomous agent (Stage 4 §1):

    parse_intent  - mechanical-tier free-text -> structured query.
    Scout         - scoped Cypher candidate generation, capped to top-K.
    drive-prefilter - origin-relative reachability prune (Epic 013 S5; degrade-safe).
    Verifier      - JIT live probes via the kind-keyed registry; source-or-silence (#1);
                    never persisted (#3).
    Curator       - hard guardrail filter + judgment-tier taste ranking (+ drive term).
    present       - templated hedged, sourced feed lines.

`plan` composes the whole pipeline; every collaborator (graph session, the live-adapter
registry, the drive-time computer, the mechanical + judge providers) is injected via
`Runtime`, so the composition is testable with fakes. `build_runtime` wires the
production collaborators from config + clients (needs a live environment to actually run).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, cast

from graph.client import GraphClient, ScopedSession
from orchestration.adapters.base import (
    ConditionKind,
    DriveTimeComputer,
    LiveAdapter,
    Point,
    VerifiedFact,
)
from orchestration.adapters.registry import (
    TTLCache,
    default_cache,
    probes_for,
)
from orchestration.confidence import Confidence, compute, for_fact
from orchestration.config import Settings
from orchestration.curator import GuardrailVerdict, evaluate_guardrails, rank_ids
from orchestration.drive_time import prefilter, time_budget_s
from orchestration.intent import Intent, parse_intent
from orchestration.present import FeedLine, summarize_fact
from orchestration.providers.base import ModelProvider
from orchestration.providers.registry import resolve
from orchestration.scout import Candidate, scout
from orchestration.verifier import verify

log = logging.getLogger(__name__)

DEFAULT_RADIUS_M = 40_000.0
_M_PER_MILE = 1609.344


@dataclass(frozen=True)
class PlannedTrail:
    candidate: Candidate
    facts: dict[ConditionKind, VerifiedFact]
    confidences: dict[ConditionKind, Confidence]
    verdict: GuardrailVerdict


@dataclass(frozen=True)
class FeedCard:
    canonical_id: str
    name: str
    distance_mi: float | None
    lines: list[FeedLine]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class PlannedBatch:
    """The guardrail-passing trails plus feed-level notices (e.g. the once-per-feed
    drive-time degrade disclosure — Epic 005 AC-6.4)."""

    trails: list[PlannedTrail]
    notices: tuple[str, ...] = ()


@dataclass
class Runtime:
    session: ScopedSession
    # Live probes keyed by ConditionKind, primary->fallback within a kind (Epic 013).
    probes: dict[ConditionKind, list[LiveAdapter]]
    mechanical: tuple[ModelProvider, str] | None = None  # intent parse
    judge: tuple[ModelProvider, str] | None = None  # taste ranking (anonymous / no-overlay path)
    # The overlay-carrying taste-ranking judge — resolved local-forced so assembled
    # personal-overlay context can never egress to a cloud provider (Rule #5; Epic 014).
    # plan() selects this judge whenever overlay context is in play; the plain `judge`
    # above is used only on the anonymous, no-overlay path (Rule #2 cloud yardstick).
    personalized_judge: tuple[ModelProvider, str] | None = None
    # Per-source TTL cache for live probes (M3); origin-relative drive-time computer.
    cache: TTLCache | None = None
    drive_time: DriveTimeComputer | None = None
    drive_speed_kmh: float = 60.0  # radius->time-budget assumption (Decision 1.5)


@dataclass(frozen=True)
class Feed:
    query: str
    cards: list[FeedCard]
    notices: tuple[str, ...] = ()


def _latlon(point: Any) -> tuple[float, float] | None:
    if point is None:
        return None
    lat = getattr(point, "latitude", None)
    lon = getattr(point, "longitude", None)
    if lat is not None and lon is not None:
        return float(lat), float(lon)
    if isinstance(point, dict) and "latitude" in point and "longitude" in point:
        return float(point["latitude"]), float(point["longitude"])
    if isinstance(point, (tuple, list)) and len(point) == 2:
        return float(point[0]), float(point[1])
    return None


def _drive_minutes(fact: VerifiedFact | None) -> float | None:
    if fact is None or not isinstance(fact.value, dict):
        return None
    secs = fact.value.get("drive_seconds")
    if isinstance(secs, (int, float)) and not isinstance(secs, bool):
        return float(secs) / 60.0
    return None


def plan_from_origin(
    lat: float,
    lon: float,
    session: ScopedSession,
    probes: dict[ConditionKind, list[LiveAdapter]],
    *,
    radius_m: float = DEFAULT_RADIUS_M,
    k: int = 10,
    cache: TTLCache | None = None,
    drive_time: DriveTimeComputer | None = None,
    budget_s: float | None = None,
) -> PlannedBatch:
    """Scout near (lat, lon); optionally prune to drive-time reachability; verify each
    survivor's conditions; drop any that trip a hard guardrail. Drive-time facts are
    folded in at construction (after the guardrail check — they never reach
    `evaluate_guardrails`, AC-5.3)."""
    candidates = scout(lat, lon, session, radius_m=radius_m, k=k)

    drive_facts: dict[str, VerifiedFact] = {}
    notices: tuple[str, ...] = ()
    if drive_time is not None and budget_s is not None:
        res = prefilter(
            (lat, lon), candidates, drive_time, budget_s, coord_of=lambda c: _latlon(c.point)
        )
        candidates = res.kept
        drive_facts = res.facts_by_id
        notices = (res.disclosure,) if res.disclosure else ()

    planned: list[PlannedTrail] = []
    for candidate in candidates:
        coord = _latlon(candidate.point)
        if coord is None:
            log.debug("candidate %s has no point; probing at query origin", candidate.canonical_id)
            probe_point = Point(lat, lon)
        else:
            probe_point = Point(*coord)
        facts = verify(probe_point, probes, cache=cache)  # point kinds only (drive_time skipped)
        verdict = evaluate_guardrails(facts)
        if verdict.blocked:
            continue  # constraints are hard filters (Stage 4 §6)
        drive_fact = drive_facts.get(candidate.canonical_id)
        if drive_fact is not None:
            facts[ConditionKind.drive_time] = drive_fact  # folded in AFTER the guardrail check
        confidences = {kind: for_fact(fact) for kind, fact in facts.items()}
        planned.append(PlannedTrail(candidate, facts, confidences, verdict))
    return PlannedBatch(trails=planned, notices=notices)


def rank_plan(
    planned: list[PlannedTrail],
    provider: ModelProvider,
    model: str,
    *,
    profile: str | None = None,
) -> list[PlannedTrail]:
    """Reorder guardrail-passing trails by the judgment-tier taste ranking. Drive time
    enters ordering as an explicit term (a deterministic closer-by-road pre-order when
    every candidate has a time, plus a per-card hint to the judge) — never via
    confidence (rule #2): a long drive lowers position, not trust. Absence of a time is
    never treated as 'far' (AC-5.3)."""
    if not planned:
        return []
    drive_secs = {
        p.candidate.canonical_id: _drive_minutes(p.facts.get(ConditionKind.drive_time))
        for p in planned
    }
    ordered = planned
    if all(drive_secs[p.candidate.canonical_id] is not None for p in planned):
        # All else equal, a nearer-by-road trail is not ranked below a farther one.
        ordered = sorted(planned, key=lambda p: drive_secs[p.candidate.canonical_id] or 0.0)
    by_id = {p.candidate.canonical_id: p for p in ordered}
    items = [(p.candidate.canonical_id, p.candidate.name) for p in ordered]
    hints = {cid: f"~{mins:.0f} min drive" for cid, mins in drive_secs.items() if mins is not None}
    order = rank_ids(items, provider, model, profile=profile, hints=hints)
    return [by_id[cid] for cid in order if cid in by_id]


def feed_card(planned: PlannedTrail) -> FeedCard:
    lines = [
        summarize_fact(kind.value, fact, planned.confidences.get(kind) or compute())
        for kind, fact in planned.facts.items()
    ]
    dist = planned.candidate.distance_m
    return FeedCard(
        canonical_id=planned.candidate.canonical_id,
        name=planned.candidate.name,
        distance_mi=round(dist / _M_PER_MILE, 1) if dist is not None else None,
        lines=lines,
        warnings=planned.verdict.warnings,
    )


def plan(
    query: str,
    origin: tuple[float, float],
    runtime: Runtime,
    *,
    k: int = 10,
    viewer_id: str = "anonymous",
) -> Feed:
    """Full pipeline: parse intent -> scout+drive-prefilter+verify+guardrail-filter ->
    context assembly -> taste-rank -> templated feed cards.

    viewer_id is used for personal context assembly (AC-5.3: assembled AFTER guardrail
    filtering, BEFORE taste ranking; AC-5.4: assembled once, passed to one rank_ids call).
    """
    from orchestration.context_assembly import (
        assemble_context,
        fetch_beliefs,
        fetch_profile,
        fetch_relevant_episodes,
    )

    intent = parse_intent(query, *runtime.mechanical) if runtime.mechanical else Intent()
    radius = float(intent.radius_m) if intent.radius_m else DEFAULT_RADIUS_M
    budget_s = (
        time_budget_s(intent, radius_m=radius, drive_speed_kmh=runtime.drive_speed_kmh)
        if runtime.drive_time is not None
        else None
    )
    batch = plan_from_origin(
        origin[0],
        origin[1],
        runtime.session,
        runtime.probes,
        radius_m=radius,
        k=k,
        cache=runtime.cache,
        drive_time=runtime.drive_time,
        budget_s=budget_s,
    )
    planned = batch.trails

    # AC-5.3: context assembled AFTER guardrail filtering (planned is already filtered)
    # AC-5.4: assembled once, passed to single rank_ids call
    candidate_ids = [p.candidate.canonical_id for p in planned]
    beliefs = fetch_beliefs(viewer_id, runtime.session.run)
    profile = fetch_profile(viewer_id, runtime.session.run)
    episodes = fetch_relevant_episodes(viewer_id, candidate_ids, runtime.session.run)
    personal_context = assemble_context(beliefs, profile, episodes)

    # Merge intent profile with personal context (intent.profile wins if both set)
    combined_profile = intent.profile or (personal_context or None)

    # Overlay-carrying ranking MUST use the local-forced personalized judge so the
    # assembled personal context never reaches a cloud provider (Rule #5; Epic 014 C4).
    # The trigger is deliberately broadened beyond "overlay present" to "any
    # authenticated (non-anonymous) viewer OR non-empty overlay": a logged-in session
    # is private by default (Rule #5), so its ranking stays on-device even when context
    # happens to be empty this run — defense-in-depth against an assembly path that
    # silently empties personal_context for a viewer who does have overlay. This is
    # strictly more conservative than AC-1.4's overlay-only trigger, never less safe.
    # The plain cloud-allowed judge runs only the anonymous, no-overlay path, where
    # combined_profile is at most user free-text (intent.profile), never overlay.
    if viewer_id != "anonymous" or personal_context:
        judge = runtime.personalized_judge
    else:
        judge = runtime.judge
    if judge:
        planned = rank_plan(planned, judge[0], judge[1], profile=combined_profile)
    return Feed(query=query, cards=[feed_card(p) for p in planned], notices=batch.notices)


def build_runtime(settings: Settings, graph_client: GraphClient, viewer_id: str) -> Runtime:
    """Production wiring: resolve providers per tier, scope the session to the viewer,
    resolve live probes + the drive-time computer from the registry. Needs a live
    environment to actually run.

    Precondition (Epic 014 S3 / Rule #5): `viewer_id` is **already authenticated**
    by the caller; this function does not verify identity. Authentication happens at
    the edge (api layer); Stage 8's session/token system slots in there without
    re-auditing the engine. A non-anonymous `viewer_id` reaching here is trusted.

    The `personalized_judge` resolved here may receive assembled personal-overlay
    context as `profile=` and is therefore privacy-routed (Epic 014 AC-2.4): it is
    resolved with `touches_private_overlay=True`, forcing the local provider so the
    overlay can never egress to a cloud provider regardless of config (Rule #5 / C4).
    """
    mechanical = resolve("extract", settings)
    # Two judgment-tier judges, same tier, split by privacy (Epic 014 C4):
    #  - `judge`: per-config (cloud allowed) — used only on the anonymous/no-overlay path.
    #  - `personalized`: resolved touches_private_overlay=True so it is forced on-device.
    #    This is the judge that may receive assembled personal-overlay context as
    #    `profile=`; routing it local is structural, not contingent on config (Rule #5).
    judge = resolve("curate", settings)
    personalized = resolve("curate", settings, touches_private_overlay=True)
    # Resolve the live adapters once; the drive-time computer is the (region-agnostic)
    # drive_time adapter from that same set, so adapters are instantiated once per request.
    probes = probes_for(settings.live_region, settings)
    dt_adapters = probes.get(ConditionKind.drive_time)
    drive = cast(DriveTimeComputer, dt_adapters[0]) if dt_adapters else None
    return Runtime(
        session=graph_client.scoped_session(viewer_id),
        probes=probes,
        mechanical=(mechanical.provider, mechanical.model),
        judge=(judge.provider, judge.model),
        personalized_judge=(personalized.provider, personalized.model),
        cache=default_cache(),
        drive_time=drive,
        drive_speed_kmh=settings.drive_speed_kmh,
    )
