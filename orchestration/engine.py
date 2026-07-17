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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
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
from orchestration.adapters.nws import NwsRegionAdapter
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
    filter_preference_hints,
    is_outside_boundary_demoted,
    is_over_length_demoted,
    is_roadlike_demoted,
    rank_ids,
    valid_max_length_mi,
)
from orchestration.drive_time import prefilter, time_budget_s
from orchestration.feed_cache import (
    CachedPlan,
    FeedCache,
    FeedCacheKey,
    default_feed_cache,
    default_pending_store,
)
from orchestration.intent import Intent, parse_intent
from orchestration.present import FeedLine, provider_short, summarize_fact
from orchestration.providers.base import ModelProvider
from orchestration.providers.registry import resolve
from orchestration.region_conditions import RegionConditions, derive_region_conditions
from orchestration.scout import Candidate, scout, scout_by_id, scout_by_name
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
    # The point kinds the Verifier actually attempted for this plan (Epic 018 S4):
    # lets the card tell "probed but no source answered" (unavailable) apart from
    # "not probed in this deployment" (not_fetched). Additive default keeps every
    # existing constructor call valid.
    probed_kinds: frozenset[ConditionKind] = frozenset()


# ── Per-kind condition disposition (Epic 018 S4 / CDP-02) ────────────────────
# The card's per-kind condition summary: every point kind gets a disposition so an
# absent condition is legible, distinct silence — never a blank or a false-clear.
# Canonical order keeps the wire (and the rendered card) deterministic.
_CONDITION_KIND_ORDER = (
    ConditionKind.weather,
    ConditionKind.air,
    ConditionKind.fire,
    ConditionKind.water,
    ConditionKind.closures,
    ConditionKind.permits,
)

# Per-kind freshness horizons (seconds) for the `stale_degraded` state: a fact older
# than this at SERVE time is still shown (with its age — honesty is relocation, not
# deletion) but flagged "last known — may have changed". Set to 2x each adapter's TTL
# (nws/airnow/firms/nps 1h · usgs_water 30m · ridb 1d — CDP-08 volatility windows):
# inside 2xTTL a fact is at worst one refresh stale; beyond it the value is past its
# rate-of-change horizon. Only an engine-layer cache re-render (Epic 039 S2) can
# normally age a fact this far.
_STALE_HORIZON_S: dict[ConditionKind, float] = {
    ConditionKind.weather: 7200.0,
    ConditionKind.air: 7200.0,
    ConditionKind.fire: 7200.0,
    ConditionKind.water: 3600.0,
    ConditionKind.closures: 7200.0,
    ConditionKind.permits: 172_800.0,
}


@dataclass(frozen=True)
class ConditionStatus:
    """One kind's disposition on one card (Epic 018 S4 / CDP-02). `state` vocabulary:

      present         — a sourced fact renders as a feed line
      stale_degraded  — a sourced fact renders, but is past its freshness horizon
      no_hazard       — the source answered "nothing to flag" (fire 0 detections,
                        closures 0 relevant alerts) — checked-clear, never assumed
      no_data         — the source answered "nothing covers this spot" (no gauge in
                        range, no NPS unit in range)
      unavailable     — the kind was probed and no source answered (couldn't verify —
                        never "clear", rule #1)
      not_fetched     — the kind is not probed in this deployment (no signal either way)

    `source`/`checked_at` are set exactly when a source actually answered; `detail`
    carries the adapter's own disclosure for the no_data case. Presentation only —
    never feeds ranking or confidence (Rule #2)."""

    kind: str  # ConditionKind.value, e.g. "weather"
    state: str
    source: str = ""  # short provider name when a source backs this state
    checked_at: datetime | None = None  # the answering fact's fetch time
    detail: str = ""  # adapter disclosure, e.g. the no-gauge radius note


def _is_coverage_gap(kind: ConditionKind, value: Any) -> bool:
    """True for a fact that is a sourced "nothing covers this spot" answer (the
    CDP-02 `no_data` state) rather than a reading — see usgs_water/nps_alerts."""
    if not isinstance(value, dict):
        return False
    if kind is ConditionKind.water:
        return value.get("gauge_available") is False
    if kind is ConditionKind.closures:
        return value.get("in_range") is False
    return False


