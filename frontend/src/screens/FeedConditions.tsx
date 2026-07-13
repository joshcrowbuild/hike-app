/**
 * The feed-level conditions ribbon (ux-review-conditions-2026-07 F3/F9a):
 * region-scope facts stated once, under the curation header, instead of
 * verbatim on all ten cards. It renders exactly what `splitFeedConditions`
 * hoisted — a sourced reading keeps its <Confidence> treatment; the silent
 * dispositions reuse the six-state compact renderer, so checked-clear,
 * couldn't-verify and not-checked stay glyph + copy + treatment distinct here
 * exactly as they are on a card (§4.3, CDP-02 — the three silences are never
 * flattened into one gray). A region-wide outage becomes one flagged statement
 * instead of a ten-card wall (F9a: honest ≠ loud).
 *
 * A `<section>` with an accessible name — a named region landmark, so
 * assistive tech can jump to (or past) the area conditions as one unit.
 * Presentation only: nothing here is a new fact, and the cards' own VMs are
 * untouched (the verdict still derives from the full card, F1).
 */
import { Confidence } from '../components'
import { lineKey, type FeedConditions } from '../data/feedConditions'
import { ConditionStates } from './ConditionStates'

export function FeedConditionsRibbon({ conditions }: { conditions: FeedConditions }) {
  const { sharedLines, sharedStates } = conditions
  if (sharedLines.length === 0 && sharedStates.length === 0) return null
  return (
    <section className="feed-conditions" aria-label="Conditions across this area">
      <p className="kicker feed-conditions-scope">In this area</p>
      {sharedLines.length > 0 ? (
        <ul className="condition-lines feed-conditions-lines">
          {/* Rows are keyed on the same full-fact identity the split dedupes
              on (`lineKey`), so two lines differing only in confidence or
              provenance can never collide. */}
          {sharedLines.map((line) => (
            <li key={lineKey(line)} className="condition-line">
              <Confidence level={line.confidence} provenance={line.provenance}>
                {line.text}
              </Confidence>
            </li>
          ))}
        </ul>
      ) : null}
      {sharedStates.length > 0 ? <ConditionStates conditions={sharedStates} compact /> : null}
    </section>
  )
}
