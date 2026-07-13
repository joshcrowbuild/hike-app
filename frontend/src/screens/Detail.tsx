import { Confidence, Icon, Signal, Staleness } from '../components'
import { gpxExportUrl } from '../data/geo'
import { useCard, useTrailWater } from '../data/PlannerProvider'
import type { CardVM, TrailWaterVM } from '../data/vm'
import { waterHeadline, waterNote } from '../data/water'
import {
  ConditionSilence,
  DecisionItem,
  DifficultyBadge,
  DirectionsLink,
  formatDrive,
  geoAscentFeet,
  SaveButton,
  TrailSummary,
  Verdict,
  verdictSpokenWarningText,
  WarningBlock,
} from './cardParts'
import { deriveSummary } from '../data/summary'
import { formatEstimatedDuration } from '../data/duration'
import { ConditionStates } from './ConditionStates'
import { glyphs } from './glyphs'
import { TerrainMap } from './map/TerrainMap'

export interface DetailProps {
  id: string
  onBack: () => void
  onReplan: () => void
}

/**
 * Decision-first trail detail (v0.3 §9): "should you go — can I actually do this today?"
 * `useCard` resolves the tapped card from the feed already in context — no
 * origin/tuning threading needed here; a cold deep-link falls back to
 * whatever frame `useCard` last saw (R7).
 */
export function Detail({ id, onBack, onReplan }: DetailProps) {
  const { status, card, reload } = useCard(id)

  return (
    <div className="app-shell">
      <header className="detail-top">
        <button className="back" type="button" onClick={onBack}>
          Back
        </button>
        <span className="screen-title">Detail</span>
      </header>

      {status === 'loading' ? <p className="state-note">Loading…</p> : null}

      {status === 'error' ? (
        <div className="state-block">
          <p className="state-note">Couldn’t load this trail.</p>
          <button className="text-action" type="button" onClick={reload}>
            Try again
          </button>
        </div>
      ) : null}

      {status === 'notfound' ? (
        <div className="state-block">
          <p className="state-note">This trail isn’t in your current set.</p>
          <button className="text-action" type="button" onClick={onReplan}>
            Back to the feed
          </button>
        </div>
      ) : null}

      {status === 'ready' && card ? <DetailBody card={card} /> : null}
    </div>
  )
}

function DetailBody({ card }: { card: CardVM }) {
  const e = card.enrichment
  const sampled = e?.provenance && e.provenance !== 'live'
  // The water answer (Epic 041): null = not-fetched silence → no row at all.
  const { water } = useTrailWater(card.id)
  // Mock enrichment carries its own ascentFeet; a live card has none yet, so it
  // falls back to the real elevation profile rather than a false "coming soon"
  // pointer to a figure that never shows up (report #2).
  const ascentFeet = e?.ascentFeet ?? geoAscentFeet(card.geo)
  return (
    <section className="detail">
      {sampled ? (
        <p className="sample-strip" role="note">
          Sample data — the layout is real; conditions and sources aren’t live yet.
        </p>
      ) : null}

      <section className="detail-head">
        <p className="kicker">Conditions</p>
        <h1 className="detail-name">{card.name}</h1>
        {e?.area || e?.routeShape ? (
          <p className="detail-area">{[e?.area, e?.routeShape].filter(Boolean).join(' · ')}</p>
        ) : null}

        {/* The poetic place cue lives on the commitment view now, not the lean
            feed card (Epic 019). */}
        {e?.placeCue ? <p className="detail-place">{e.placeCue}</p> : null}

        <Verdict card={card} className="verdict--detail" />

        <WarningBlock warnings={card.warnings} spokenText={verdictSpokenWarningText(card)} />

        <div className="detail-actions">
          <SaveButton id={card.id} name={card.name} />
          {card.geo ? <DirectionsLink trailhead={card.geo.trailhead} name={card.name} /> : null}
          {card.geo?.geometry ? (
            <a
              className="action-chip"
              download
              href={gpxExportUrl(card.id)}
              aria-label={`Download the ${card.name} route as a GPX file`}
            >
              <Icon glyph={glyphs.download} label="Download" className="action-chip-icon" />
              GPX
            </a>
          ) : null}
        </div>

        <div className="detail-facts">
          {e?.driveMinutes != null ? (
            <DecisionItem label="Drive" value={formatDrive(e.driveMinutes)} glyph={glyphs.drive} />
          ) : null}
          {e?.distanceMiles != null ? (
            <DecisionItem label="Distance" value={`${e.distanceMiles.toFixed(1)} mi`} glyph={glyphs.distance} />
          ) : card.distanceMi != null ? (
            <DecisionItem label="Distance" value={`${card.distanceMi.toFixed(1)} mi`} glyph={glyphs.distance} />
          ) : null}
          {ascentFeet != null ? (
            <DecisionItem label="Ascent" value={`${ascentFeet.toLocaleString()} ft`} glyph={glyphs.ascent} />
          ) : null}
          {e?.durationHours ? (
            <DecisionItem label="Duration" value={e.durationHours} glyph={glyphs.duration} />
          ) : card.geo?.elevationProfile?.estimatedDurationMin != null ? (
            <DecisionItem
              label="Duration"
              value={formatEstimatedDuration(card.geo.elevationProfile.estimatedDurationMin)}
              glyph={glyphs.duration}
            />
          ) : null}
        </div>

        <WaterFact water={water} />

        {/* A derived difficulty estimate (R2: presentation only, never ranking). */}
        <DifficultyBadge card={card} />

        <ConditionLines card={card} />

        {e?.caution ? <Signal className="signal--detail">{e.caution}</Signal> : null}
        {e?.practicalNote ? <p className="detail-practical">{e.practicalNote}</p> : null}
      </section>

      {card.geo ? (
        <TerrainMap
          geo={card.geo}
          trailName={card.name}
          // Markers only in the answered state (AC-3.2) — an answered-empty or
          // a silent region puts nothing on the map.
          water={water?.state === 'sources' ? water : undefined}
        />
      ) : null}

      {/* The honest one-line character, DERIVED from the card's own verified
          figures (R1) — it replaces the hand-written prose that could not scale
          without fabricating texture. `null` when nothing verified is worth
          saying, so the section drops rather than pad. */}
      {deriveSummary(card) ? (
        <section className="detail-block">
          <p className="kicker">Character</p>
          <TrailSummary card={card} className="prose" />
        </section>
      ) : null}

      {e?.fitLine ? (
        <section className="detail-block">
          <p className="kicker">Why it fits</p>
          <p className="prose">{e.fitLine}</p>
        </section>
      ) : null}

      <section className="detail-block">
        <p className="kicker">Sources</p>
        <TrustCue card={card} />
      </section>
    </section>
  )
}