def _is_checked_clear(kind: ConditionKind, value: Any) -> bool:
    """True for a hazard-shaped kind whose source answered "nothing to flag" (the
    CDP-02 `no_hazard` state). Only fire/closures are hazard-shaped — a zero count IS
    the all-clear; value kinds (weather/air/water/permits) always carry a reading and
    are never "clear"."""
    if not isinstance(value, dict):
        return False
    if kind is ConditionKind.fire:
        return value.get("hotspot_count") == 0
    if kind is ConditionKind.closures:
        return value.get("count") == 0
    return False


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
    # Per-kind condition disposition (Epic 018 S4 / CDP-02): one entry per point
    # kind in `_CONDITION_KIND_ORDER`, so absent conditions are legible, distinct
    # silence on the wire — never a blank the client must guess about.
    conditions: tuple[ConditionStatus, ...] = ()


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
    # Engine-layer anonymous ranked-plan cache (Epic 039 S2). None = disabled (the
    # feed_cache_ttl_s==0 kill switch) → plan() is a byte-identical no-op vs. before
    # this story. Never read/written for a non-anonymous viewer_id (Rule #5).
    feed_cache: FeedCache | None = None
    # Whether THIS request's plan() was served from the feed cache — set by plan(),
    # read by the api layer for metrics honesty (AC-2.9). Lives on the per-request
    # Runtime (not FeedCache.stats) because a shared-counter before/after delta
    # misattributes a concurrent request's hit to a request that actually computed
    # and spent tokens (adversarial-review finding, 2026-07-08).
    feed_cache_hit: bool = False
    # Short-TTL holding pen for anonymous phase-1 plans awaiting their conditions
    # call (Epic 040 D7) — a SEPARATE store from `feed_cache` by construction, so an
    # all-`not_fetched` phase-1 plan can never be served as a full plan. None = the
    # two-phase server kill switch (ADVENTURE_TWO_PHASE_ENABLED=0) or a hermetic
    # test runtime. Anonymous-only, like `feed_cache` (Rule #5): a non-anonymous
    # phase-1 plan is never stored (the key carries no viewer identity).
    phase1_pending: FeedCache | None = None
    # The region-level NWS probe (frame-conditions-wave §5, epic-054 S2/S3) —
    # forecast periods + recent station observations, fetched ONCE per plan at the
    # query origin (`_fetch_region_raw`), never per candidate. None = no NWS
    # credential configured (source-or-silence: `region_conditions` stays absent).
    region_probe: LiveAdapter | None = None


