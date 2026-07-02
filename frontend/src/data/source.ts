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
import type { CardVM, EpisodeVM, FeedVM, OutcomeVM } from './vm'
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
   * A single card by id, for when the caller (`useCard`) can't resolve it from
   * the feed already in memory — a true deep-link, or an id outside the current
   * result set. Returns null when the id is unknown. `tuning` is the CURRENT
   * frame (never a rebuilt default) so the refetch reflects what the viewer
   * actually has dialed in; when omitted (cold deep-link / anonymous) the card
   * degrades to a distance-only default frame (R7).
   */
  getCard(id: string, scope: ScopeContext, tuning?: TuningState): Promise<CardVM | null>

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
