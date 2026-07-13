import { Confidence, Staleness } from '../components'
import { conditionStateKey, lineKey } from '../data/feedConditions'
import type { CardVM } from '../data/vm'
import {
  cardAccessibleName,
  ConditionSilence,
  DecisionItem,
  DirectionsLink,
  formatDrive,
  SaveButton,
  Verdict,
  verdictSpokenWarningText,
  WarningBlock,
} from './cardParts'
import { ConditionStates } from './ConditionStates'
import { glyphs } from './glyphs'
import { ElevationGlyph } from './map/ElevationGlyph'

const NO_KEYS: ReadonlySet<string> = new Set()

/**
 * A lean, scannable recommendation card (Epic 019 · DD1) — one tap opens Detail,
 * no nested interactive elements. The card is a glanceable PEER: verdict, name,
 * a couple of decision facts, the elevation glyph, ONE "Now" condition line, and
 * any verified warning — the commitment view (character, fit, the full condition
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
  /** Warning texts the feed banner already states (F1). */
  hoistedWarningTexts?: ReadonlySet<string>
  /** `lineKey`s the conditions ribbon already states (F3). */
  hoistedLineKeys?: ReadonlySet<string>
  /** `conditionStateKey`s the conditions ribbon already states (F3). */
  hoistedStateKeys?: ReadonlySet<string>
}) {
  const e = card.enrichment
  const ownWarnings = card.warnings.filter((w) => !hoistedWarningTexts.has(w.text))
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

        <ConditionBlock card={card} hoistedLineKeys={hoistedLineKeys} hoistedStateKeys={hoistedStateKeys} />

        {/* A verified trail-specific hazard STAYS on the card — only the one
            sentence the verdict above already speaks is collapsed to source +
            age (AC-19.1.3). A banner-hoisted region-wide warning is
            source-stamped once at feed level instead of ten times here; the
            verdict above still carries it (F1). */}
        <WarningBlock warnings={ownWarnings} spokenText={verdictSpokenWarningText(card)} />

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
 * the merged condition when enrichment supplies one, else the first live/thin
 * condition line the feed ribbon hasn't already stated (F3) — always through
 * <Confidence>, so honesty is structural. The FULL multi-line list and its
 * residual-silence note live on Detail; here the empty case degrades to a
 * single legible silence state (CDP-02), never a blank and never a false-clear.
 */
function ConditionBlock({
  card,
  hoistedLineKeys,
  hoistedStateKeys,
}: {
  card: CardVM
  hoistedLineKeys: ReadonlySet<string>
  hoistedStateKeys: ReadonlySet<string>
}) {
  const e = card.enrichment
  // The card's own Now reading: the first line the ribbon doesn't already
  // state — a region-identical reading yields the slot to a real per-trail
  // delta (a gauge, a microclimate difference) instead of repeating the ribbon.
  const primary = card.conditionLines.find((l) => !hoistedLineKeys.has(lineKey(l)))
  // The per-kind coverage summary (Epic 018 S4f): the kinds that DON'T render
  // as lines — checked-clear, coverage gaps, outages, not-checked — shown as
  // grouped compact rows beneath the Now slot, so the shown line never implies
  // the set is exhaustive (AC-4f.2) and an answered-clear card never reads as
  // couldn't-verify (the retired lines.length===0 mislabel). Dispositions the
  // ribbon already states once are not repeated here (F3/F9a).
  const silentStates = card.conditions?.filter(
    (s) => s.state !== 'present' && s.state !== 'stale-degraded' && !hoistedStateKeys.has(conditionStateKey(s)),
  )
  const summary = silentStates && silentStates.length > 0 ? <ConditionStates conditions={silentStates} compact /> : null
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
  if (primary) {
    return (
      <>
        <div className="condition">
          <span className="condition-label">Now</span>
          <span className="condition-value">
            <Confidence level={primary.confidence} provenance={primary.provenance}>
              {primary.text}
            </Confidence>
          </span>
        </div>
        {summary}
      </>
    )
  }
  if (summary) return summary
  // Everything this card knows is already stated once at feed level: stay
  // silent about what the ribbon said (F3) — rendering the not-fetched
  // fallback here would falsely mark a CHECKED card as never checked.
  if (card.conditionLines.length > 0 || (card.conditions?.length ?? 0) > 0) return null
  // No signal at all: with the per-kind payload absent the legacy blanket
  // silence is the honest default — never a blank, never a false-clear
  // (CDP-02), and never `checked-clear` without a source.
  return <ConditionSilence silence={card.conditionSilence ?? { state: 'not-fetched' }} />
}
