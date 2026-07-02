/**
 * Relative-age humaniser (§7.2): the surface shows a fact's age as a relative
 * string ("2h ago"), never a raw datetime. Honesty over precision: an
 * unparseable timestamp degrades to a disclosed "time unknown", never a blank
 * or a fabricated age.
 */
export function relativeAge(iso: string, nowMs: number = Date.now()): string {
  const then = Date.parse(iso)
  if (Number.isNaN(then)) return 'time unknown'
  const deltaMs = nowMs - then
  if (deltaMs < 60_000) return 'just now'
  const minutes = Math.floor(deltaMs / 60_000)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}
