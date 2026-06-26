import { Confidence, Signal, Staleness } from '../components'
import { useCard } from '../data/PlannerProvider'
import type { CardVM } from '../data/vm'
import type { OriginKey } from '../types'
import { DecisionItem, TerrainPreview, formatDrive } from './cardParts'

export interface DetailProps {
  id: string
  /** Current frame origin for drive time; omit on a cold deep-link (R7). */
  origin?: OriginKey
  onBack: () => void
  onReplan: () => void
}

/** Viability-first trail detail (v0.3 §9): "can I actually do this today?" */
export function Detail({ id, origin, onBack, onReplan }: DetailProps) {
  const { status, card, reload } = useCard(id, origin)

  return (
    <div className="app-shell">
      <header className="detail-top">
        <button className="back" type="button" onClick={onBack}>
          Back
        </button>
        <span className="wordmark">Detail</span>
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
  return (
    <section className="detail">
      {sampled ? (
        <p className="sample-strip" role="note">
          Sample data — the layout is real; conditions and sources aren’t live yet.
        </p>
      ) : null}

      <section className="detail-head">
        <p className="kicker">Viability</p>
        <h1 className="detail-name">{card.name}</h1>
        {e?.area || e?.routeShape ? (
          <p className="detail-area">{[e?.area, e?.routeShape].filter(Boolean).join(' · ')}</p>
        ) : null}

        <div className="detail-facts">
          {e?.driveMinutes != null ? <DecisionItem label="Drive" value={formatDrive(e.driveMinutes)} /> : null}
          {e?.distanceMiles != null ? (
            <DecisionItem label="Distance" value={`${e.distanceMiles.toFixed(1)} mi`} />
          ) : card.distanceMi != null ? (
            <DecisionItem label="Distance" value={`${card.distanceMi.toFixed(1)} mi`} />
          ) : null}
          {e?.ascentFeet != null ? (
            <DecisionItem label="Ascent" value={`${e.ascentFeet.toLocaleString()} ft`} />
          ) : null}
          {e?.durationHours ? <DecisionItem label="Duration" value={e.durationHours} /> : null}
        </div>

        <ConditionLines card={card} />

        {e?.caution ? <Signal className="signal--detail">{e.caution}</Signal> : null}
        {e?.practicalNote ? <p className="detail-practical">{e.practicalNote}</p> : null}
      </section>

      {e?.terrainPath && e?.profilePath ? (
        <section className="detail-block">
          <p className="kicker">Terrain</p>
          <div className="terrain-grid terrain-grid--detail">
            <TerrainPreview values={e.terrainPath} label="Route / terrain" />
            <TerrainPreview values={e.profilePath} label="Elevation profile" />
          </div>
        </section>
      ) : null}

      {e?.character ? (
        <section className="detail-block">
          <p className="kicker">Character</p>
          <p className="prose">{e.character}</p>
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

/** The "Now" conditions, each carrying its own source + confidence tier. */
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
  if (card.conditionLines.length === 0) return null
  return (
    <ul className="condition-lines condition-lines--detail">
      {card.conditionLines.map((line, i) => (
        <li key={i} className="condition-line">
          <Confidence level={line.confidence} provenance={line.provenance}>
            {line.text}
          </Confidence>
        </li>
      ))}
    </ul>
  )
}

/**
 * Source basis. Reuses the real per-line sources/confidence; only adds the
 * enrichment source list when present (and the sample strip already discloses
 * mock provenance — we never dress a fabricated source as inspected truth, R11).
 */
function TrustCue({ card }: { card: CardVM }) {
  const e = card.enrichment
  return (
    <div className="trust-cue">
      {e?.freshness ? <Staleness>{e.freshness}</Staleness> : null}
      {e?.sources && e.sources.length > 0 ? (
        <ul className="source-list">
          {e.sources.map((source) => (
            <li key={source}>{source}</li>
          ))}
        </ul>
      ) : card.conditionLines.length > 0 ? (
        <ul className="source-list">
          {card.conditionLines.map((line, i) => (
            <li key={i}>{line.source}</li>
          ))}
        </ul>
      ) : (
        <p className="prose">Full source inspection lands when trail detail is wired to live data.</p>
      )}
    </div>
  )
}
