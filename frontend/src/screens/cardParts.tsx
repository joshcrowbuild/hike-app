/** Small presentational pieces shared by the card and the detail screen. Each
 *  is typed against the view-model, not the legacy Trail. */
import { Signal, Staleness } from '../components'
import type { WarningVM } from '../data/vm'

/**
 * Verified hazard warnings, worn prominently on both the feed card and Detail
 * (decision of 2026-07-01): a trail under a live alert SHOWS with its warning —
 * it is never hidden, on either surface. Each warning routes through <Signal>
 * (the accent caution primitive) and wears its source + relative age via
 * <Staleness>, mirroring how condition lines carry source/confidence — a hazard
 * claim is a fact and dresses like one (R1).
 */
export function WarningBlock({ warnings }: { warnings: WarningVM[] }) {
  if (warnings.length === 0) return null
  return (
    <div className="card-warnings">
      {warnings.map((w, i) => (
        <Signal key={i} label="Warning" className="card-warning">
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
