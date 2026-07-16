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
import { Confidence, Text } from '../components'
import { lineKey, type FeedConditions } from '../data/feedConditions'
import { ConditionStates } from './ConditionStates'

export function ContextSentence({
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
    <section className="context-sentence" aria-label="This frame">
      <div className="context-sentence-head">
        <Text role="lead" as="span" className="context-sentence-text">{contextText}</Text>
        <button className="context-edit-action" type="button" onClick={onOpenTuning}>
          Edit
        </button>
      </div>

      {hasConditions ? (
        <div className="feed-conditions-body">
          {sharedLines.length > 0 ? (
            <div className="feed-conditions-line">
              {/* Rows are keyed on the same full-fact identity the split dedupes
                  on (`lineKey`), so two lines differing only in confidence or
                  provenance can never collide. */}
              {sharedLines.map((line) => (
                <div key={lineKey(line)} className="condition-line">
                  <Confidence level={line.confidence} provenance={line.provenance}>
                    {line.text}
                  </Confidence>
                </div>
              ))}
            </div>
          ) : null}
          {sharedStates.length > 0 ? <ConditionStates conditions={sharedStates} compact /> : null}
        </div>
      ) : null}
    </section>
  )
}
