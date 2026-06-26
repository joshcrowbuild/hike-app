import { Confidence, Signal, Staleness } from '../components'
import type { CardVM } from '../data/vm'
import { DecisionItem, formatDrive, formatTrail } from './cardParts'
import { ElevationGlyph } from './map/ElevationGlyph'

/**
 * A peer recommendation card (v0.3 §3) — one tap opens Detail, no nested
 * interactive elements. It renders the SAME CardVM two ways: the rich card when
 * enrichment is present (the destination feel), and an honest-thin card when
 * only `/plan` data exists. The condition value carries its provenance through
 * <Confidence>, so a sampled value is visibly demoted and tagged — never
 * indistinguishable from a verified one (R1).
 */
export function RecommendationCard({ card, onOpen }: { card: CardVM; onOpen: () => void }) {
  const e = card.enrichment
  return (
    <article className="card">
      <button className="card-tap" type="button" onClick={onOpen} aria-label={`Open ${card.name}`}>
        {e?.placeCue ? <p className="card-place">{e.placeCue}</p> : null}

        <div className="card-id">
          <h3 className="card-name">{card.name}</h3>
          {e?.area || e?.routeShape ? (
            <p className="card-area">{[e?.area, e?.routeShape].filter(Boolean).join(' · ')}</p>
          ) : null}
        </div>

        {card.geo?.elevationProfile ? <ElevationGlyph profile={card.geo.elevationProfile} /> : null}

        <div className="decision">
          {e?.driveMinutes != null ? (
            <DecisionItem label="Drive" value={formatDrive(e.driveMinutes)} />
          ) : null}
          {e?.distanceMiles != null && e?.ascentFeet != null ? (
            <DecisionItem label="Trail" value={formatTrail(e.distanceMiles, e.ascentFeet)} />
          ) : card.distanceMi != null ? (
            <DecisionItem label="Distance" value={`${card.distanceMi.toFixed(1)} mi`} />
          ) : null}
        </div>

        <ConditionBlock card={card} />

        {e?.caution ? <Signal>{e.caution}</Signal> : null}

        {e?.fitLine ? <p className="fit">{e.fitLine}</p> : null}

        <div className="card-foot">
          {e?.freshness ? <Staleness>{e.freshness}</Staleness> : <span />}
          <span className="open-detail">Open detail</span>
        </div>
      </button>
    </article>
  )
}

/**
 * The "Now" condition. Rich mode shows the merged condition value (with its
 * provenance); thin mode lists the real per-line condition lines, each with its
 * own source + confidence tier. Either way every value flows through
 * <Confidence>, so honesty is structural, not optional.
 */
function ConditionBlock({ card }: { card: CardVM }) {
  const e = card.enrichment
  if (e?.conditionValue) {
    return (
      <div className="condition">
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
    <ul className="condition-lines">
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
