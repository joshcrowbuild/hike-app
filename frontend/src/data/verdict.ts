/**
 * The go/no-go headline (product voice, 2026-07-03). A hedged verdict DERIVED
 * from the same real signals a card already shows — its verified hazard warnings
 * and its verified conditions — so it is a *summary*, never a new fact and never
 * a guarantee (source-or-silence, R1). It is presentation only: it summarizes the
 * signals, it NEVER touches ranking (Rule #2). Its `provenance` follows the
 * driving signal so the surface can demote/tag a non-live verdict, exactly as the
 * <Confidence> primitive demotes a non-live reading — a sampled "go" can never
 * wear the costume of a verified one.
 */
import type { CardVM, ConditionStateVM, Provenance } from './vm'

export type VerdictTone = 'go' | 'caution' | 'unverified'

export interface VerdictVM {
  tone: VerdictTone
  /** The lead phrase — "Good to go" | "Caution" | "Heads up". */
  lead: string
  /** The derived reason, from real signals. A summary, never a guarantee. */
  detail: string
  /** Provenance of the driving signal, so a non-live verdict demotes/tags (R1). */
  provenance: Provenance
}

const UNVERIFIED: Omit<VerdictVM, 'provenance'> = {
  tone: 'unverified',
  lead: 'Heads up',
  detail: 'conditions couldn’t be verified',
}

/** The states where a source actually ANSWERED (CDP-02) — the only ones the
 *  go-detail may count as a completed check. `unavailable`/`not-fetched` are
 *  not checks: counting them would dress an outage as a completed sweep. */
const CHECKED_STATES: ReadonlySet<ConditionStateVM> = new Set([
  'present',
  'stale-degraded',
  'no-hazard',
  'no-data',
])

/**
 * The go-detail when no merged reading exists. It claims exactly what was
 * verified and nothing more (F2, ux-review 2026-07 / Invariant 1): "clear" is a
 * weather word, and the old `'conditions look clear'` fallback asserted a
 * sky-state no source had stated — rendered beside a sourced "Showers And
 * Thunderstorms Likely" line, it was an unsourced editorial claim. What the
 * verdict actually means is "nothing blocking", so that is all it says, counted
 * from the six-state payload's answered checks.
 */
function checkedDetail(card: CardVM): string {
  const n = card.conditions?.filter((s) => CHECKED_STATES.has(s.state)).length ?? 0
  if (n === 0) return 'nothing flagged'
  return n === 1 ? 'nothing flagged in 1 check' : `nothing flagged across ${n} checks`
}

/**
 * Derive the verdict from a card's own verified signals. Order matters: a live
 * hazard leads; an unverifiable reading is never dressed as clear (Rule #1); a
 * verified, unflagged reading is the "good to go"; and absence falls back to an
 * honest heads-up (never a false all-clear).
 */
export function deriveVerdict(card: CardVM): VerdictVM {
  // 1) A verified hazard is the headline. Each warning carries its own source +
  //    timestamp, shown in full right below the verdict — this only summarizes it.
  if (card.warnings.length > 0) {
    const [first, ...rest] = card.warnings
    const detail = rest.length > 0 ? `active ${first.text} (+${rest.length} more)` : `active ${first.text}`
    return { tone: 'caution', lead: 'Caution', detail, provenance: first.provenance }
  }

  const e = card.enrichment
  const primary = card.conditionLines[0]
  const provenance = e?.provenance ?? primary?.provenance ?? 'live'

  // 2) A flagged reading is unverifiable — never a false "clear" (Rule #1).
  if (card.conditionLines.some((l) => l.confidence === 'flagged')) {
    return { ...UNVERIFIED, provenance }
  }

  // 3) A verified, unflagged reading → good to go. Summarised from the merged
  //    "Now" value when present; else the checked-count phrasing — it claims only
  //    what was verified, never a sky-state (F2), and never echoes a sourced
  //    per-line string (source lives in the Sources section, not here).
  if (e?.conditionValue ?? primary) {
    return { tone: 'go', lead: 'Good to go', detail: e?.conditionValue ?? checkedDetail(card), provenance }
  }

  // 4) No usable reading. An explicit checked-clear silence is a real positive —
  //    spoken in the six-state vocabulary ("checked — nothing to flag"), never a
  //    sky-word; the honest default (not-fetched / no-data / stale) is an
  //    unverified nudge.
  if (card.conditionSilence?.state === 'checked-clear') {
    return { tone: 'go', lead: 'Good to go', detail: 'checked — nothing to flag', provenance: 'live' }
  }
  return { ...UNVERIFIED, provenance }
}