@dataclass(frozen=True)
class Feed:
    query: str
    cards: list[FeedCard]
    notices: tuple[str, ...] = ()
    # Trails a hard live guardrail ruled out, disclosed with cause + source (Epic 018
    # S5 AC-5.2). Kept off the ranked `cards` — a safety set-aside, not a demotion.
    set_aside: tuple[SetAsideTrail, ...] = ()
    # Area-level conditions (frame-conditions-wave §5, epic-054 S5 AC-5.1): None
    # when not attempted this phase (a phase-1 shell, or no region probe
    # configured) — distinct from "attempted, degraded", which is a
    # `RegionConditions` whose members are individually null.
    region_conditions: RegionConditions | None = None
    # True whenever the judge fell back to generic ranking this plan (Q8 / S5
    # AC-5.2) — a structured twin of `PERSONAL_CONTEXT_UNAVAILABLE_NOTICE`.
    personalization_degraded: bool = False


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
    Each block becomes a source-stamped reason line — the cause, then its short
    provider name in parens (D3 consistency pass: the same calm label a condition
    line or a card warning wears, never the raw domain-suffixed source) — mirroring
    how `present.py` stamps a surfaced fact (AC-5.1/5.2). `source` itself stays the
    fact's full provenance, preserved for a future inspectable detail surface."""
    reasons = tuple(
        SetAsideReason(
            text=f"{b.reason} ({provider_short(b.source)})", source=b.source, kind=b.kind
        )
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


def _plan_from_candidates(
    candidates: list[Candidate],
    session: ScopedSession,
    probes: dict[ConditionKind, list[LiveAdapter]],
    *,
    fallback_lat: float,
    fallback_lon: float,
    drive_facts: dict[str, VerifiedFact] | None = None,
    notices: tuple[str, ...] = (),
    cache: TTLCache | None = None,
    probe_max_workers: int = DEFAULT_MAX_WORKERS,
    verify: bool = True,
) -> PlannedBatch:
    """The post-Scout tail shared by every candidate-generation path (origin-relative
    `plan_from_origin` and name-search `search_trails`, Epic 038): verify each
    candidate's conditions, drop any that trip a hard guardrail, fold in corpus
    corroboration + (when supplied) drive-time facts. Live-condition verification
    runs as one batched, concurrent fan-out (`verify_batch`) across every candidate
    rather than probing them one at a time — the dominant cost of `/plan` (latency
    follow-up to Epic 018 S6); `probe_max_workers` bounds total in-flight probes.

    `fallback_lat`/`fallback_lon` stand in for a candidate with no `point` of its own
    (a query-origin fallback on the spatial path; a first-candidate fallback on the
    name-search path, where there is no query origin at all — see `search_trails`).

    `verify=False` is the Epic 040 phase-1 path: the live-probe fan-out is skipped
    entirely (zero `probe()` calls for any point kind) and `probed_kinds` stays
    empty, so every point kind honestly classifies `not_fetched` — nothing was
    fetched, so nothing is asserted, warned about, disclosed, or set aside (rule
    #1's contrapositive)."""
    drive_facts = drive_facts or {}

    # CDP-01: distinct-origin corroboration per candidate from the SAME_AS corpus layer.
    # B4 (Epic 039 mitigation ladder): this read is independent of the live-probe
    # fan-out below, so it runs on one worker thread concurrently with the fan-out
    # instead of adding its own serial graph round trip. Thread-safe because
    # `ScopedSession.run` opens a fresh driver session per call (graph/client.py
    # read_runner; the neo4j Driver itself is thread-safe) and nothing else touches
    # `session` until the result is joined after the fan-out. Same function, same
    # inputs, joined at the same consumption point — byte-identical outputs.
    corr_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="corroboration")
    corr_future = corr_pool.submit(_corpus_corroboration, candidates, session)
    corr_pool.shutdown(wait=False)  # no more work; the thread exits once the read completes

    # Which point kinds the Verifier will actually attempt — lets the guardrails tell
    # "weather probed but no source answered" (unverifiable → disclosed on the card,
    # rule #1 + #6) apart from "weather not probed in this deployment" (no signal
    # either way). On the phase-1 path (verify=False) NOTHING is attempted, so this
    # stays empty and every kind classifies `not_fetched` (Epic 040 D2).
    probed_kinds = (
        frozenset(
            kind
            for kind, adapters in probes.items()
            if adapters and kind is not ConditionKind.drive_time
        )
        if verify
        else frozenset()
    )

    if verify:
        probe_points: list[Point] = []
        for candidate in candidates:
            coord = _latlon(candidate.point)
            if coord is None:
                log.debug(
                    "candidate %s has no point; probing at query origin", candidate.canonical_id
                )
                probe_points.append(Point(fallback_lat, fallback_lon))
            else:
                probe_points.append(Point(*coord))
        # The live-condition fan-out: every candidate's (point, kind) probes run
        # concurrently across a bounded pool, aligned back to `candidates` by index —
        # byte-for-byte the same facts a sequential `verify()` per candidate would
        # produce (point kinds only; drive_time is skipped, folded in below instead).
        facts_by_candidate = verify_batch(
            probe_points, probes, cache=cache, max_workers=probe_max_workers
        )
    else:
        # Phase 1 (Epic 040 S1 AC-1.1): zero live probes — every candidate gets an
        # empty facts dict, so `evaluate_guardrails` below has nothing to block,
        # warn, or disclose on (empty facts + empty probed_kinds → empty verdict).
        facts_by_candidate = [{} for _ in candidates]
    # Join the overlapped corroboration read. `_corpus_corroboration` catches its own
    # read failures (degrading to the honest count-as-1 baseline, rule #6), so this
    # `result()` re-raises nothing in practice — the degrade path is unchanged.
    corr_by_id, sources_by_id = corr_future.result()

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
        # corpus tier; the count is the live SAME_AS independence count. source_kind is
        # explicitly "aggregated" (not the for_fact default "primary"): a single
        # upstream provider (OSM alone, not yet SAME_AS-matched to USGS/USFS/NPS) is
        # genuinely unverified structural data, same as an aggregated live source — it
        # must earn "stated" via real cross-provider corroboration (corr >= 2), not
        # get an institutional-singularity pass the way one NWS office does (CDP-06
        # retune; see orchestration/confidence.py).
        corpus_confidence = compute(
            authority="tier1", freshness="slow", corroboration=corr, source_kind="aggregated"
        )
        planned.append(
            PlannedTrail(
                candidate,
                facts,
                confidences,
                verdict,
                corpus_corroboration=corr,
                corpus_sources=srcs,
                corpus_confidence=corpus_confidence,
                probed_kinds=probed_kinds,
            )
        )
    return PlannedBatch(trails=planned, notices=notices, set_aside=tuple(set_aside))


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
    verify: bool = True,
) -> PlannedBatch:
    """Scout near (lat, lon); optionally prune to drive-time reachability; verify each
    survivor's conditions; drop any that trip a hard guardrail. Drive-time facts are
    folded in at construction (after the guardrail check — they never reach
    `evaluate_guardrails`, AC-5.3).

    `verify=False` is the Epic 040 phase-1 path (see `_plan_from_candidates`). Scout
    and the drive prefilter (its facts are origin-relative, not point conditions) run
    exactly as the full path; the rest — live verification, corroboration, guardrail
    filtering, PlannedTrail construction — is `_plan_from_candidates` (Epic 038: shared
    with the name-search path, `search_trails`)."""
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

    return _plan_from_candidates(
        candidates,
        session,
        probes,
        fallback_lat=lat,
        fallback_lon=lon,
        drive_facts=drive_facts,
        notices=notices,
        cache=cache,
        probe_max_workers=probe_max_workers,
        verify=verify,
    )


