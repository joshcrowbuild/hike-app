/**
 * The per-kind condition coverage renderer (Epic 018 S4f / CDP-02) — the surface
 * for the six-state `conditions` payload the API returns. Every kind's
 * disposition renders visibly distinct through glyph + copy + treatment, never
 * colour alone (§4.3):
 *
 * - `present` / `stale-degraded` carry a sourced value (the condition lines);
 *   here they render as quiet coverage rows, stale wearing its age through the
 *   <Staleness> primitive ("last known 3h ago — may have changed").
 * - `no-hazard` is CALM sourced silence — "checked, nothing to flag" with its
 *   source + age, never a loud "0 detections" (the quiet field of CDP-02).
 * - `no-data` is a sourced coverage gap, carrying the adapter's own disclosure.
 * - `unavailable` (probed, no answer) routes through the flagged <Confidence>
 *   tier — the design system's owned couldn't-verify treatment — so an outage
 *   can never be mistaken for the quiet `not-fetched` row below it.
 * - `not-fetched` is the honest "no signal either way": muted, dashed, and
 *   copy-distinct from an outage.
 *
 * Presentation only — never a ranking input (Rule #2). `compact` renders the
 * card's grouped one-row-per-state summary; the default renders Detail's
 * row-per-kind coverage list.
 *
 * Detail's default (non-compact) list additionally takes `lines` (ux-review
 * 2026-07 Finding 4/7): the human-readable VALUE a `present`/`stale-degraded`
 * row's line carries ("Sunny 90°F") is folded into that row via
 * `foldLineValue`, so the value is stated once, in the table, framed by the
 * row's own honest state — never a second prose sentence repeating it.
 */
import { Confidence, Staleness } from '../components'
import { foldLineValue, sharedAmong } from '../data/feedConditions'
import type { ConditionStateVM, ConditionStatusVM, LineVM } from '../data/vm'
import { glyphs } from './glyphs'

/** Human labels for the wire condition kinds. An unknown kind falls back to the
 *  raw wire string — disclosed as-is, never dropped (Rule #1). */
export const conditionKindLabels: Record<string, string> = {
  weather: 'Weather',
  air: 'Air quality',
  fire: 'Fire',
  water: 'Streamflow',
  closures: 'Closures',
  permits: 'Permits',
}

const kindLabel = (kind: string): string => conditionKindLabels[kind] ?? kind

/**
 * Per-state copy + text glyph. Mirrors `cardParts`' SILENCE_COPY vocabulary.
 * `present` and `no-hazard` share ✓ but never a treatment (bare mark vs filled
 * chip) or copy; every other state has its own glyph, with `stale-degraded`
 * carrying the real Lucide `History` mark (AC-20.3.1) and `unavailable`
 * carrying no glyph of its own — its whole body routes through flagged
 * <Confidence>, whose treatment (the verify accent + sr-only lead-in) is the
 * distinguisher.
 */
const STATE_COPY: Record<ConditionStateVM, { glyph: string | null; announce: string; label: string }> = {
  present: { glyph: '✓', announce: 'Reported', label: 'reported' },
  'stale-degraded': { glyph: null, announce: 'Stale, may have changed', label: 'last known' },
  'no-hazard': { glyph: '✓', announce: 'Checked, nothing to flag', label: 'checked — nothing to flag' },
  'no-data': { glyph: '–', announce: 'No source covers this spot', label: 'no coverage here' },
  unavailable: { glyph: '×', announce: '', label: 'couldn’t be verified right now' },
  'not-fetched': { glyph: '○', announce: 'Not checked yet', label: 'not checked here' },
}

/** Grouped display order for the compact card summary: sourced answers first,
 *  then the outage, then the quietest state last. */
const COMPACT_ORDER: ConditionStateVM[] = [
  'stale-degraded',
  'no-hazard',
  'no-data',
  'unavailable',
  'not-fetched',
]

