/**
 * The data-source port. Screens depend on this interface, never on a concrete
 * adapter — so swapping mock ⇄ live is a one-line provider change and tests
 * inject a fake. Method signatures mirror the real API plus an explicit
 * `ScopeContext` (R5), so the Phase-2 grant dimension never becomes a signature
 * break.
 *
 * Extended per feature: `plan`/`getCard` ship with the spine; outcome/belief
 * methods are added by their own epics so each stays one logical change.
 */
import type { OutcomeBody, ScopeContext } from './api'
import type { CardVM, ConditionsPatchVM, EpisodeVM, FeedVM, OutcomeVM, TrailWaterVM } from './vm'
import type { TuningState } from '../types'

export interface PlanInput {
  tuning: TuningState
  /** Max results (the API's `k`). */
  k?: number
}

export interface PlannerClient {
  /** The curated feed for a tuning frame and viewer scope. */
  plan(input: PlanInput, scope: ScopeContext): Promise<FeedVM>
  /**
   * Trail-name search (Epic 038/B001 build lane, frontend half): a finite
   * lookup through the engine, returning the SAME `FeedVM` shape `plan` does
   * (same cards, same mapping — never a second presentation truth). Optional
   * so a fixture client predating search still satisfies the interface;
   * `useSearch` calls it only when present and degrades to a calm "search
   * unavailable" disclosure otherwise (Rule #6 posture).
   */
  search?(query: string, scope: ScopeContext, k?: number): Promise<FeedVM>
  /**
   * The phase-2 verified overlay for a phase-1 feed's card ids (Epic 040 S2).
   * Optional: only the HTTP adapter implements it — the mock always returns
   * complete feeds, so `useFeed` runs phase 2 only when the resolved feed says
   * `conditionsPending` AND the client can. Rejects on failure — the caller
   * owns the calm retry surface, never a fake-clear.
   */
  planConditions?(
    input: PlanInput,
    scope: ScopeContext,
    canonicalIds: string[],
  ): Promise<ConditionsPatchVM>
  /**
   * A single card by id, for when the caller (`useCard`) can't resolve it from
   * the feed already in memory — a true deep-link, or an id outside the current
   * result set. Returns null when the id is unknown. `tuning` is the CURRENT
   * frame (never a rebuilt default) so the refetch reflects what the viewer
   * actually has dialed in; when omitted (cold deep-link / anonymous) the card
   * degrades to a distance-only default frame (R7).
   */
  getCard(id: string, scope: ScopeContext, tuning?: TuningState): Promise<CardVM | null>

  /**
   * The water answer for one trail (Epic 041, Detail-only) — `GET /trail/{id}`'s
   * `water_sources` slice. Null = honest silence (region never water-ingested,
   * OR the read failed): Detail renders no water row at all. Never throws —
   * water is enrichment on the commitment view, not a dependency (Rule #6
   * posture): a fetch failure degrades to silence, not an error surface.
   */
  trailWater(id: string, scope: ScopeContext): Promise<TrailWaterVM | null>

  // ---- Post-hike loop ----
  /** Recent hikes for this viewer (the source of the pending outcome nod). */
  recentEpisodes(scope: ScopeContext): Promise<EpisodeVM[]>
  /** One episode by id (deep-link to the outcome card). */
  getEpisode(id: string, scope: ScopeContext): Promise<EpisodeVM | null>
  /** Record (or idempotently update) a post-hike outcome. */
  recordOutcome(
    episodeId: string,
    body: OutcomeBody,
    companions: EpisodeVM['companions'],
    scope: ScopeContext,
  ): Promise<OutcomeVM>
}