def search_trails(
    query_text: str,
    session: ScopedSession,
    probes: dict[ConditionKind, list[LiveAdapter]],
    *,
    k: int = 10,
    cache: TTLCache | None = None,
    probe_max_workers: int = DEFAULT_MAX_WORKERS,
    verify: bool = True,
) -> PlannedBatch:
    """Trail-name search (Epic 038 / B001 Problem A): `scout_by_name` -> the same
    verify/guardrail/corroboration tail `plan_from_origin` uses, so name-matched
    trails flow through the identical Scout -> Verifier -> Curator pipeline as
    origin-based `/plan` — cards carry sourced+timestamped conditions and confidence
    (rule #1), never a raw graph dump. No name match -> an honest empty `PlannedBatch`
    (never an error; the API layer's `/search` renders that as an empty `FeedResponse`).

    There is no query origin on this path, so a point-less candidate's probe
    fallback is the FIRST candidate in the batch that DOES have a resolvable point
    (arbitrary but stable — any matched trail's neighborhood is a reasonable place to
    probe from) rather than a lat/lon the caller never supplied. In the pathological
    case where NO candidate in the whole batch has a point (an ingest gap, never
    observed in practice — `CanonicalTrail.point`/`Trailhead.point` are populated by
    every ingestion path), there is no sane fallback coordinate at all: rather than
    probe a real-but-meaningless location (e.g. Null Island, `(0, 0)`), live
    verification is skipped entirely for this batch (`verify=False` — every point kind
    honestly classifies `not_fetched`, mirroring the Epic 040 phase-1 disclosure
    rather than fabricating a location no candidate is actually near)."""
    candidates = scout_by_name(query_text, session, k=k)
    if not candidates:
        return PlannedBatch(trails=[])

    fallback = next(
        (
            coord
            for c in candidates
            if (coord := (_latlon(c.point) or _latlon(c.trailhead_point))) is not None
        ),
        None,
    )
    if fallback is None:
        log.warning(
            "search_trails: no candidate in a %d-result batch has a resolvable point; "
            "skipping live verification rather than probing a fabricated location",
            len(candidates),
        )
        fallback_lat, fallback_lon = 0.0, 0.0
        verify = False
    else:
        fallback_lat, fallback_lon = fallback

    return _plan_from_candidates(
        candidates,
        session,
        probes,
        fallback_lat=fallback_lat,
        fallback_lon=fallback_lon,
        cache=cache,
        probe_max_workers=probe_max_workers,
        verify=verify,
    )


