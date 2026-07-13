/**
 * Splits a feed's card warnings into one feed-level banner + the set of shared
 * texts each card should stop re-RENDERING (report finding #1): a region-wide
 * NWS product duplicated verbatim on most cards was a full-color wall that
 * pushed distance off a 390px screen. Hoisting is presentation only — it never
 * touches ranking or drops a fact (Rule #2, R6).
 *
 * Load-bearing shape (F1, ux-review 2026-07): this module returns a *rendering
 * suppression set*, never a rewritten card. An earlier version handed Home a
 * warnings-stripped card copy, and the card's verdict — derived from
 * `card.warnings` — flipped to "Good to go" under an active regional alert
 * while Detail (full card) said "Caution": the same trail, two verdicts, the
 * single worst failure mode for a trust-under-stress product. Every verdict
 * and accessible-name consumer must keep reading the FULL card; only the
 * duplicate warning *block* rendering is suppressed.
 */
import type { CardVM, WarningVM } from './vm'

/** NWS-style product severity, parsed from the human-readable text (the API
 *  sends no structured severity field) — Warning > Watch > Advisory > other. */
export function warningSeverity(text: string): number {
  if (/warning/i.test(text)) return 3
  if (/watch/i.test(text)) return 2
  if (/advisory/i.test(text)) return 1
  return 0
}

// A warning counts as region-wide once at least two cards carry it AND it
// covers a majority of the feed — coincidence on a single card (or a 1-card
// feed) never gets hoisted away from the card that actually has it.
const SHARED_MIN_CARDS = 2
const SHARED_MIN_SHARE = 0.5

export interface FeedWarnings {
  /** The region-wide alert(s), one per hazard kind, ranked by severity. */
  banner: WarningVM[]
  /**
   * Texts stated once at feed level, which a card's warning BLOCK should not
   * re-render. Rendering-only: the warnings themselves stay on the card VM, so
   * the verdict and the accessible name still speak them (F1).
   */
  sharedTexts: ReadonlySet<string>
}

/**
 * Hoist any warning shared across a majority of cards to the banner. When two
 * near-identical shared alerts of the same `kind` both qualify (an Extreme
 * Heat Warning and a Heat Advisory, say), only the higher-severity one
 * survives in the banner — the lower one is suppressed everywhere rather than
 * stacked (it still counts as shared, so no card re-renders it as its own).
 */
export function splitFeedWarnings(cards: CardVM[]): FeedWarnings {
  const total = cards.length
  if (total === 0) return { banner: [], sharedTexts: new Set() }

  const byText = new Map<string, { warning: WarningVM; count: number }>()
  for (const card of cards) {
    const seenOnCard = new Set<string>()
    for (const w of card.warnings) {
      if (seenOnCard.has(w.text)) continue
      seenOnCard.add(w.text)
      const entry = byText.get(w.text)
      if (entry) entry.count += 1
      else byText.set(w.text, { warning: w, count: 1 })
    }
  }

  const sharedTexts = new Set(
    [...byText.entries()]
      .filter(([, v]) => v.count >= SHARED_MIN_CARDS && v.count / total >= SHARED_MIN_SHARE)
      .map(([text]) => text),
  )

  // Deliberate trade-off (review M2, accepted): one banner slot per kind means a
  // second DISTINCT shared hazard of the same kind (or a severity tie) loses its
  // banner sentence. The fact is never dropped — it stays in every affected
  // card's verdict count ("+N more"), its accessible name, and Detail's warning
  // block (which renders full sentences for non-spoken warnings) — but the feed
  // shows one sentence per kind by design: the banner is a calm top slot, not a
  // stack.
  const bestByKind = new Map<string, WarningVM>()
  for (const text of sharedTexts) {
    const w = byText.get(text)!.warning
    const current = bestByKind.get(w.kind)
    if (!current || warningSeverity(w.text) > warningSeverity(current.text)) bestByKind.set(w.kind, w)
  }
  const banner = [...bestByKind.values()].sort((a, b) => warningSeverity(b.text) - warningSeverity(a.text))

  return { banner, sharedTexts }
}
