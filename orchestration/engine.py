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

from graph import queries
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
from orchestration.curator import (
    CardWarning,
    ConditionUnavailable,
    GuardrailVerdict,
    evaluate_guardrails,
    is_outside_boundary_demoted,
    is_over_length_demoted,
    is_roadlike_demoted,
    rank_ids,
    valid_max_length_mi,
)
from orchestration.drive_time import prefilter, time_budget_s
from orchestration.intent import Intent, parse_intent
from orchestration.present import FeedLine, summarize_fact
from orchestration.providers.base import ModelProvider
from orchestration.providers.registry import resolve
from orchestration.scout import Candidate, scout
from orchestration.verifier import DEFAULT_MAX_WORKERS, verify_batch

log = logging.getLogger(__name__)

DEFAULT_RADIUS_M = 40_000.0
_M_PER_MILE = 1609.344

# Disclosed once per feed when personal context could not be applied (Rules #6/#7:
# enrichment degrades-and-discloses, never breaks the feed).
PERSONAL_CONTEXT_UNAVAILABLE_NOTICE = (
    "Personal context unavailable — showing general recommendations."
)


@dataclass(frozen=True)
class PlannedTrail:
    candidate: Candidate
    facts: dict[ConditionKind, VerifiedFact]
    confidences: dict[ConditionKind, Confidence]
    verdict: GuardrailVerdict
    # CDP-01 corroboration (spike): the corpus/SAME_AS layer is the one place genuine
    # multi-origin corroboration lives. `corpus_corroboration` is the count of distinct
    # upstream origins agreeing the trail exists (≥1, honest baseline); `corpus_sources`
    # names them; `corpus_confidence` is the score with that real count fed to the
    # corroboration axis. Live condition facts stay an honest single source (their
    # `confidences` carry corroboration=1) — only the corpus identity carries the count.
    # Carried on the plan for the corpus-confidence surface; the api response is
    # intentionally unchanged this PR (labels travel via present.py text instead).
    corpus_corroboration: int = 1
    corpus_sources: tuple[str, ...] = ()
    corpus_confidence: Confidence | None = None


@dataclass(frozen=True)
class UnavailableCondition:
    """One condition that couldn't be verified — disclosed on the card as a calm,
    source-honest note rather than causing the trail to be set aside (decision of
    2026-07-02; rule #6: live conditions are enrichment, never a dependency). `text`
    is ready-to-show ("cause (source)"), mirroring `SetAsideReason` below."""

    text: str
    source: str
    kind: str  # ConditionKind.value the gap came from, e.g. "weather"


@dataclass(frozen=True)
class FeedCard:
    canonical_id: str
    name: str
    distance_mi: float | None
    lines: list[FeedLine]
    # Prominent source-stamped hazard warnings the card wears (a VERIFIED hazard
    # shows, never hides — decision of 2026-07-01). Presentation only (Rule #2).
    warnings: tuple[CardWarning, ...]
    # Conditions that couldn't be verified — disclosed here, never a reason the
    # trail was held back (decision of 2026-07-02; rule #6). Presentation only.
    unavailable: tuple[UnavailableCondition, ...] = ()


@dataclass(frozen=True)
class SetAsideReason:
    """One source-stamped cause a trail was set aside (Epic 018 S5 AC-5.1). `text` is
    the ready-to-show disclosure ("cause (source)"); `source`/`kind` keep the pieces
    structured for the wire."""

    text: str
    source: str
    kind: str  # ConditionKind.value the block came from


@dataclass(frozen=True)
class SetAsideTrail:
    """A candidate a *verified* hard guardrail ruled out — a hard non-weather
    threshold (hazardous AQI). Disclosed, never silently dropped (Epic 018 S5
    AC-5.2): it carries its cause + source so the surface can show *why* it's set
    aside. An UNVERIFIABLE condition (a failed weather probe, a failed alerts
    sub-call) is NOT set aside as of 2026-07-02 — rule #1 still holds (a failed
    probe is never "clear"), but rule #6 means an outage must never blank the feed,
    so the trail stays a card carrying an `UnavailableCondition` disclosure instead.
    A VERIFIED hazard is not set aside either — it stays a card wearing a prominent
    warning (decision of 2026-07-01). A safety gate only — it never feeds
    ranking/confidence (Rule #2)."""

    canonical_id: str
    name: str
    reasons: tuple[SetAsideReason, ...]