def plan_trail_by_id(
    canonical_id: str,
    session: ScopedSession,
    probes: dict[ConditionKind, list[LiveAdapter]],
    *,
    cache: TTLCache | None = None,
    probe_max_workers: int = DEFAULT_MAX_WORKERS,
    verify: bool = True,
) -> PlannedBatch:
    """Trail-by-id card fetch (Epic 045 / S2): `scout_by_id` -> the same verify/
    guardrail/corroboration tail `search_trails` uses, so a trail fetched by id flows
    through the identical Scout -> Verifier -> Curator pipeline as `/plan` and `/search`
    — the card carries sourced+timestamped conditions and confidence (rule #1), never a
    raw graph dump. Unknown id -> an honest empty `PlannedBatch` (never an error; the
    API layer's `/trail/{id}/card` renders that as an empty `FeedResponse`).

    Like `search_trails`, there is no query origin, so the fallback for a point-less
    candidate (never observed in practice) is the candidate's point if it has one, or
    zero-verify (skip live probes, `verify=False`) if even the single result has no point."""
    candidates = scout_by_id(canonical_id, session)
    if not candidates:
        return PlannedBatch(trails=[])

    # A by-id fetch returns 0 or 1 trail, so there is at most one candidate to extract
    # a fallback coordinate from.
    fallback = next(
        (
            coord
            for c in candidates
            if (coord := (_latlon(c.point) or _latlon(c.trailhead_point))) is not None
        ),
        None,
    )
    if fallback is None:
        log.warning(
            "plan_trail_by_id: candidate %s has no resolvable point; "
            "skipping live verification rather than probing a fabricated location",
            canonical_id,
        )
        fallback_lat, fallback_lon = 0.0, 0.0
        verify = False
    else:
        fallback_lat, fallback_lon = fallback

    return _plan_from_candidates(
        candidates,
        session,
        probes,
        fallback_lat=fallback_lat,
        fallback_lon=fallback_lon,
        cache=cache,
        probe_max_workers=probe_max_workers,
        verify=verify,
    )


def rank_plan(
    planned: list[PlannedTrail],
    provider: ModelProvider,
    model: str,
    *,
    profile: str | None = None,
    filters: dict[str, object] | None = None,
) -> list[PlannedTrail]:
    """Reorder guardrail-passing trails by the judgment-tier taste ranking. Drive time
    enters ordering as an explicit term (a deterministic closer-by-road pre-order when
    every candidate has a time, plus a per-card hint to the judge) — never via
    confidence (rule #2): a long drive lowers position, not trust. Absence of a time is
    never treated as 'far' (AC-5.3).

    `filters` is the mechanical-tier parser's `Intent.filters` (dog/difficulty/
    max_length_mi). All three are SOFT signals only (Rule #2 — demote, never hard-
    drop): `max_length_mi` sinks over-budget candidates via `is_over_length_demoted`
    (same stable-partition demotion as the roadlike/boundary de-ranks); `dog` and
    `difficulty` have no persisted corpus property yet, so they ride as a documented
    hint in the judge's profile text instead (`filter_preference_hints`) until real
    graph props exist. Values are validated defensively — a malformed mechanical-
    tier parse (bool/str/negative/missing) no-ops rather than crashing."""
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
    # Three soft, reversible de-rank signals feed the same demotion set: the roadlike/
    # access name signal (persisted way-type), the Phase-2 spatial signal (the
    # trail's point outside the region's protected-area boundary), and the hiker's
    # requested max_length_mi (Intent.filters). Any of the three sinks a candidate
    # below the rest; none of them drops it. All are no-ops absent the backing data
    # (way_type/outside_boundary/length_mi all default to None on an un-backfilled
    # corpus → never demoted).
    filters = filters or {}
    max_length_mi = valid_max_length_mi(filters.get("max_length_mi"))
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
        log.debug("rank_plan: de-ranking %d roadlike/access/over-length way(s)", len(demote_ids))
    # dog/difficulty have no corpus property to demote against yet — surfaced as a
    # documented soft hint on the judge's profile text instead (Rule #2).
    hint = filter_preference_hints(filters)
    if hint:
        profile = f"{profile}\n{hint}" if profile else hint
    # CDP-01 corroboration, carried per-trail on PlannedTrail already (Epic 026a) —
    # handed to the Curator's rescue-only pass (default OFF; see
    # `curator.apply_corroboration_rescue`), which can lift a demoted way back out
    # when an authoritative source independently corroborates it. Never adds a
    # demotion of its own.
    corroboration = {p.candidate.canonical_id: p.corpus_corroboration for p in ordered}
    corroboration_sources = {p.candidate.canonical_id: p.corpus_sources for p in ordered}
    order = rank_ids(
        items,
        provider,
        model,
        profile=profile,
        hints=hints,
        demote_ids=demote_ids,
        corroboration=corroboration,
        corroboration_sources=corroboration_sources,
    )
    return [by_id[cid] for cid in order if cid in by_id]


def _unavailable_condition(u: ConditionUnavailable) -> UnavailableCondition:
    """Build the disclosed unavailable-condition record (mirrors `_set_aside`'s
    cause-then-source-in-parens shape)."""
    return UnavailableCondition(text=f"{u.reason} ({u.source})", source=u.source, kind=u.kind)


