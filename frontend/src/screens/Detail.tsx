import { Confidence, Icon, Signal, Staleness } from '../components'
import { sharedAmong, unclaimedLines } from '../data/feedConditions'
import { gpxExportUrl } from '../data/geo'
import { useCard, useTrailWater } from '../data/PlannerProvider'
import type { CardVM, LineVM, TrailWaterVM } from '../data/vm'
import { waterHeadline, waterNote } from '../data/water'
import {
  ConditionSilence,
  DecisionFacts,
  DifficultyBadge,
  DirectionsLink,
  SaveButton,
  TrailSummary,
  verdictSpokenWarningText,
  WarningBlock,
} from './cardParts'
import { deriveSummary } from '../data/summary'
import { glyphs } from './glyphs'
import { TerrainMap } from './map/TerrainMap'
import { Text } from '../components'
import { DetailConditions } from './DetailConditions'

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
  return (
    <section className="detail">
      {sampled ? (
        <p className="sample-strip" role="note">
          Sample data — the layout is real; conditions and sources aren’t live yet.
        </p>
      ) : null}

      <section className="detail-head">
        <Text role="display" as="h1" className="detail-name">{card.name}</Text>
        {e?.area || e?.routeShape ? (
          <p className="detail-area">{[e?.area, e?.routeShape].filter(Boolean).join(' · ')}</p>
        ) : null}

        {/* The poetic place cue lives on the commitment view now, not the lean
            feed card (Epic 019). */}
        {e?.placeCue ? <p className="detail-place">{e.placeCue}</p> : null}

        <WarningBlock warnings={card.warnings} />

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

        <DecisionFacts card={card} className="detail-facts" />

        <WaterFact water={water} />

        {/* A derived difficulty estimate (R2: presentation only, never ranking). */}
        <DifficultyBadge card={card} />

        <DetailConditions card={card} />

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
 * Source basis. We never dress a fabricated provenance list as inspected truth
 * (R11): the enrichment `sources` list is shown ONLY when it is live. For the
 * mock we fall through to the real per-line sources (the one real provenance the
 * API gives) — and tonight those are mock too, so the honest "lands when wired"
 * copy is what actually ships, never a confident fake source list.
 */
function TrustCue({ card }: { card: CardVM }) {
  const e = card.enrichment
  const liveSources = e?.provenance === 'live' && e.sources && e.sources.length > 0 ? e.sources : null
  const liveLines =
    card.conditionLines.length > 0 && card.conditionLines.every((l) => l.provenance === 'live')
      ? card.conditionLines
      : null
  return (
    <div className="trust-cue">
      {e?.freshness ? <Staleness>{e.freshness}</Staleness> : null}
      {liveSources ? (
        <ul className="source-list">
          {liveSources.map((source, i) => (
            <li key={`${source}-${i}`}>{source}</li>
          ))}
        </ul>
      ) : liveLines ? (
        <SourceList lines={liveLines} />
      ) : (
        <p className="prose">Full source inspection lands when trail detail is wired to live data.</p>
      )}
    </div>
  )
}

// The closed vocabulary `present.py::_source_note` welds onto every line's
// `source` (`"<label> · <descriptor>[ (<origin>)]"`) — a CDP-01 honesty
// disclosure ("this fact hasn't been cross-checked against a second
// provider") that reads near-identically on almost every row (A5, Epic 046
// S1 AC-1.5). `source` itself is an untouched, already-locked wire field
// (`tests/test_present.py`), so the two known phrases are matched directly
// rather than adding a parallel structured field just for this de-duplication.
const SOURCE_DESCRIPTORS = ['single authoritative source', 'single aggregated source'] as const

/** Which of the two known descriptors (if either) a composed `source` label
 *  carries — `undefined` for a source that doesn't follow the convention (an
 *  older/synthetic value), which then renders untouched, never guessed at. */
function sourceDescriptor(source: string): (typeof SOURCE_DESCRIPTORS)[number] | undefined {
  return SOURCE_DESCRIPTORS.find((d) => source.includes(` · ${d}`))
}

/**
 * The Sources section's row list (A5). Stating the majority descriptor ONCE
 * for the section — rather than on every row — drops nothing: a row whose
 * descriptor is the MINORITY (an aggregator kind, e.g. AirNow) keeps its full
 * original text, still fully disclosed inline. `sharedAmong` (binding decision
 * 2) requires at least two rows to actually share a descriptor before calling
 * it "shared" — a lone match is just that one row's own note, not a
 * section-wide pattern.
 */
function SourceList({ lines }: { lines: LineVM[] }) {
  const shared = sharedAmong(lines.map((l) => sourceDescriptor(l.source)))
  return (
    <>
      <ul className="source-list">
        {lines.map((l, i) => {
          const d = sourceDescriptor(l.source)
          const label = d && d === shared ? l.source.replace(` · ${d}`, '') : l.source
          return <li key={`${l.source}-${i}`}>{label}</li>
        })}
      </ul>
      {shared ? (
        <p className="prose source-note">
          Each of these is a {shared} — not yet cross-checked against another provider.
        </p>
      ) : null}
    </>
  )
}