export function ConditionStates({
  conditions,
  compact = false,
  lines = [],
}: {
  conditions: ConditionStatusVM[]
  /** Card mode: one grouped row per state, kinds joined — the lean summary. */
  compact?: boolean
  /**
   * The card's condition-line prose (Detail mode only) — each `present`/
   * `stale-degraded` row claims its matching line's value by source (Finding
   * 4/7), so the value renders once, inside the row. Unclaimed lines (no
   * `conditions` payload covers them, an older backend) are the caller's own
   * fallback to render, never silently dropped.
   */
  lines?: LineVM[]
}) {
  if (conditions.length === 0) return null
  if (compact) return <CompactStates conditions={conditions} />
  const claimed = new Set<LineVM>()
  // Block-scope freshness (AC-1.4): `stale-degraded` rows never participate —
  // they always carry their own unconditional age + "may have changed" hedge,
  // a distinct disclosure that must never be folded into a generic stamp.
  const blockAge = sharedAmong(
    conditions.filter((s) => s.state !== 'stale-degraded').map((s) => s.checkedAgo),
  )
  return (
    <>
      {blockAge ? (
        <p className="condition-states-stamp">
          <Staleness>Checked {blockAge}</Staleness>
        </p>
      ) : null}
      <ul className="condition-states">
        {conditions.map((s) => (
          <li key={s.kind} className={`condition-state condition-state--${s.state}`}>
            <span className="condition-state-kind">{kindLabel(s.kind)}</span>
            <StateBody status={s} value={foldLineValue(s, lines, claimed)} blockAge={blockAge} />
          </li>
        ))}
      </ul>
    </>
  )
}

function CompactStates({ conditions }: { conditions: ConditionStatusVM[] }) {
  const groups = COMPACT_ORDER.map(
    (state) => [state, conditions.filter((s) => s.state === state)] as const,
  ).filter(([, members]) => members.length > 0)
  if (groups.length === 0) return null
  return (
    <div className="condition-states condition-states--compact">
      {groups.map(([state, members]) => (
        <CompactGroup key={state} state={state} members={members} />
      ))}
    </div>
  )
}

/**
 * One grouped compact row, e.g. "✓ Checked — nothing to flag · 20m ago: Fire
 * (FIRMS), Closures (NPS)". A shared age states once for the whole group (A4,
 * Epic 046 S1 AC-1.5) rather than once per kind; a member whose age DIVERGES
 * from the group keeps its own inline, never silently dropped. Source stays
 * on each kind regardless (it differs and carries info); the no-data
 * disclosure detail is Detail-only.
 */
function CompactGroup({ state, members }: { state: ConditionStateVM; members: ConditionStatusVM[] }) {
  const copy = STATE_COPY[state]
  const groupAge = sharedAmong(members.map((s) => s.checkedAgo))
  const kinds = members.map((s) => {
    const age = s.checkedAgo && s.checkedAgo !== groupAge ? s.checkedAgo : undefined
    const meta = [s.source, age].filter(Boolean).join(' · ')
    return meta ? `${kindLabel(s.kind)} (${meta})` : kindLabel(s.kind)
  })
  if (state === 'unavailable') {
    return (
      <p className="condition-state-group condition-state--unavailable">
        <Confidence level="flagged" provenance="live">
          Couldn’t verify: {kinds.join(', ')}
        </Confidence>
      </p>
    )
  }
  return (
    <p className={`condition-state-group condition-state--${state}`}>
      <span className="sr-only">{copy.announce}: </span>
      <span className="condition-state-glyph" aria-hidden="true">
        {copy.glyph ?? <HistoryGlyph />}
      </span>
      <span className="condition-state-text">
        {compactLabel(state)}
        {groupAge ? (
          <>
            {' · '}
            <Staleness>{groupAge}</Staleness>
          </>
        ) : null}
        {': '}
        {kinds.join(', ')}
      </span>
    </p>
  )
}

