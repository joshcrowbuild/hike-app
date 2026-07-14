/**
 * The Context Ribbon (ux-vision-2026-07 §5/§9 item 1 — "Implement
 * Region-Scoped Conditions"): Home's top used to be TWO separate elements — a
 * tappable context sentence button (when · where · from) and, below it, a
 * disconnected "In this area" conditions band. The vision's Home header reads
 * the region ONCE, at a glance, as a single confident unit: region + when +
 * origin *together with* the genuinely-shared conditions for that frame,
 * before the cards. This is that unit — one `<section>` landmark, one
 * accessible name, still tappable to open Tuning.
 *
 * The conditions half is unchanged in substance from the original
 * `FeedConditionsRibbon` (ux-review-conditions-2026-07 F3/F9a) — it renders
 * exactly what `splitFeedConditions` hoisted, nothing more: region-scope facts
 * — one NWS zone's weather, one AirNow region's reading or outage, a
 * fire/closure sweep — stated ONCE, with source + stamp, never a fabricated
 * "region weather" invented for the occasion (source-or-silence). A sourced
 * reading keeps its <Confidence> treatment; the silent dispositions reuse the
 * six-state compact renderer, so checked-clear, couldn't-verify and
 * not-checked stay glyph + copy + treatment distinct (§4.3, CDP-02 — the three
 * silences are never flattened into one gray). Presentation only: nothing
 * here is a new fact, and the cards' own VMs are untouched (the verdict still
 * derives from the full card, F1) — `splitFeedConditions`'s hoist keys still
 * drive what each card suppresses.
 *
 * One `<section aria-label>` names the whole band (context + conditions) as a
 * single region landmark, so assistive tech reads the frame once, then the
 * conditions, without leaving the landmark — never two adjacent regions a
 * screen-reader user has to stitch together themselves.
 */
import { Confidence } from '../components'
import { lineKey, type FeedConditions } from '../data/feedConditions'
import { ConditionStates } from './ConditionStates'

export function ContextRibbon({
  contextText,
  onOpenTuning,
  conditions,
}: {
  /** The when · where · from sentence (Home's `contextSentence()`). */
  contextText: string
  onOpenTuning: () => void
  conditions: FeedConditions
}) {
  const { sharedLines, sharedStates } = conditions
  const hasConditions = sharedLines.length > 0 || sharedStates.length > 0
  return (
    <section className="context-ribbon" aria-label="This frame">
      <button className="context-ribbon-head" type="button" onClick={onOpenTuning}>
        <span className="context-ribbon-text">{contextText}</span>
        <span className="context-adjust">Adjust</span>
      </button>

      {hasConditions ? (
        <div className="feed-conditions-body">
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
        </div>
      ) : null}
    </section>
  )
}
