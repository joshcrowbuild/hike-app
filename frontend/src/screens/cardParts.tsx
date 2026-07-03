/** Small presentational pieces shared by the card and the detail screen. Each
 *  is typed against the view-model, not the legacy Trail. */
import { ToggleButton } from 'react-aria-components'

import { Signal, Staleness } from '../components'
import { metersToFeet, trailheadDirectionsUrl } from '../data/geo'
import { toggleTrailSaved, useIsTrailSaved } from '../data/savedTrails'
import type { CardVM, GeoPosition, TrailGeo, WarningVM } from '../data/vm'
import { deriveVerdict } from '../data/verdict'

/**
 * The go/no-go headline worn at the top of a card and Detail (product voice,
 * 2026-07-03). It reads the card's own verified signals and renders a hedged
 * verdict — a *summary* of the warnings + conditions shown below, never a new
 * fact and never a guarantee (source-or-silence, R1). Presentation only: it
 * touches nothing about ranking (Rule #2).
 *
 * Caution routes through the owned <Signal> primitive — the sole carrier of the
 * accent hue — so a live hazard reads as caution in colour AND copy. "Good to go"
 * and "Heads up" are plain ink, told apart by their words and treatment, never by
 * colour alone (§4.3). A non-live verdict carries a visible "sample" tag and a
 * demoted treatment, mirroring <Confidence> — a sampled verdict never poses as a
 * verified one.
 */
export function Verdict({ card, className }: { card: CardVM; className?: string }) {
  const v = deriveVerdict(card)
  const live = v.provenance === 'live'
  const body = (
    <>
      <span className="verdict-lead">{v.lead}</span>
      {v.detail ? <span className="verdict-detail"> — {v.detail}</span> : null}
      {live ? null : (
        <span className="verdict-sample" aria-hidden="true">
          {' '}
          sample
        </span>
      )}
    </>
  )
  const place = className ? ` ${className}` : ''
  if (v.tone === 'caution') {
    // A hazard keeps its accent even when sampled (mirrors <Confidence>).
    return (
      <Signal className={`verdict verdict--caution${place}`} label="Should you go? Caution">
        {body}
      </Signal>
    )
  }
  const announce = v.tone === 'go' ? 'Should you go? Looks good to go' : 'Should you go? Heads up, not verified'
  return (
    <p className={`verdict verdict--${v.tone}${live ? '' : ' verdict--sample'}${place}`}>
      <span className="sr-only">{announce}: </span>
      {body}
    </p>
  )
}

/**
 * Verified hazard warnings, worn prominently on both the feed card and Detail
 * (decision of 2026-07-01): a trail under a live alert SHOWS with its warning —
 * it is never hidden, on either surface. Each warning routes through <Signal>
 * (the accent caution primitive) and wears its source + relative age via
 * <Staleness>, mirroring how condition lines carry source/confidence — a hazard
 * claim is a fact and dresses like one (R1).
 *
 * `collapsed` drops the repeated hazard sentence when a <Verdict> headline
 * directly above has already spoken it (a caution verdict is always derived
 * from these same warnings) — source + age still show, so source-or-silence
 * holds, but the sentence itself is never said twice on one card.
 */
export function WarningBlock({
  warnings,
  label = 'Warning',
  collapsed = false,
}: {
  warnings: WarningVM[]
  label?: string
  collapsed?: boolean
}) {
  if (warnings.length === 0) return null
  return (
    <div className="card-warnings">
      {warnings.map((w, i) => (
        <Signal key={i} label={label} className="card-warning">
          {collapsed ? null : w.text}
          <span className="card-warning-meta">
            {collapsed ? null : ' — '}
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

/**
 * A driving-directions deep link to the trailhead — the same
 * `trailheadDirectionsUrl` (S6 AC-6.4) that already powered Detail's map
 * controls, now surfaced as a first-class action on both the feed card and
 * Detail instead of being reachable only after opening the map block. Rendered
 * only by callers that hold a `TrailGeo` (Rule #1 — never a dead link to a
 * point we don't have).
 */
export function DirectionsLink({ trailhead, name, className }: { trailhead: GeoPosition; name: string; className?: string }) {
  return (
    <a
      className={className ? `action-chip ${className}` : 'action-chip'}
      href={trailheadDirectionsUrl(trailhead)}
      target="_blank"
      rel="noreferrer"
      aria-label={`Directions to the ${name} trailhead (opens Google Maps in a new tab)`}
    >
      <DirectionsIcon />
      Directions
    </a>
  )
}

/**
 * A client-side bookmark toggle — `localStorage` only, no backend or auth, so
 * it works the same for the anonymous world-browse posture as for a signed-in
 * viewer. The on/off state reaches assistive tech through React Aria's
 * `aria-pressed` on `ToggleButton`; the visible label and the glyph's fill
 * both flip too, so "saved" is never colour-only (§4.3).
 */
export function SaveButton({ id, name, className }: { id: string; name: string; className?: string }) {
  const saved = useIsTrailSaved(id)
  return (
    <ToggleButton
      className={className ? `action-chip ${className}` : 'action-chip'}
      isSelected={saved}
      onChange={() => toggleTrailSaved(id)}
      aria-label={saved ? `Remove ${name} from saved trails` : `Save ${name}`}
    >
      <BookmarkIcon filled={saved} />
      {saved ? 'Saved' : 'Save'}
    </ToggleButton>
  )
}

function DirectionsIcon() {
  return (
    <svg
      className="action-chip-icon"
      viewBox="0 0 16 16"
      aria-hidden="true"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.3"
      strokeLinejoin="round"
      strokeLinecap="round"
    >
      <path d="M8 1.5 13.5 14 8 11 2.5 14 8 1.5Z" />
    </svg>
  )
}

function BookmarkIcon({ filled }: { filled: boolean }) {
  return (
    <svg
      className="action-chip-icon"
      viewBox="0 0 16 16"
      aria-hidden="true"
      fill={filled ? 'currentColor' : 'none'}
      stroke="currentColor"
      strokeWidth="1.3"
      strokeLinejoin="round"
    >
      <path d="M4 2.75a.75.75 0 0 1 .75-.75h6.5a.75.75 0 0 1 .75.75v10.6l-4-2.35-4 2.35V2.75Z" />
    </svg>
  )
}
