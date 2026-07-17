import { Staleness, Text, MetricRow } from '../components'
import type { CardVM } from '../data/vm'
import type { MetricItem } from '../components/MetricRow/MetricRow'
import { cardAccessibleName, DirectionsLink, SaveButton, WarningBlock, geoAscentFeet } from './cardParts'
import { ElevationGlyph } from './map/ElevationGlyph'
import { glyphs } from './glyphs'
import { resolveMiles, resolveDurationMinutes } from '../data/summary'
import { formatEstimatedDuration } from '../data/duration'

const NO_KEYS: ReadonlySet<string> = new Set()

/**
 * A lean, scannable recommendation card (Epic 019 · DD1; frame-conditions-wave
 * Q2) — one tap opens Detail, no nested interactive elements. The card is
 * CONDITIONS-SILENT: no per-card condition summary or state chips (an area fact
 * belongs at area level — the This-feed card carries them, Law 3). It keeps its
 * name, decision facts, the elevation glyph, its actions, and any VERIFIED
 * hazard — a trail under a live alert still SHOWS with its warning (Q1), tinted
 * by the curator's graded severity (Q7: blocked terracotta / heads-up amber).
 *
 * `hoistedWarningTexts` (F1) names the region-wide alert the feed already states
 * once in its banner, so this card carries only its per-trail warnings. The
 * accessible name below still derives from the FULL `card` — a card can never
 * say "Good to go" while its own Detail says "Caution".
 */
export function RecommendationCard({
  card,
  onOpen,
  hoistedWarningTexts = NO_KEYS,
}: {
  card: CardVM
  onOpen: () => void
  hoistedWarningTexts?: ReadonlySet<string>
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

        {/* No spokenText: the redesigned card has no Verdict to "speak" the
            primary warning, so suppressing it here would drop it entirely. */}
        <WarningBlock warnings={ownWarnings} />

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