def _condition_summary(
    planned: PlannedTrail, render_now: datetime
) -> tuple[tuple[ConditionStatus, ...], list[ConditionKind]]:
    """Classify every point kind for one card (Epic 018 S4 / CDP-02) and name which
    kinds render as feed lines. Pure presentation — never feeds ranking (Rule #2):

      fact is a coverage-gap answer  → no_data   (silence, no line)
      fact is a checked-clear answer → no_hazard (silence, no line)
      fact past its horizon          → stale_degraded (the line still renders, aged)
      fact fresh                     → present   (renders as a line)
      probed, no fact                → unavailable (couldn't verify — never "clear")
      not probed in this deployment  → not_fetched
    """
    statuses: list[ConditionStatus] = []
    line_kinds: list[ConditionKind] = []
    for kind in _CONDITION_KIND_ORDER:
        fact = planned.facts.get(kind)
        if fact is None:
            state = "unavailable" if kind in planned.probed_kinds else "not_fetched"
            statuses.append(ConditionStatus(kind=kind.value, state=state))
            continue
        src = provider_short(fact.source)
        if _is_coverage_gap(kind, fact.value):
            statuses.append(
                ConditionStatus(
                    kind=kind.value,
                    state="no_data",
                    source=src,
                    checked_at=fact.fetched_at,
                    detail=fact.disclosures[0] if fact.disclosures else "",
                )
            )
            continue
        if _is_checked_clear(kind, fact.value):
            statuses.append(
                ConditionStatus(
                    kind=kind.value, state="no_hazard", source=src, checked_at=fact.fetched_at
                )
            )
            continue
        age_s = (render_now - fact.fetched_at).total_seconds()
        state = "stale_degraded" if age_s > _STALE_HORIZON_S.get(kind, 7200.0) else "present"
        statuses.append(
            ConditionStatus(kind=kind.value, state=state, source=src, checked_at=fact.fetched_at)
        )
        line_kinds.append(kind)
    return tuple(statuses), line_kinds


def feed_card(planned: PlannedTrail, *, now: datetime | None = None) -> FeedCard:
    """Render one card's condition lines + the per-kind condition summary. `now` is
    threaded to `summarize_fact` so a cache hit can re-render freshness against
    serve-time rather than capture-time (`_render_feed` below is the only caller that
    ever passes a non-None `now`); `None` here means "real wall-clock now", identical
    to today's behavior.

    A coverage-gap or checked-clear answer (no_data / no_hazard) renders as legible
    silence in `conditions`, not as a feed line — "0 detections nearby" is exactly the
    calm-clear CDP-02's silence states exist for. Its source + timestamp still travel
    on the ConditionStatus, so nothing sourced is dropped (honesty relocated, never
    deleted). The drive-time line is origin-relative, not a point condition — it stays
    a line and has no ConditionStatus entry."""
    render_now = now or datetime.now(timezone.utc)
    conditions, line_kinds = _condition_summary(planned, render_now)
    lines = [
        summarize_fact(
            kind.value, planned.facts[kind], planned.confidences.get(kind) or compute(), now=now
        )
        for kind in line_kinds
    ]
    drive_fact = planned.facts.get(ConditionKind.drive_time)
    if drive_fact is not None:
        lines.append(
            summarize_fact(
                ConditionKind.drive_time.value,
                drive_fact,
                planned.confidences.get(ConditionKind.drive_time) or compute(),
                now=now,
            )
        )
    dist = planned.candidate.distance_m
    return FeedCard(
        canonical_id=planned.candidate.canonical_id,
        name=planned.candidate.name,
        distance_mi=round(dist / _M_PER_MILE, 1) if dist is not None else None,
        lines=lines,
        warnings=planned.verdict.warnings,
        unavailable=tuple(_unavailable_condition(u) for u in planned.verdict.unavailable),
        conditions=conditions,
    )


def _anon_key(query: str, origin: tuple[float, float], k: int) -> FeedCacheKey:
    """Cache key for the anonymous plan cache (Epic 039 S2). The caller gates this to
    `viewer_id == "anonymous"` (Rule #5) — no private identity can ever enter this key.

    3-decimal point rounding (~111m) deliberately MATCHES the probe TTLCache's own
    `_key` rounding (`adapters/registry.py`), not a finer one: within one 3-decimal
    cell the probe layer already returns identical facts and drive-time, so the
    ranked order is already identical there — this adds no aliasing beyond what the
    probe layer already permits, and a finer rounding would only lower the hit rate.

    Region is intentionally NOT in the key: `FeedCache` is a per-process singleton
    that serves exactly one fixed `settings.region`/`live_region` for the process's
    whole life (it dies empty on redeploy/restart), so region is a process-level
    invariant here, not a per-request one. (Open question if multi-region-per-process
    is ever built — would need region threaded through `Runtime`.)
    """
    lat, lon = origin
    return (query, round(lat, 3), round(lon, 3), k)


