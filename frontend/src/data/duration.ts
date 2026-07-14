/**
 * Naismith's-rule duration humaniser (Rule #1/#7): the backend's minutes
 * figure is an inference, never a stated fact, so it must always carry an
 * explicit `est.` disclosure somewhere on the surface — never a bare number
 * that could be mistaken for a verified duration.
 *
 * The disclosure used to be baked inline (`"~1 hr 10 min · est."`), which made
 * the string the widest of the four decision facts — on a long duration
 * ("~5 hr 5 min · est.") it was wider than the card's own fact column and
 * clipped at the right edge on every viewport (ux-review 2026-07 Finding 1).
 * This now returns the bare humanised core; callers render the `est.` tag as
 * its own small badge (mirroring `DifficultyBadge`'s `.difficulty-est`
 * treatment) via `DecisionItem`'s `badge` prop, so the disclosure never grows
 * the fact's own nowrap value string.
 */
export function formatEstimatedDuration(minutes: number): string {
  const rounded = Math.max(5, Math.round(minutes / 5) * 5)
  const hours = Math.floor(rounded / 60)
  const mins = rounded % 60
  const core = hours > 0 ? (mins > 0 ? `${hours} hr ${mins} min` : `${hours} hr`) : `${mins} min`
  return `~${core}`
}
