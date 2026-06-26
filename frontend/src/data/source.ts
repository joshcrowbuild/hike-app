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
import type { ScopeContext } from './api'
import type { CardVM, FeedVM } from './vm'
import type { OriginKey, TuningState } from '../types'

export interface PlanInput {
  tuning: TuningState
  /** Max results (the API's `k`). */
  k?: number
}

export interface PlannerClient {
  /** The curated feed for a tuning frame and viewer scope. */
  plan(input: PlanInput, scope: ScopeContext): Promise<FeedVM>
  /**
   * A single card by id, resolvable independent of the current feed so a
   * deep-link / reload survives (fixes the in-memory-lookup orphan). Returns
   * null when the id is unknown. `origin` is the current frame's start, used
   * to compute drive time; when omitted (cold deep-link / anonymous) the card
   * degrades to distance-only (R7).
   */
  getCard(id: string, scope: ScopeContext, origin?: OriginKey): Promise<CardVM | null>
}
