import { Staleness, Text, Button, MetricRow } from '../components'
import { conditionStateKey, lineKey } from '../data/feedConditions'
import type { CardVM, LineVM } from '../data/vm'
import type { MetricItem } from '../components/MetricRow/MetricRow'
import {
  cardAccessibleName,
  ConditionSilence,
  DirectionsLink,
  SaveButton,
  Verdict,
  verdictSpokenWarningText,
  WarningBlock,
} from './cardParts'
import { summarizeConditions, ConditionStatusLine } from './ConditionStatus'
import { ElevationGlyph } from './map/ElevationGlyph'
import { glyphs } from './glyphs'
import { resolveMiles, resolveDurationMinutes } from '../data/summary'
import { formatEstimatedDuration } from '../data/duration'
import { geoAscentFeet } from './cardParts'

const NO_KEYS: ReadonlySet<string> = new Set()

/**
 * A lean, scannable recommendation card (Epic 019 · DD1) — one tap opens Detail,
 * no nested interactive elements. The card is a glanceable PEER: verdict, name,
 * its decision facts, the elevation glyph, ONE "Now" condition line, and any
 * verified warning — the commitment view (character, fit, the full condition
 * list, sources) lives on Detail. It renders the SAME CardVM Detail does (no VM
 * change): the condition value carries its provenance through <Confidence>, so a
 * sampled value is visibly demoted and tagged — never indistinguishable from a
 * verified one (R1).
 *
 * The `hoisted*` props (F1/F3, ux-review 2026-07) name signals the feed already
 * states once — the alert banner and the conditions ribbon — so this card stops
 * re-RENDERING them and carries only its per-trail deltas. Rendering-only: the
 * verdict and the accessible name below still derive from the FULL `card`,
 * exactly as Detail does. One signal set, both surfaces: a card can never say
 * "Good to go" while its own Detail says "Caution".
 */
export function RecommendationCard({
  card,
  onOpen,
  hoistedWarningTexts = NO_KEYS,
  hoistedLineKeys = NO_KEYS,
  hoistedStateKeys = NO_KEYS,
}: {
  card: CardVM
  onOpen: () => void
  hoistedWarningTexts?: ReadonlySet<string>
  hoistedLineKeys?: ReadonlySet<string>
  hoistedStateKeys?: ReadonlySet<string>
}) {
  const e = card.enrichment
  const ownWarnings = card.warnings.filter((w) => !hoistedWarningTexts.has(w.text))

  const distanceMiles = resolveMiles(card)
  const ascentFeet = e?.ascentFeet ?? geoAscentFeet(card.geo)
  const durationMinutes = resolveDurationMinutes(card)
  const duration = e?.durationHours ?? (durationMinutes != null ? formatEstimatedDuration(durationMinutes) : null)

  const metrics: MetricItem[] = []
  if (distanceMiles != null) {
    metrics.push({ kind: 'distance', label: 'Distance', value: `${distanceMiles.toFixed(1)} mi`, glyph: glyphs.distance })
  }
  if (ascentFeet != null) {
    metrics.push({ kind: 'ascent', label: 'Ascent', value: `${ascentFeet.toLocaleString()} ft`, glyph: glyphs.ascent })
  } else if (distanceMiles != null) {
    metrics.push({ kind: 'ascent', label: 'Ascent', value: null, glyph: glyphs.ascent })
  }
  if (duration != null) {
    metrics.push({ kind: 'duration', label: 'Duration', value: duration, glyph: glyphs.duration })
  } else if (distanceMiles != null) {
    metrics.push({ kind: 'duration', label: 'Duration', value: null, glyph: glyphs.duration })
  }

  // Filter out hoisted lines
  const unhoistedLines = card.conditionLines.filter((l) => !hoistedLineKeys.has(lineKey(l)))
  const unhoistedConditions = card.conditions?.filter((s) => !hoistedStateKeys.has(conditionStateKey(s))) || []
  
  // Combine warnings into conditions for summarization
  // A warning is effectively a blocked or headsUp condition.
  // Actually, we can just use the summarizer for conditions and warnings.
  const summary = summarizeConditions(unhoistedConditions, unhoistedLines, 'card')

  return (
    <article className="card">
      <button className="card-tap" type="button" onClick={onOpen} aria-label={cardAccessibleName(card.name, card.warnings)}>
        <div className="card-id">
          <Text role="title" as="h3" className="card-name">{card.name}</Text>
          {e?.area || e?.routeShape ? (
            <Text role="bodySm" as="p" className="card-area">{[e?.area, e?.routeShape].filter(Boolean).join(' · ')}</Text>
          ) : null}
        </div>

        <MetricRow items={metrics} className="decision" />

        {card.geo?.elevationProfile ? <ElevationGlyph profile={card.geo.elevationProfile} /> : null}

        {summary && summary.tier !== 'clear' ? (
          <ConditionStatusLine tier={summary.tier} copy={summary.conclusion} />
        ) : null}

        <div className="card-foot">
          {e?.freshness ? <Staleness>{e.freshness}</Staleness> : <span />}
        </div>
      </button>

      <div className="card-actions">
        <SaveButton id={card.id} name={card.name} />
        {card.geo ? <DirectionsLink trailhead={card.geo.trailhead} name={card.name} /> : null}
      </div>
    </article>
  )
}

