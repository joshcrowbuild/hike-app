/**
 * Naismith's-rule duration humaniser (Rule #1/#7): the backend's minutes
 * figure is an inference, never a stated fact, so every rendered value
 * carries an explicit `est.` disclosure — never a bare number that could be
 * mistaken for a verified duration.
 */
export function formatEstimatedDuration(minutes: number): string {
  const rounded = Math.max(5, Math.round(minutes / 5) * 5)
  const hours = Math.floor(rounded / 60)
  const mins = rounded % 60
  const core = hours > 0 ? (mins > 0 ? `${hours} hr ${mins} min` : `${hours} hr`) : `${mins} min`
  return `~${core} · est.`
}
