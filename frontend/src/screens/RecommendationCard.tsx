import { Confidence, Signal, Staleness } from '../components'
import type { CardVM, ConditionSilence as ConditionSilenceVM, SilenceState } from '../data/vm'
import { cardAccessibleName, DecisionItem, formatDrive, formatTrail, geoAscentFeet, WarningBlock } from './cardParts'
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
  // Mock enrichment carries its own ascentFeet; a live card has none yet, so it
  // falls back to the real elevation profile rather than showing nothing (#2).
  const ascentFeet = e?.ascentFeet ?? geoAscentFeet(card.geo)
  return (
    <article className="card">
      <button className="card-tap" type="button" onClick={onOpen} aria-label={cardAccessibleName(card.name, card.warnings)}>
        {e?.placeCue ? <p className="card-place">{e.placeCue}</p> : null}

        <div className="card-id">
          <h3 className="card-name">{card.name}</h3>
          {e?.area || e?.routeShape ? (
            <p className="card-area">{[e?.area, e?.routeShape].filter(Boolean).join(' · ')}</p>
          ) : null}
        </div>

        <WarningBlock warnings={card.warnings} />

        {card.geo?.elevationProfile ? <ElevationGlyph profile={card.geo.elevationProfile} /> : null}

        <div className="decision">
          {e?.driveMinutes != null ? (
            <DecisionItem label="Drive" value={formatDrive(e.driveMinutes)} />
          ) : null}
          {e?.distanceMiles != null && ascentFeet != null ? (
            <DecisionItem label="Trail" value={formatTrail(e.distanceMiles, ascentFeet)} />
          ) : card.distanceMi != null ? (
            <DecisionItem label="Distance" value={`${card.distanceMi.toFixed(1)} mi`} />
          ) : null}
          {e?.distanceMiles == null && ascentFeet != null ? (
            <DecisionItem label="Ascent" value={`${ascentFeet.toLocaleString()} ft`} />
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
  // No usable line: render a legible silence state rather than a blank card
  // (CDP-02). The honest default when the backend signals nothing is
  // `not-fetched` — we never imply we *checked and it's clear* without a source.
  if (card.conditionLines.length === 0) {
    return <ConditionSilence silence={card.conditionSilence ?? { state: 'not-fetched' }} />
  }
  // Some kinds present, others absent: show the lines, and — when the card
  // discloses a residual silence — a note so the shown set isn't read as
  // exhaustive (AC-4.3).
  return (
    <>
      <ul className="condition-lines">
        {card.conditionLines.map((line, i) => (
          <li key={i} className="condition-line">
            <Confidence level={line.confidence} provenance={line.provenance}>
              {line.text}
            </Confidence>
          </li>
        ))}
      </ul>
      {card.conditionSilence ? <ConditionSilence silence={card.conditionSilence} partial /> : null}
    </>
  )
}

/**
 * The four silence states (CDP-02). Each carries its own copy, a leading glyph,
 * and its own treatment — meaning is never colour-only (glyph + copy differ per
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

function ConditionSilence({ silence, partial }: { silence: ConditionSilenceVM; partial?: boolean }) {
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