@dataclass(frozen=True)
class PlannedBatch:
    """The guardrail-passing trails plus feed-level notices (e.g. the once-per-feed
    drive-time degrade disclosure — Epic 005 AC-6.4) and the trails a hard live
    guardrail set aside (Epic 018 S5): disclosed with cause + source, not dropped."""

    trails: list[PlannedTrail]
    notices: tuple[str, ...] = ()
    set_aside: tuple[SetAsideTrail, ...] = ()


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
    # Concurrency cap on the Verifier's live-probe fan-out (latency follow-up to Epic
    # 018 S6) — bounds how hard one /plan can hit a rate-limited third-party source
    # regardless of k. Config-driven via Settings.live_probe_max_workers.
    probe_max_workers: int = DEFAULT_MAX_WORKERS


@dataclass(frozen=True)
class Feed:
    query: str
    cards: list[FeedCard]
    notices: tuple[str, ...] = ()
    # Trails a hard live guardrail ruled out, disclosed with cause + source (Epic 018
    # S5 AC-5.2). Kept off the ranked `cards` — a safety set-aside, not a demotion.
    set_aside: tuple[SetAsideTrail, ...] = ()


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


def _corpus_corroboration(
    candidates: list[Candidate], session: ScopedSession
) -> tuple[dict[str, int], dict[str, tuple[str, ...]]]:
    """Read the distinct-origin corroboration count per candidate trail from the
    SAME_AS cluster (CDP-01 moat — the one place real corroboration lives). One batched
    world-read. Corroboration is *enrichment, not a dependency* (rule #6 in spirit): a
    read failure degrades to the honest count-as-1 baseline rather than blocking the
    feed."""
    ids = [c.canonical_id for c in candidates]
    counts: dict[str, int] = {}
    sources: dict[str, tuple[str, ...]] = {}
    if not ids:
        return counts, sources
    try:
        rows = session.run(queries.trail_source_corroboration(ids))
    except Exception:
        log.debug("corpus corroboration read failed; defaulting to count-as-1", exc_info=True)
        return counts, sources
    for row in rows:
        cid = row.get("canonical_id")
        if not cid:
            continue
        srcs = tuple(s for s in (row.get("sources") or []) if isinstance(s, str))
        sources[cid] = srcs
        raw = row.get("corroboration")
        counts[cid] = raw if isinstance(raw, int) and not isinstance(raw, bool) else len(srcs)
    return counts, sources