def _fetch_region_raw(origin: tuple[float, float], runtime: Runtime) -> VerifiedFact | None:
    """The RAW region-level NWS fetch (forecast periods + recent station
    observations) — ONE probe per plan at the query origin, the simplest honest
    region-representative anchor available (there is no separate region-centroid
    concept in this codebase; the origin the hiker is planning from IS the region
    the frame's conditions describe). Never per candidate (AC-2.4). Routed through
    the same per-source TTL cache every other live probe uses (`Runtime.cache`) so
    a repeat within the adapter's TTL costs nothing — `when` is deliberately never
    passed here (see `NwsRegionAdapter`): the raw fetch doesn't vary by day, only
    its render-time selection does. `None` when no region probe is configured (no
    NWS credential) or the fetch itself failed (source-or-silence)."""
    if runtime.region_probe is None:
        return None
    point = Point(*origin)
    if runtime.cache is not None:
        return runtime.cache.probe(runtime.region_probe, point)
    return runtime.region_probe.probe(point)


def _compute_plan(
    query: str,
    origin: tuple[float, float],
    runtime: Runtime,
    *,
    k: int = 10,
    viewer_id: str = "anonymous",
    verify: bool = True,
) -> CachedPlan:
    """Full pipeline: parse intent -> scout+drive-prefilter+verify+guardrail-filter ->
    context assembly -> taste-rank. Returns the cacheable `CachedPlan` rather than a
    rendered `Feed` — `_render_feed` below does the (re-)rendering.

    `verify=False` (Epic 040 S1) skips ONLY the live-probe fan-out (see
    `plan_from_origin`); the taste rank below runs exactly as the full path's —
    same judge tier, same demotion signals, drive hints included (AC-1.3). The
    result must NEVER be written to the anonymous FeedCache: an all-`not_fetched`
    plan served to a later full request would be a silent verification skip
    (`orchestration/two_phase.py` owns that discipline — this function never
    touches the cache either way).

    viewer_id is used for personal context assembly (AC-5.3: assembled AFTER guardrail
    filtering, BEFORE taste ranking; AC-5.4: assembled once, passed to one rank_ids call).

    MERGE-SENSITIVE (Epic 039 S2): the anonymous outcome must stay byte-identical to
    before this split — `context_degraded` stays False and `use_personal_judge` stays
    False on that path, and the anonymous judge-failure re-raise below is load-
    bearing: because it raises from inside this function, `plan()`'s cache `put` is
    never reached, so a failed run is never cached (AC-2.5).
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
        verify=verify,
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
    # Anonymous viewers have no private overlay to assemble — skip the three
    # owner-scoped Neo4j reads entirely (they return empty for
    # owner_id=="anonymous" anyway). A deliberate skip is NOT a degrade:
    # context_degraded stays False so PERSONAL_CONTEXT_UNAVAILABLE_NOTICE is
    # never emitted (Rule #6 enrichment-skip vs. Rule #1 disclosure distinction).
    if viewer_id != "anonymous":
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
    if judge:
        try:
            planned = rank_plan(
                planned, judge[0], judge[1], profile=combined_profile, filters=intent.filters
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
                    filters=intent.filters,
                )
    notices = batch.notices
    if context_degraded:
        notices = notices + (PERSONAL_CONTEXT_UNAVAILABLE_NOTICE,)
    # Region-level conditions (frame-conditions-wave §5, epic-054 S2/S3): ONE probe
    # at the query origin, only on the live-verifying path — phase 1 (verify=False)
    # stays genuinely probe-free (D2), exactly like the per-candidate fan-out above.
    # RAW (unselected-by-day) so a cache hit here is reused regardless of which
    # `when` a later request wants (see `_fetch_region_raw`/`region_conditions.py`).
    region_raw = _fetch_region_raw(origin, runtime) if verify else None
    # AC-5.2/5.3: set-aside trails ride the CachedPlan as a disclosed, cause+source
    # list — kept off `planned` (ranking never sees them; a hazard is a safety gate,
    # not a taste demotion). Ranking above operates only on the guardrail-passing
    # `planned`. Rendering into `FeedCard`s happens in `_render_feed`, never here —
    # this is the one boundary a cache sits below (see feed_cache.py).
    return CachedPlan(
        planned=tuple(planned),
        notices=notices,
        set_aside=batch.set_aside,
        region_raw=region_raw,
        # Q8 / S5 AC-5.2: the SAME condition that emits the notice above, as a
        # structured flag the wire can key a banner off of — never a second,
        # independently-derived signal.
        personalization_degraded=context_degraded,
    )


def _render_feed(
    query: str, cached: CachedPlan, *, now: datetime | None = None, when: str | None = None
) -> Feed:
    """The ONLY place `feed_card` runs — so a live-condition line's freshness is
    always rendered against serve-time `now`, cache hit or not. Caching the rendered
    `Feed` instead of `CachedPlan` would freeze the relative-age copy at capture time
    (see feed_cache.py's module docstring); this function is what keeps that from
    ever happening. `region_conditions` gets the SAME discipline: `cached.region_raw`
    is the RAW fetch (day-independent), and `when` — the CURRENT caller's frame, not
    whatever a cache hit's original caller wanted — drives which days actually render
    (a cache hit must never serve a stranger's forecast day)."""
    render_now = now or datetime.now(timezone.utc)
    region_conditions = (
        derive_region_conditions(cached.region_raw, when=when, now=render_now)
        if cached.region_raw is not None
        else None
    )
    return Feed(
        query=query,
        cards=[feed_card(p, now=now) for p in cached.planned],
        notices=cached.notices,
        set_aside=cached.set_aside,
        region_conditions=region_conditions,
        personalization_degraded=cached.personalization_degraded,
    )


def plan(
    query: str,
    origin: tuple[float, float],
    runtime: Runtime,
    *,
    k: int = 10,
    viewer_id: str = "anonymous",
    when: str | None = None,
) -> Feed:
    """Thin wrapper: on a cache hit, skip `_compute_plan` entirely (including the
    ~0.3s intent parse) and re-render the cached plan against serve-time freshness;
    on a miss, compute once (single-flight collapses concurrent identical misses),
    cache only on success, then render. Keying on the raw `query` string (not the
    parsed intent) means two queries that happen to parse identically won't share a
    cache entry — accepted (Epic 039 S2 design: the intent-parse cost is small).

    `when` (frame-conditions-wave S2) is NOT part of the cache key (`_anon_key`):
    it only selects which forecast days `_render_feed` shows, a render-time
    concern re-applied on every call, cache hit or not (see `_render_feed`)."""
    fc = runtime.feed_cache
    key = _anon_key(query, origin, k) if (fc is not None and viewer_id == "anonymous") else None
    runtime.feed_cache_hit = False
    if key is None:
        cached = _compute_plan(query, origin, runtime, k=k, viewer_id=viewer_id)
        return _render_feed(query, cached, when=when)
    assert fc is not None  # narrows for mypy; implied by `key is not None` above

    computed = False

    def _compute() -> CachedPlan:
        nonlocal computed
        computed = True
        return _compute_plan(query, origin, runtime, k=k, viewer_id=viewer_id)

    cached = fc.get_or_compute(key, _compute)
    # Request-local hit disposition: `computed` flips only if THIS thread ran the
    # pipeline, so a hit-after-wait (another thread filled the gate) still counts as
    # a hit — this request spent no tokens/probes. Runtime is per-request, so the
    # flag can't race the way a shared FeedCacheStats counter delta does.
    runtime.feed_cache_hit = not computed
    return _render_feed(query, cached, when=when)


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
    # feed_cache_ttl_s == 0 disables the cache entirely (None → plan() is a
    # byte-identical no-op vs. before Epic 039 S2) — the operator kill switch.
    feed_cache = (
        default_feed_cache(settings.feed_cache_ttl_s, settings.feed_cache_max_entries)
        if settings.feed_cache_ttl_s > 0
        else None
    )
    # The region-level conditions probe (frame-conditions-wave §5, epic-054 S2/S3):
    # resolved directly from the same NWS credential `NwsAdapter` uses, NOT through
    # `probes_for` (a region-level fact has no per-candidate `ConditionKind` fan-out
    # to join — see `NwsRegionAdapter`). Absent credential → None (source-or-silence).
    region_probe = NwsRegionAdapter.from_config(settings)
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
        feed_cache=feed_cache,
        # The phase-1 holding pen exists only while the two-phase flow is enabled;
        # ADVENTURE_TWO_PHASE_ENABLED=0 leaves it None and `/plan` with
        # phase:"cards" serves the full single-pass response instead (Epic 040 D6).
        phase1_pending=default_pending_store() if settings.two_phase_enabled else None,
        region_probe=region_probe,
    )
