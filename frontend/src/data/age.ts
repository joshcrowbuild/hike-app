/**
 * Relative-age humaniser (§7.2): the surface shows a fact's age as a relative
 * string ("2h ago"), never a raw datetime. Honesty over precision: an
 * unparseable timestamp degrades to a disclosed "time unknown", never a blank
 * or a fabricated age.
 */

/**
 * The disclosed token for an unparseable timestamp. A caller that RENDERS a
 * stamp (rather than logging/inspecting the raw fact) must never show this
 * literal text (Epic 046 S4 AC-4.2 / D6): it's treated as "no stamp at all"
 * at the call site (mapped to `undefined`) instead, so an unparseable time
 * degrades to honest silence, not a visible "time unknown" — and can never
 * enter a shared block-stamp agreement (e.g. `feedConditions.ts::sharedAmong`)
 * as if two independent failures were one real agreement.
 */
export const TIME_UNKNOWN = 'time unknown'

export function relativeAge(iso: string, nowMs: number = Date.now()): string {
  const then = Date.parse(iso)
  if (Number.isNaN(then)) return TIME_UNKNOWN
  const deltaMs = nowMs - then
  if (deltaMs < 60_000) return 'just now'
  const minutes = Math.floor(deltaMs / 60_000)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}
