import { Confidence, Staleness } from '../components'
import type { CardVM } from '../data/vm'
import {
  cardAccessibleName,
  ConditionSilence,
  DecisionItem,
  DirectionsLink,
  formatDrive,
  SaveButton,
  Verdict,
  WarningBlock,
} from './cardParts'
import { glyphs } from './glyphs'
import { ElevationGlyph } from './map/ElevationGlyph'

/**
 * A lean, scannable recommendation card (Epic 019 · DD1) — one tap opens Detail,
 * no nested interactive elements. The card is a glanceable PEER: verdict, name,
 * a couple of decision facts, the elevation glyph, ONE "Now" condition line, and
 * any verified warning — the commitment view (character, fit, the full condition
 * list, sources) lives on Detail. It renders the SAME CardVM Detail does (no VM
 * change): the condition value carries its provenance through <Confidence>, so a
 * sampled value is visibly demoted and tagged — never indistinguishable from a
 * verified one (R1).
 */
export function RecommendationCard({ card, onOpen }: { card: CardVM; onOpen: () => void }) {
  const e = card.enrichment
  return (
    <article className="card">
      <button className="card-tap" type="button" onClick={onOpen} aria-label={cardAccessibleName(card.name, card.warnings)}>
        <Verdict card={card} className="verdict--card" />

        <div className="card-id">
          <h3 className="card-name">{card.name}</h3>
          {e?.area || e?.routeShape ? (
            <p className="card-area">{[e?.area, e?.routeShape].filter(Boolean).join(' · ')}</p>
          ) : null}
        </div>

        {/* Two decision facts only (DD1). The glyph below owns ascent, so there
            is no separate Ascent fact on the lean card — the full fact set (incl.
            Ascent + Duration) lives on Detail. */}
        <div className="decision">
          {e?.distanceMiles != null ? (
            <DecisionItem label="Distance" value={`${e.distanceMiles.toFixed(1)} mi`} glyph={glyphs.distance} />
          ) : card.distanceMi != null ? (
            <DecisionItem label="Distance" value={`${card.distanceMi.toFixed(1)} mi`} glyph={glyphs.distance} />
          ) : null}
          {e?.driveMinutes != null ? (
            <DecisionItem label="Drive" value={formatDrive(e.driveMinutes)} glyph={glyphs.drive} />
          ) : null}
        </div>

        {card.geo?.elevationProfile ? <ElevationGlyph profile={card.geo.elevationProfile} /> : null}

        <ConditionBlock card={card} />

        {/* A verified hazard STAYS on the card, collapsed under the verdict that
            already speaks it — source + age retained, sentence suppressed
            (AC-19.1.3). It is never relocated off the card. */}
        <WarningBlock warnings={card.warnings} collapsed />

        <div className="card-foot">
          {e?.freshness ? <Staleness>{e.freshness}</Staleness> : <span />}
          <span className="open-detail">Open detail</span>
        </div>
      </button>

      {/* Outside the tap button on purpose: the card's whole-tap target never
          nests another interactive element, so Save/Directions live as sibling
          controls in their own row. */}
      <div className="card-actions">
        <SaveButton id={card.id} name={card.name} />
        {card.geo ? <DirectionsLink trailhead={card.geo.trailhead} name={card.name} /> : null}
      </div>
    </article>
  )
}

/**
 * The single "Now" condition slot (DD1 line 6). It shows exactly ONE value —
 * the merged condition when enrichment supplies one, else the primary live/thin
 * condition line — always through <Confidence>, so honesty is structural. The
 * FULL multi-line list and its residual-silence note live on Detail; here the
 * empty case degrades to a single legible silence state (CDP-02), never a blank
 * and never a false-clear.
 */
function ConditionBlock({ card }: { card: CardVM }) {
  const e = card.enrichment
  const primary = card.conditionLines[0]
  if (e?.conditionValue) {
    return (
      <div className="condition">
        <span className="condition-label">Now</span>
        <span className="condition-value">
          <Confidence level={primary?.confidence ?? 'stated'} provenance={e.provenance}>
            {e.conditionValue}
          </Confidence>
        </span>
      </div>
    )
  }
  if (primary) {
    return (
      <div className="condition">
        <span className="condition-label">Now</span>
        <span className="condition-value">
          <Confidence level={primary.confidence} provenance={primary.provenance}>
            {primary.text}
          </Confidence>
        </span>
      </div>
    )
  }
  // No usable line: a legible silence rather than a blank card (CDP-02). The
  // honest default when the backend signals nothing is `not-fetched` — we never
  // imply we *checked and it's clear* without a source.
  return <ConditionSilence silence={card.conditionSilence ?? { state: 'not-fetched' }} />
}