def _set_aside(candidate: Candidate, verdict: GuardrailVerdict) -> SetAsideTrail:
    """Build the disclosed set-aside record for a hard-blocked candidate (Epic 018 S5).
    Each block becomes a source-stamped reason line — the cause, then its source in
    parens — mirroring how `present.py` stamps a surfaced fact (AC-5.1/5.2)."""
    reasons = tuple(
        SetAsideReason(text=f"{b.reason} ({b.source})", source=b.source, kind=b.kind)
        for b in verdict.blocks
    )
    return SetAsideTrail(canonical_id=candidate.canonical_id, name=candidate.name, reasons=reasons)


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
    probe_max_workers: int = DEFAULT_MAX_WORKERS,
) -> PlannedBatch:
    """Scout near (lat, lon); optionally prune to drive-time reachability; verify each
    survivor's conditions; drop any that trip a hard guardrail. Drive-time facts are
    folded in at construction (after the guardrail check — they never reach
    `evaluate_guardrails`, AC-5.3). Live-condition verification runs as one batched,
    concurrent fan-out (`verify_batch`) across every candidate rather than probing
    them one at a time — the dominant cost of `/plan` (latency follow-up to Epic 018
    S6); `probe_max_workers` bounds total in-flight probes."""
    candidates = scout(lat, lon, session, radius_m=radius_m, k=k)

    drive_facts: dict[str, VerifiedFact] = {}
    notices: tuple[str, ...] = ()
    if drive_time is not None and budget_s is not None:
        res = prefilter(
            (lat, lon),
            candidates,
            drive_time,
            budget_s,
            coord_of=lambda c: _latlon(c.trailhead_point) or _latlon(c.point),
        )
        candidates = res.kept
        drive_facts = res.facts_by_id
        notices = (res.disclosure,) if res.disclosure else ()

    # CDP-01: distinct-origin corroboration per candidate from the SAME_AS corpus layer.
    corr_by_id, sources_by_id = _corpus_corroboration(candidates, session)

    # Which point kinds the Verifier will actually attempt — lets the guardrails tell
    # "weather probed but no source answered" (unverifiable → disclosed on the card,
    # rule #1 + #6) apart from "weather not probed in this deployment" (no signal
    # either way).
    probed_kinds = frozenset(
        kind
        for kind, adapters in probes.items()
        if adapters and kind is not ConditionKind.drive_time
    )

    probe_points: list[Point] = []
    for candidate in candidates:
        coord = _latlon(candidate.point)
        if coord is None:
            log.debug("candidate %s has no point; probing at query origin", candidate.canonical_id)
            probe_points.append(Point(lat, lon))
        else:
            probe_points.append(Point(*coord))
    # The live-condition fan-out: every candidate's (point, kind) probes run
    # concurrently across a bounded pool, aligned back to `candidates` by index —
    # byte-for-byte the same facts a sequential `verify()` per candidate would
    # produce (point kinds only; drive_time is skipped, folded in below instead).
    facts_by_candidate = verify_batch(
        probe_points, probes, cache=cache, max_workers=probe_max_workers
    )

    planned: list[PlannedTrail] = []
    set_aside: list[SetAsideTrail] = []
    for candidate, facts in zip(candidates, facts_by_candidate, strict=True):
        verdict = evaluate_guardrails(facts, probed_kinds=probed_kinds)
        if verdict.blocked:
            # Hard filter (Stage 4 §6) — a *verified* hard-threshold block is set
            # aside with a source-stamped reason, never silently dropped (Epic 018 S5
            # AC-5.1/5.2). Neither an unverifiable condition (rule #6, 2026-07-02) nor
            # a VERIFIED hazard (decision of 2026-07-01) takes this path — both stay
            # cards, carrying their disclosure/warning respectively.
            set_aside.append(_set_aside(candidate, verdict))
            continue
        drive_fact = drive_facts.get(candidate.canonical_id)
        if drive_fact is not None:
            facts[ConditionKind.drive_time] = drive_fact  # folded in AFTER the guardrail check
        # Live condition facts are single-source by construction → honest count-as-1
        # (never imply corroboration we don't have; spike item 2). The real distinct-
        # origin count is the corpus identity's, passed to the corroboration axis below.
        confidences = {kind: for_fact(fact, corroboration=1) for kind, fact in facts.items()}
        corr = max(1, corr_by_id.get(candidate.canonical_id, 1))
        srcs = sources_by_id.get(candidate.canonical_id, ())
        # The corpus identity is the one fact that carries genuine multi-origin
        # corroboration (CDP-01). authority/freshness reflect the slow, bulk-ingested
        # corpus tier; the count is the live SAME_AS independence count.
        corpus_confidence = compute(authority="tier1", freshness="slow", corroboration=corr)
        planned.append(
            PlannedTrail(
                candidate,
                facts,
                confidences,
                verdict,
                corpus_corroboration=corr,
                corpus_sources=srcs,
                corpus_confidence=corpus_confidence,
            )
        )
    return PlannedBatch(trails=planned, notices=notices, set_aside=tuple(set_aside))


def rank_plan(
    planned: list[PlannedTrail],
    provider: ModelProvider,
    model: str,
    *,
    profile: str | None = None,
    max_length_mi: float | None = None,
) -> list[PlannedTrail]:
    """Reorder guardrail-passing trails by the judgment-tier taste ranking. Drive time
    enters ordering as an explicit term (a deterministic closer-by-road pre-order when
    every candidate has a time, plus a per-card hint to the judge) — never via
    confidence (rule #2): a long drive lowers position, not trust. Absence of a time is
    never treated as 'far' (AC-5.3). `max_length_mi` (Intent.filters, already validated
    by the caller) SOFT-demotes over-length candidates alongside the roadlike/boundary
    signals — never a hard drop (rule #2); a candidate with no known length_mi is
    never demoted."""
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
    # Feed-quality de-rank: sink roadlike/access ways (persisted OSM way-type) below
    # real trails — soft + reversible, never a drop, fire/dike roads kept (see
    # `is_roadlike_demoted`). A no-op until a re-ingest persists `way_type` (older
    # nodes carry None → never demoted).
    # Two soft, reversible de-rank signals feed the same demotion set: the roadlike/
    # access name signal (persisted way-type) and the Phase-2 spatial signal (the
    # trail's point outside the region's protected-area boundary). Either sinks an
    # ambiguous way below real trails; neither drops it. Both are no-ops until a
    # re-ingest persists the respective flag (older nodes carry None).
    demote_ids = {
        p.candidate.canonical_id
        for p in ordered
        if is_roadlike_demoted(p.candidate.way_type, p.candidate.name)
        or is_outside_boundary_demoted(
            p.candidate.way_type, p.candidate.name, p.candidate.outside_boundary
        )
        or is_over_length_demoted(p.candidate.length_mi, max_length_mi)
    }
    if demote_ids:
        log.debug("rank_plan: de-ranking %d roadlike/access way(s)", len(demote_ids))
    order = rank_ids(items, provider, model, profile=profile, hints=hints, demote_ids=demote_ids)
    return [by_id[cid] for cid in order if cid in by_id]


