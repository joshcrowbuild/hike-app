"""The Phase-0 engine: Scout -> Verifier -> Curator (code-orchestrated workflow).

A fixed, authored DAG — not an autonomous agent (Stage 4 §1):

    parse_intent  - mechanical-tier free-text -> structured query.
    Scout         - scoped Cypher candidate generation, capped to top-K.
    Verifier      - JIT live probes; source-or-silence in code; never persisted (#3).
    Curator       - hard guardrail filter + judgment-tier taste ranking.
    present       - templated hedged, sourced feed lines.

`plan` composes the whole pipeline; every collaborator (graph session, probes, the
mechanical + judge providers) is injected via `Runtime`, so the composition is
testable with fakes. `build_runtime` wires the production collaborators from config
+ clients (needs a live environment to actually run).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from graph.client import GraphClient, ScopedSession
from orchestration.adapters.base import VerifiedFact
from orchestration.confidence import Confidence, compute, for_fact
from orchestration.config import Settings
from orchestration.curator import GuardrailVerdict, evaluate_guardrails, rank_ids
from orchestration.intent import Intent, parse_intent
from orchestration.present import FeedLine, summarize_fact
from orchestration.providers.base import ModelProvider
from orchestration.providers.registry import resolve
from orchestration.scout import Candidate, scout
from orchestration.verifier import Probe, build_probes, verify

DEFAULT_RADIUS_M = 40_000.0
_M_PER_MILE = 1609.344


@dataclass(frozen=True)
class PlannedTrail:
    candidate: Candidate
    facts: dict[str, VerifiedFact]
    confidences: dict[str, Confidence]
    verdict: GuardrailVerdict


@dataclass(frozen=True)
class FeedCard:
    canonical_id: str
    name: str
    distance_mi: float | None
    lines: list[FeedLine]
    warnings: tuple[str, ...]


@dataclass
class Runtime:
    session: ScopedSession
    probes: dict[str, Probe]
    mechanical: tuple[ModelProvider, str] | None = None  # intent parse
    judge: tuple[ModelProvider, str] | None = None  # taste ranking (anonymous / no-overlay path)
    # The overlay-carrying taste-ranking judge — resolved local-forced so assembled
    # personal-overlay context can never egress to a cloud provider (Rule #5; Epic 014).
    # plan() selects this judge whenever overlay context is in play; the plain `judge`
    # above is used only on the anonymous, no-overlay path (Rule #2 cloud yardstick).
    personalized_judge: tuple[ModelProvider, str] | None = None


@dataclass(frozen=True)
class Feed:
    query: str
    cards: list[FeedCard]


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


def plan_from_origin(
    lat: float,
    lon: float,
    session: ScopedSession,
    probes: dict[str, Probe],
    *,
    radius_m: float = DEFAULT_RADIUS_M,
    k: int = 10,
) -> list[PlannedTrail]:
    """Scout near (lat, lon), verify each candidate's conditions, drop any that
    trip a hard guardrail. Distance-ordered (taste ranking applied separately)."""
    planned: list[PlannedTrail] = []
    for candidate in scout(lat, lon, session, radius_m=radius_m, k=k):
        point = _latlon(candidate.point)
        if point is None:
            clat, clon = lat, lon
            import logging as _log

            _log.getLogger(__name__).debug(
                "candidate %s has no point; probing at query origin", candidate.canonical_id
            )
        else:
            clat, clon = point
        facts = verify(clat, clon, probes)
        verdict = evaluate_guardrails(facts)
        if verdict.blocked:
            continue  # constraints are hard filters (Stage 4 §6)
        confidences = {kind: for_fact(fact) for kind, fact in facts.items()}
        planned.append(PlannedTrail(candidate, facts, confidences, verdict))
    return planned


def rank_plan(
    planned: list[PlannedTrail],
    provider: ModelProvider,
    model: str,
    *,
    profile: str | None = None,
) -> list[PlannedTrail]:
    """Reorder guardrail-passing trails by the judgment-tier taste ranking. The
    soft half of the Curator; confidence is not an input (rule #2)."""
    by_id = {p.candidate.canonical_id: p for p in planned}
    items = [(p.candidate.canonical_id, p.candidate.name) for p in planned]
    order = rank_ids(items, provider, model, profile=profile)
    return [by_id[cid] for cid in order if cid in by_id]


def feed_card(planned: PlannedTrail) -> FeedCard:
    lines = [
        summarize_fact(kind, fact, planned.confidences.get(kind) or compute())
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
    """Full pipeline: parse intent -> scout+verify+guardrail-filter -> context assembly
    -> taste-rank -> templated feed cards.

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
    planned = plan_from_origin(
        origin[0], origin[1], runtime.session, runtime.probes, radius_m=radius, k=k
    )

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
    return Feed(query=query, cards=[feed_card(p) for p in planned])


def build_runtime(settings: Settings, graph_client: GraphClient, viewer_id: str) -> Runtime:
    """Production wiring: resolve providers per tier, scope the session to the
    viewer, build probes from config. Needs a live environment to actually run.

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
    return Runtime(
        session=graph_client.scoped_session(viewer_id),
        probes=build_probes(settings),
        mechanical=(mechanical.provider, mechanical.model),
        judge=(judge.provider, judge.model),
        personalized_judge=(personalized.provider, personalized.model),
    )
