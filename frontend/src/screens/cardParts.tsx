/** Small presentational pieces shared by the card and the detail screen. Each
 *  is typed against the view-model, not the legacy Trail. */
import type { LucideIcon } from 'lucide-react'
import { ToggleButton } from 'react-aria-components'

import { Icon, Signal, Staleness } from '../components'
import { glyphs } from './glyphs'
import { metersToFeet, trailheadDirectionsUrl } from '../data/geo'
import { toggleTrailSaved, useIsTrailSaved } from '../data/savedTrails'
import { deriveDifficulty, deriveSummary } from '../data/summary'
import type {
  CardVM,
  ConditionSilence as ConditionSilenceVM,
  GeoPosition,
  SilenceState,
  TrailGeo,
  WarningVM,
} from '../data/vm'
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
 * The one-line trail character (product voice, 2026-07-03), rendered on both the
 * card and Detail. It is `deriveSummary`'s output — a *summary of the card's own
 * verified figures* (mapped length, profile climb, geometry-read shape, summit),
 * never invented texture (source-or-silence, R1). `null` when there isn't enough
 * verified data to say anything, so the caller renders nothing rather than pad.
 */
export function TrailSummary({ card, className }: { card: CardVM; className?: string }) {
  const summary = deriveSummary(card)
  if (!summary) return null
  return <p className={className ? `trail-summary ${className}` : 'trail-summary'}>{summary}</p>
}

/**
 * The derived difficulty estimate (√(2·climb·miles), banded easy →
 * very-strenuous). Labeled "est." on its face and given an inspectable
 * description of the exact formula + score, so it never poses as an authoritative
 * rating — it is a transparent derivation from the two figures the card already
 * shows. Presentation only: it is NEVER a ranking signal (Rule #2). A non-live
 * estimate wears a "sample" tag, mirroring <Confidence>. `null` (renders nothing)
 * when climb or length is unknown, so we never guess a rating.
 */
export function DifficultyBadge({ card }: { card: CardVM }) {
  const d = deriveDifficulty(card)
  if (!d) return null
  const live = d.provenance === 'live'
  const desc = `Estimated from distance and climb (rating ${d.score}); an estimate, not a rank.`
  return (
    <span className={`difficulty difficulty--${d.band}${live ? '' : ' difficulty--sample'}`} title={desc}>
      <span className="sr-only">Difficulty estimate: </span>
      <span className="difficulty-label">{d.label}</span>
      <span className="difficulty-est" aria-label="derived estimate">
        {' '}
        est.
      </span>
      {live ? null : (
        <span className="difficulty-sample" aria-hidden="true">
          {' '}
          sample
        </span>
      )}
    </span>
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

/**
 * One decision fact — icon + LABEL WORD + value (Epic 021 · AC-21.2.1). The
 * glyph is a small LEADING ACCENT beside the word, never a replacement: the word
 * always stays, so a fact is never label-less. `glyph` is optional so a caller
 * that has no assigned DD2 glyph degrades to the word alone rather than reaching
 * for a stand-in. The icon's sr-only label carries the word to assistive tech;
 * the visible word is a sighted-only echo of it (`aria-hidden`), so the fact
 * reads once, not twice.
 */
export function DecisionItem({ label, value, glyph }: { label: string; value: string; glyph?: LucideIcon }) {
  return (
    <div className="decision-item">
      <span className="decision-label">
        {glyph ? <Icon glyph={glyph} label={label} className="decision-icon" /> : null}
        <span aria-hidden={glyph ? 'true' : undefined}>{label}</span>
      </span>
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
      <Icon glyph={glyphs.directions} label="Directions" className="action-chip-icon" />
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
      <Icon glyph={saved ? glyphs.saved : glyphs.save} label={saved ? 'Saved' : 'Save'} className="action-chip-icon" />
      {saved ? 'Saved' : 'Save'}
    </ToggleButton>
  )
}

/**
 * The four silence states (CDP-02), shared by the card's single condition slot
 * and Detail's condition block. Each carries its own copy, a leading glyph, and
 * its own treatment — meaning is never colour-only (glyph + copy differ per
 * state, §4.3 colour-blind safe), and no two look like the same gray (AC-4.2).
 * `stale-degraded` routes its age through the <Staleness> primitive so a
 * last-known value wears its age honestly (§7.2).
 */
const SILENCE_COPY: Record<SilenceState, { glyph: string; announce: string; label: string }> = {
  'not-fetched': { glyph: '○', announce: 'Not checked yet', label: 'Conditions not checked — open to verify' },
  'checked-clear': { glyph: '✓', announce: 'Checked, clear', label: 'Checked — nothing to flag' },
  'no-data': { glyph: '–', announce: 'No source', label: 'No live source covers this spot' },
  'stale-degraded': { glyph: '!', announce: 'Stale, may have changed', label: 'Last known conditions' },
}

export function ConditionSilence({ silence, partial }: { silence: ConditionSilenceVM; partial?: boolean }) {
  const { state, detail } = silence
  const copy = SILENCE_COPY[state]
  return (
    <p className={`condition-silence condition-silence--${state}${partial ? ' condition-silence--partial' : ''}`}>
      <span className="sr-only">{copy.announce}: </span>
      <span className="condition-silence-glyph" aria-hidden="true">
        {copy.glyph}
      </span>
      <span className="condition-silence-text">
        {partial ? 'Other conditions: ' : ''}
        {copy.label}
        {detail ? (
          state === 'stale-degraded' ? (
            <>
              {' — '}
              <Staleness stale>{detail}</Staleness>
            </>
          ) : (
            ` — ${detail}`
          )
        ) : null}
      </span>
    </p>
  )
}