/**
 * The one water line (Epic 041) — a TRAIL FACT in the facts area, answering
 * "can I refill, or do I carry everything?". Deliberately NOT part of the
 * conditions block or the six-state system: water sources are slow/structural
 * corpus data, not a live probe. The CDP-02 three ways render as:
 * - `sources`      → the answer + the "not verified live" hedge
 * - `none-nearby`  → a calm answered-empty (same quiet treatment — an answer,
 *                    never the flagged couldn't-verify styling)
 * - `null`         → NOTHING (not-fetched silence: the region has no water
 *                    data, or the read failed — no row, no empty claim)
 */
function WaterFact({ water }: { water: TrailWaterVM | null }) {
  if (!water) return null
  return (
    <div className="detail-water">
      <p className="detail-water-line">
        {/* DecisionItem's label pattern: the Icon carries the sr-only name and
            the visible twin is aria-hidden, so "Water" is announced once. */}
        <span className="detail-water-label">
          <Icon glyph={glyphs.water} label="Water" className="detail-water-icon" />
          <span aria-hidden="true">Water</span>
        </span>
        <span className="detail-water-text">{waterHeadline(water)}</span>
      </p>
      <p className="detail-water-note">{waterNote(water)}</p>
    </div>
  )
}

/**
 * The full "Now" conditions, each carrying its own source + confidence tier —
 * the commitment view (Epic 019) shows every line, not just the card's single
 * slot. The empty case and the residual-silence note (the shown set isn't
 * exhaustive, AC-4.3) render here through the shared <ConditionSilence>.
 */
function ConditionLines({ card }: { card: CardVM }) {
  const e = card.enrichment
  if (e?.conditionValue) {
    return (
      <div className="condition condition--detail">
        <span className="condition-label">Now</span>
        <span className="condition-value">
          <Confidence level={card.conditionLines[0]?.confidence ?? 'stated'} provenance={e.provenance}>
            {e.conditionValue}
          </Confidence>
        </span>
      </div>
    )
  }
  // The per-kind coverage list (Epic 018 S4f): every kind's disposition, row
  // per kind — present rows quietly confirm the lines above; each silence state
  // renders visibly distinct (no_hazard = calm sourced silence; unavailable =
  // the flagged couldn't-verify; not_fetched = quiet not-checked). The payload
  // supersedes the legacy blanket silence.
  const coverage = card.conditions && card.conditions.length > 0 ? <ConditionStates conditions={card.conditions} /> : null
  if (card.conditionLines.length === 0) {
    return coverage ?? <ConditionSilence silence={card.conditionSilence ?? { state: 'not-fetched' }} />
  }
  return (
    <>
      <ul className="condition-lines condition-lines--detail">
        {card.conditionLines.map((line, i) => (
          <li key={i} className="condition-line">
            <Confidence level={line.confidence} provenance={line.provenance}>
              {line.text}
            </Confidence>
          </li>
        ))}
      </ul>
      {coverage ?? (card.conditionSilence ? <ConditionSilence silence={card.conditionSilence} partial /> : null)}
    </>
  )
}

/**
 * Source basis. We never dress a fabricated provenance list as inspected truth
 * (R11): the enrichment `sources` list is shown ONLY when it is live. For the
 * mock we fall through to the real per-line sources (the one real provenance the
 * API gives) — and tonight those are mock too, so the honest "lands when wired"
 * copy is what actually ships, never a confident fake source list.
 */
function TrustCue({ card }: { card: CardVM }) {
  const e = card.enrichment
  const liveSources = e?.provenance === 'live' && e.sources && e.sources.length > 0 ? e.sources : null
  const realLineSources =
    card.conditionLines.length > 0 && card.conditionLines.every((l) => l.provenance === 'live')
      ? card.conditionLines.map((l) => l.source)
      : null
  const sources = liveSources ?? realLineSources
  return (
    <div className="trust-cue">
      {e?.freshness ? <Staleness>{e.freshness}</Staleness> : null}
      {sources ? (
        <ul className="source-list">
          {sources.map((source, i) => (
            <li key={`${source}-${i}`}>{source}</li>
          ))}
        </ul>
      ) : (
        <p className="prose">Full source inspection lands when trail detail is wired to live data.</p>
      )}
    </div>
  )
}
