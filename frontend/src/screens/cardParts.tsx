/** Small presentational pieces shared by the card and the detail screen. Each
 *  is typed against the view-model, not the legacy Trail. */
import { Signal, Staleness } from '../components'
import { metersToFeet } from '../data/geo'
import type { TrailGeo, WarningVM } from '../data/vm'

/**
 * Verified hazard warnings, worn prominently on both the feed card and Detail
 * (decision of 2026-07-01): a trail under a live alert SHOWS with its warning —
 * it is never hidden, on either surface. Each warning routes through <Signal>
 * (the accent caution primitive) and wears its source + relative age via
 * <Staleness>, mirroring how condition lines carry source/confidence — a hazard
 * claim is a fact and dresses like one (R1).
 */
export function WarningBlock({ warnings, label = 'Warning' }: { warnings: WarningVM[]; label?: string }) {
  if (warnings.length === 0) return null
  return (
    <div className="card-warnings">
      {warnings.map((w, i) => (
        <Signal key={i} label={label} className="card-warning">
          {w.text}
          <span className="card-warning-meta">
            {' — '}
            {w.source} · <Staleness>{w.observedAgo}</Staleness>
          </span>
        </Signal>
      ))}
    </div>
  )
}

/**
 * The card's whole-tap-target accessible name (report #4/#7): an `aria-label`
 * on the button SWALLOWS its descendant content for assistive tech, so a plain
 * "Open {name}" silently erases the warnings a sighted user sees rendered
 * right there. Folding the warning text into the name keeps it short (no
 * source/age chatter — that's still one tap away on Detail) but complete: a
 * screen-reader user hears the same hazard a sighted user sees before opening.
 */
export function cardAccessibleName(name: string, warnings: WarningVM[]): string {
  if (warnings.length === 0) return `Open ${name}`
  return `Open ${name} — warning: ${warnings.map((w) => w.text).join('; ')}`
}

/**
 * Ascent in feet derived from the live elevation profile, when the API
 * supplies one. The fallback for the (common, today) case where a card has no
 * mock `enrichment.ascentFeet` — without it, a live card with a real profile
 * still showed no ascent figure anywhere (report #2). `undefined` when no
 * profile exists, so callers degrade to hiding the figure, never a fake one.
 */
export function geoAscentFeet(geo: TrailGeo | undefined): number | undefined {
  const gain = geo?.elevationProfile?.totalGainMeters
  return gain != null ? Math.round(metersToFeet(gain)) : undefined
}

export function DecisionItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="decision-item">
      <span className="decision-label">{label}</span>
      <span className="decision-value">{value}</span>
    </div>
  )
}

export const formatDrive = (minutes: number): string => `${minutes} min`
export const formatTrail = (miles: number, ascentFeet: number): string =>
  `${miles.toFixed(1)} mi · ${ascentFeet.toLocaleString()} ft`
