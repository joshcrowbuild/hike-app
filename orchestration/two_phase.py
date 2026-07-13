"""Two-phase render (Epic 040): cards first, conditions verified behind.

Phase 1 (`plan_cards`) returns taste-ranked, corpus-backed cards with ZERO live
probes — every point kind honestly `not_fetched` (D2: nothing has been fetched, so
"not probed (yet)" is true silence, never a placeholder trick). Phase 2
(`plan_conditions`) runs the live-probe fan-out for exactly the cards phase 1
returned and hands back the verified overlay: per-card six-state `conditions`,
condition lines, warnings, unavailable disclosures — plus the disclosed removal
list for hard-guardrail blocks (D5: phase 2 may REMOVE, never reorder).

Cache discipline (D7, honored exactly):
  * a WARM anonymous key short-circuits phase 1 into today's full response
    (withholding already-paid-for facts would be manufactured latency);
  * a phase-1 plan is NEVER written to the feed cache — it parks in the separate
    short-TTL holding pen (`feed_cache.default_pending_store`) instead;
  * the conditions call's COMPOSED result is what warms the feed cache for the
    key, single-flighted through the cache's own gate.

The composition is what the eval-replay gate's `two_phase_composition` criterion
defends: phase 1 + the patch, composed by `verify_planned`, must equal today's
single-pass output over the same recorded world (two phases are a presentation
split, never a second truth — D3).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from graph import queries
from orchestration.adapters.base import ConditionKind, LiveAdapter, Point
from orchestration.adapters.registry import TTLCache
from orchestration.confidence import for_fact
from orchestration.curator import evaluate_guardrails
from orchestration.engine import (
    Feed,
    FeedCard,
    PlannedTrail,
    Runtime,
    SetAsideTrail,
    _anon_key,
    _compute_plan,
    _latlon,
    _render_feed,
    _set_aside,
    feed_card,
)
from orchestration.feed_cache import CachedPlan, FeedCache, FeedCacheKey
from orchestration.scout import Candidate
from orchestration.verifier import DEFAULT_MAX_WORKERS, verify_batch

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConditionsPatch:
    """The `/plan/conditions` result: the verified overlay for the requested ids.

    `cards` re-renders each surviving requested trail through the SAME `feed_card`
    path production serves (AC-2.1 — no second presentation truth); `set_aside`
    holds the requested ids a hard live guardrail removed, cause + source (D5);
    `unknown` names requested ids this call could not resolve at all (not in the
    plan, not in the graph) — omitted with disclosure, never fabricated (AC-2.2).
    `from_cache` is the metrics-honesty flag: True when THIS call spent no probes
    (served from an already-composed cached plan)."""

    cards: list[FeedCard]
    set_aside: tuple[SetAsideTrail, ...]
    unknown: tuple[str, ...]
    from_cache: bool


def plan_cards(
    query: str,
    origin: tuple[float, float],
    runtime: Runtime,
    *,
    k: int = 10,
    viewer_id: str = "anonymous",
) -> tuple[Feed, bool]:
    """Phase 1: the graph-only ranked plan (Epic 040 S1). Returns `(feed, complete)`.

    `complete=True` means the feed already carries verified conditions and the
    client must skip the conditions call (the warm-key case, D7 — facts already
    paid for are never withheld to honor a phase). `complete=False` means every
    point kind is `not_fetched` and a `/plan/conditions` follow-up is expected.

    The phase-1 plan is parked in the holding pen (anonymous only) and is NEVER
    written to the feed cache (AC-1.4): a later full `/plan` on the same key must
    miss and compute rather than silently serve an unverified plan.
    """
    fc = runtime.feed_cache
    # The anonymous key exists independently of the feed cache: the holding pen
    # must keep working when the cache is TTL-0-disabled (its kill switch must
    # not silently degrade the two-phase composition to the graph fallback).
    # None for any non-anonymous viewer — a personalized plan never enters
    # either shared store (Rule #5).
    key = _anon_key(query, origin, k) if viewer_id == "anonymous" else None
    runtime.feed_cache_hit = False
    if fc is not None and key is not None:
        cached = fc.get(key)
        if cached is not None:
            # Warm key: the full verified plan is already paid for — serve it
            # complete (re-rendered against serve-time freshness) instead of
            # recomputing a phase-1 (D7).
            runtime.feed_cache_hit = True
            return _render_feed(query, cached), True
    pending_store = runtime.phase1_pending
    if key is not None and pending_store is not None:
        # Park-or-reuse through the pen's own single-flight gate: two identical
        # phase-1 misses landing together rank once, not twice (same discipline
        # as the full path's FeedCache.get_or_compute), and a re-tap within the
        # pen's short TTL reuses the parked plan — its conditions are fetched
        # fresh by the follow-up call either way.
        phase1 = pending_store.get_or_compute(
            key,
            lambda: _compute_plan(query, origin, runtime, k=k, viewer_id=viewer_id, verify=False),
        )
    else:
        phase1 = _compute_plan(query, origin, runtime, k=k, viewer_id=viewer_id, verify=False)
    return _render_feed(query, phase1), False


def verify_planned(
    planned: tuple[PlannedTrail, ...] | list[PlannedTrail],
    origin: tuple[float, float],
    probes: dict[ConditionKind, list[LiveAdapter]],
    *,
    cache: TTLCache | None = None,
    probe_max_workers: int = DEFAULT_MAX_WORKERS,
) -> tuple[list[PlannedTrail], list[SetAsideTrail]]:
    """The phase-2 fold: run the live-probe fan-out over an already-ranked plan and
    fold the verified facts in — the SAME `verify_batch` → `evaluate_guardrails` →
    fold-drive-after-guardrail sequence `plan_from_origin` runs single-pass, applied
    to `PlannedTrail`s instead of raw candidates, so the two paths cannot drift in
    semantics (the eval gate's `two_phase_composition` criterion holds them equal).

    Order is preserved exactly; a hard-guardrail block is REMOVED into the returned
    set-aside list (D5: remove, never reorder). Drive-time facts from phase 1 are
    folded back in AFTER the guardrail check (they never reach
    `evaluate_guardrails` — Epic 005 AC-5.3, unchanged)."""
    probed_kinds = frozenset(
        kind
        for kind, adapters in probes.items()
        if adapters and kind is not ConditionKind.drive_time
    )
    points = [Point(*(_latlon(p.candidate.point) or origin)) for p in planned]
    facts_by_trail = verify_batch(points, probes, cache=cache, max_workers=probe_max_workers)
    composed: list[PlannedTrail] = []
    set_aside: list[SetAsideTrail] = []
    for trail, facts in zip(planned, facts_by_trail, strict=True):
        verdict = evaluate_guardrails(facts, probed_kinds=probed_kinds)
        if verdict.blocked:
            set_aside.append(_set_aside(trail.candidate, verdict))
            continue
        drive_fact = trail.facts.get(ConditionKind.drive_time)
        if drive_fact is not None:
            facts[ConditionKind.drive_time] = drive_fact
        # Live facts stay an honest single source (CDP-01) — same construction as
        # `plan_from_origin`; the corpus-level corroboration fields ride through
        # unchanged from phase 1 on the replace() below.
        confidences = {kind: for_fact(fact, corroboration=1) for kind, fact in facts.items()}
        composed.append(
            replace(
                trail,
                facts=facts,
                confidences=confidences,
                verdict=verdict,
                probed_kinds=probed_kinds,
            )
        )
    return composed, set_aside


def plan_conditions(
    query: str,
    origin: tuple[float, float],
    runtime: Runtime,
    canonical_ids: list[str],
    *,
    k: int = 10,
    viewer_id: str = "anonymous",
) -> ConditionsPatch:
    """Phase 2: the verified overlay for `canonical_ids` (Epic 040 S2).

    Resolution ladder:
      1. a FRESH feed-cache entry for the key serves the patch without re-probing
         (AC-2.5's second half — the facts are already paid for);
      2. the phase-1 holding pen: compose via `verify_planned` and warm the feed
         cache with the composed plan, single-flighted through the cache's own
         gate (AC-2.5's first half);
      3. graph lookup by id (holding pen expired / another instance / a
         non-anonymous viewer): probe the trails' own points and return the
         overlay without warming the cache (a faithful composition needs the
         phase-1 plan; a partial one must never pose as it).

    This call never ranks — zero LLM spend by construction (AC-2.3)."""
    requested = list(dict.fromkeys(canonical_ids))  # de-dupe, order preserved
    fc = runtime.feed_cache
    # Same key derivation as `plan_cards` (decoupled from the feed cache's
    # presence, None for non-anonymous viewers — Rule #5).
    key = _anon_key(query, origin, k) if viewer_id == "anonymous" else None

    if fc is not None and key is not None:
        cached = fc.get(key)
        if cached is not None:
            return _patch_from_plan(cached, requested, from_cache=True)

    pending = (
        runtime.phase1_pending.get(key)
        if (key is not None and runtime.phase1_pending is not None)
        else None
    )
    if pending is not None:
        composed_plan, computed = _compose_and_warm(pending, origin, runtime, fc, key)
        return _patch_from_plan(composed_plan, requested, from_cache=not computed)

    return _patch_from_graph(requested, origin, runtime)


def _compose_and_warm(
    pending: CachedPlan,
    origin: tuple[float, float],
    runtime: Runtime,
    fc: "FeedCache | None",
    key: FeedCacheKey | None,
) -> tuple[CachedPlan, bool]:
    """Compose the full plan from the parked phase-1 plan and warm the feed cache
    with it (single-flighted). Returns `(plan, computed)` — `computed` is False on
    a hit-after-wait (another request's compose filled the key first), so metrics
    stay honest about which request actually spent probes."""
    computed = False

    def _compose() -> CachedPlan:
        nonlocal computed
        computed = True
        composed, aside = verify_planned(
            pending.planned,
            origin,
            runtime.probes,
            cache=runtime.cache,
            probe_max_workers=runtime.probe_max_workers,
        )
        return CachedPlan(
            planned=tuple(composed),
            notices=pending.notices,
            set_aside=pending.set_aside + tuple(aside),
        )

    if fc is not None and key is not None:
        return fc.get_or_compute(key, _compose), computed
    return _compose(), computed


def _patch_from_plan(
    plan: CachedPlan, requested: list[str], *, from_cache: bool
) -> ConditionsPatch:
    """Render the patch for `requested` out of a fully-composed plan — through
    `feed_card`, the same rendering path `/plan` serves (AC-2.1)."""
    by_id = {p.candidate.canonical_id: p for p in plan.planned}
    aside_by_id = {t.canonical_id: t for t in plan.set_aside}
    cards: list[FeedCard] = []
    set_aside: list[SetAsideTrail] = []
    unknown: list[str] = []
    for cid in requested:
        trail = by_id.get(cid)
        if trail is not None:
            cards.append(feed_card(trail))
        elif cid in aside_by_id:
            set_aside.append(aside_by_id[cid])
        else:
            unknown.append(cid)
    return ConditionsPatch(
        cards=cards, set_aside=tuple(set_aside), unknown=tuple(unknown), from_cache=from_cache
    )


def _patch_from_graph(
    requested: list[str], origin: tuple[float, float], runtime: Runtime
) -> ConditionsPatch:
    """The no-holding-pen fallback: resolve the requested ids straight from the
    graph (world read through the scoped session, rule #4), probe their points,
    and return the overlay. Ids the graph doesn't know land in `unknown` —
    disclosed, never fabricated (AC-2.2). The feed cache is NOT warmed here: this
    path has no phase-1 plan (no rank, no drive facts, no corroboration read), so
    what it composes is a faithful per-card overlay but not a faithful full plan.

    A graph read failure raises — the API layer maps it to its standard 500 and
    the client's patch-failure surface keeps the cards usable (fail loudly at the
    boundary, degrade gracefully at the surface)."""
    rows = runtime.session.run(queries.trails_detail(requested))
    by_id = {r["canonical_id"]: r for r in rows if r.get("canonical_id")}
    empty_verdict = evaluate_guardrails({}, probed_kinds=())
    planned: list[PlannedTrail] = []
    unknown: list[str] = []
    for cid in requested:
        row = by_id.get(cid)
        if row is None:
            unknown.append(cid)
            continue
        candidate = Candidate(
            canonical_id=cid,
            name=row.get("name") or cid,
            trailhead_id="",
            distance_m=0.0,  # unused: the patch payload carries no distance field
            point=row.get("trail_point"),
            trailhead_point=row.get("trailhead_point"),
        )
        planned.append(
            PlannedTrail(candidate=candidate, facts={}, confidences={}, verdict=empty_verdict)
        )
    composed, set_aside = verify_planned(
        planned,
        origin,
        runtime.probes,
        cache=runtime.cache,
        probe_max_workers=runtime.probe_max_workers,
    )
    return ConditionsPatch(
        cards=[feed_card(p) for p in composed],
        set_aside=tuple(set_aside),
        unknown=tuple(unknown),
        from_cache=False,
    )
