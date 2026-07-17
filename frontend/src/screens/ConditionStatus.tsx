import type { ConditionStatusVM } from '../data/vm'
import type { ConditionTier, ConditionTierMapper } from '../design/contracts'

/**
 * The single source of the coverage→tier decision (design-system-v0.2.md II.B):
 * a pure function mapping the six coverage states to the 4-tier signal system.
 * `ConditionStates` (Detail's coverage list) and the conditions strip both read
 * it, so the tier/colour judgment can never drift between surfaces.
 *
 *   no-hazard                                     -> clear    (silent)
 *   present (closure/permit hard-stop)            -> blocked
 *   present (heat/flow/advisory)                  -> headsUp
 *   no-data | unavailable | not-fetched |
 *     stale-degraded                              -> unknown  (gray, never red)
 */
export const toTier: ConditionTierMapper = (status: ConditionStatusVM): ConditionTier => {
  if (status.state === 'no-hazard') return 'clear'
  if (status.state === 'present') {
    // Actionability split (Law 7): a hard stop is blocked; everything else that
    // is present-and-actionable is a heads-up. Severity comes from the engine,
    // not colour — the strip renders the tier the backend graded (Q7).
    if (status.kind === 'closures' || status.kind === 'permits') return 'blocked'
    return 'headsUp'
  }
  return 'unknown'
}