def _unavailable_condition(u: ConditionUnavailable) -> UnavailableCondition:
    """Build the disclosed unavailable-condition record (mirrors `_set_aside`'s
    cause-then-source-in-parens shape)."""
    return UnavailableCondition(text=f"{u.reason} ({u.source})", source=u.source, kind=u.kind)


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
        unavailable=tuple(_unavailable_condition(u) for u in planned.verdict.unavailable),
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
        probe_max_workers=runtime.probe_max_workers,
    )
    planned = batch.trails

    # AC-5.3: context assembled AFTER guardrail filtering (planned is already filtered)
    # AC-5.4: assembled once, passed to single rank_ids call
    # Personal context is enrichment, never a dependency (Rules #6/#7): any failure in
    # assembly degrades to the anonymous-quality feed with a disclosed notice — a 500
    # here would make the private overlay a hard dependency of the world feed.
    candidate_ids = [p.candidate.canonical_id for p in planned]
    personal_context = ""
    context_degraded = False
    try:
        beliefs = fetch_beliefs(viewer_id, runtime.session.run)
        profile = fetch_profile(viewer_id, runtime.session.run)
        episodes = fetch_relevant_episodes(viewer_id, candidate_ids, runtime.session.run)
        personal_context = assemble_context(beliefs, profile, episodes)
    except Exception:
        log.exception("personal-context assembly failed; serving the anonymous-quality feed")
        context_degraded = True

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
    use_personal_judge = viewer_id != "anonymous" or bool(personal_context)
    judge = runtime.personalized_judge if use_personal_judge else runtime.judge
    # Validated once, up front: a malformed LLM-parsed value (bool/str/list/negative)
    # no-ops the filter instead of crashing either rank_plan call below.
    max_length_mi = valid_max_length_mi(intent.filters.get("max_length_mi"))
    if judge:
        try:
            planned = rank_plan(
                planned,
                judge[0],
                judge[1],
                profile=combined_profile,
                max_length_mi=max_length_mi,
            )
        except Exception:
            if not use_personal_judge:
                raise  # anonymous path: a judge failure is not a personal-context failure
            # The local-forced personalized judge is unavailable (e.g. a hosted deploy
            # with no on-device model). Personal context is enrichment (Rule #6): rank
            # with the plain judge exactly as the anonymous path would — the overlay is
            # STRIPPED from the fallback profile so it still never egresses (Rule #5).
            log.exception("personalized ranking failed; serving the anonymous-quality feed")
            context_degraded = True
            if runtime.judge:
                planned = rank_plan(
                    planned,
                    runtime.judge[0],
                    runtime.judge[1],
                    profile=intent.profile or None,
                    max_length_mi=max_length_mi,
                )
    notices = batch.notices
    if context_degraded:
        notices = notices + (PERSONAL_CONTEXT_UNAVAILABLE_NOTICE,)
    # AC-5.2/5.3: set-aside trails ride the feed as a disclosed, cause+source list —
    # kept off `cards` (ranking never sees them; a hazard is a safety gate, not a
    # taste demotion). Ranking above operates only on the guardrail-passing `planned`.
    return Feed(
        query=query,
        cards=[feed_card(p) for p in planned],
        notices=notices,
        set_aside=batch.set_aside,
    )


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
        probe_max_workers=settings.live_probe_max_workers,
    )