const compactLabel = (state: ConditionStateVM): string =>
  state === 'stale-degraded'
    ? 'Last known — may have changed'
    : state === 'no-hazard'
      ? 'Checked — nothing to flag'
      : state === 'no-data'
        ? 'No coverage here'
        : 'Not checked here'

/**
 * One kind's full-row body (Detail's coverage list). `value` is the folded
 * line for a `present`/`stale-degraded` row (Finding 4/7) — its VALUE (`body`:
 * hedge + value, no source/age) renders ahead of the disposition label
 * ("Sunny 90°F · reported"), so the row states the actual fact once, framed
 * by its own honest state (never the line's own separately-hedged framing,
 * which the merge retires along with the line). Reading `value.text` here
 * instead of `value.body` would re-weld the line's own source+age onto the
 * row, which ALSO renders `status.source`/`status.checkedAgo` in `meta` below
 * — the A3 in-row double this split exists to prevent (falls back to `.text`
 * only for an older/mock line that never got the `body` field, never for a
 * roundtrip through the live wire).
 */
function StateBody({
  status,
  value,
  blockAge,
}: {
  status: ConditionStatusVM
  value?: LineVM
  /** The block-scope freshness stamp (if any, AC-1.4) — a row's own age is
   *  suppressed here exactly when it agrees with this value; a diverging row
   *  still renders its own, so nothing is silently dropped. */
  blockAge?: string
}) {
  const copy = STATE_COPY[status.state]
  if (status.state === 'unavailable') {
    // The design system's owned couldn't-verify treatment: flagged <Confidence>
    // supplies the verify accent AND the "Unverified, verify before you go"
    // sr-only lead-in — an outage is loud where not-fetched is quiet.
    return (
      <span className="condition-state-body">
        <Confidence level="flagged" provenance="live">
          {copy.label}
        </Confidence>
      </span>
    )
  }
  // `stale-degraded` never reads its age here — it always carries its own
  // unconditional age + "may have changed" hedge below, untouched by the
  // block-scope collapse. Every other answered state suppresses its OWN age
  // only when it agrees with `blockAge` (the block already states it once);
  // a diverging age (or no shared block age at all) still renders per-row.
  const rowAge =
    status.checkedAgo && status.state !== 'stale-degraded' && status.checkedAgo !== blockAge
      ? status.checkedAgo
      : undefined
  const meta = status.source ? (
    <span className="condition-state-meta">
      {' · '}
      {status.source}
      {rowAge ? (
        <>
          {' · '}
          <Staleness>{rowAge}</Staleness>
        </>
      ) : null}
    </span>
  ) : null
  return (
    <span className="condition-state-body">
      <span className="sr-only">{copy.announce}: </span>
      <span className="condition-state-glyph" aria-hidden="true">
        {copy.glyph ?? <HistoryGlyph />}
      </span>
      <span className="condition-state-text">
        {value ? <span className="condition-state-value">{value.body ?? value.text} · </span> : null}
        {copy.label}
        {status.state === 'stale-degraded' ? (
          // The hedge is unconditional — a stale row without an age must still
          // say "may have changed", never read as a bare current value.
          <>
            {status.checkedAgo ? (
              <>
                {' '}
                <Staleness stale>{status.checkedAgo}</Staleness>
              </>
            ) : null}
            {' — may have changed'}
          </>
        ) : null}
        {status.state === 'no-data' && status.detail ? ` — ${status.detail}` : null}
      </span>
      {meta}
    </span>
  )
}

/**
 * `history` — reserved solely for the stale-degraded state (DD2: never the
 * hazard glyph). The wrapping `.condition-state-glyph` span is `aria-hidden`,
 * so this rides bare — same idiom as `cardParts`' HistoryIcon.
 */
function HistoryGlyph() {
  return <glyphs.history size={10} aria-hidden="true" focusable={false} />
}
