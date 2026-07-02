/**
 * Splits a feed's card warnings into one feed-level banner + per-card leftovers
 * (report finding #1): a region-wide NWS product duplicated verbatim on most
 * cards was a full-color wall that pushed distance off a 390px screen. Hoisting
 * it once, and keeping only the trail-specific deltas per card, is presentation
 * only — it never touches ranking or drops a fact (Rule #2, R6).
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
  /** Each card's warnings with the banner-hoisted text removed. */
  perCard: Map<string, WarningVM[]>
}

/**
 * Hoist any warning shared across a majority of cards to the banner. When two
 * near-identical shared alerts of the same `kind` both qualify (an Extreme
 * Heat Warning and a Heat Advisory, say), only the higher-severity one
 * survives — the lower one is dropped everywhere rather than stacked.
 */
export function splitFeedWarnings(cards: CardVM[]): FeedWarnings {
  const total = cards.length
  const perCard = new Map<string, WarningVM[]>()
  if (total === 0) return { banner: [], perCard }

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

  const bestByKind = new Map<string, WarningVM>()
  for (const text of sharedTexts) {
    const w = byText.get(text)!.warning
    const current = bestByKind.get(w.kind)
    if (!current || warningSeverity(w.text) > warningSeverity(current.text)) bestByKind.set(w.kind, w)
  }
  const banner = [...bestByKind.values()].sort((a, b) => warningSeverity(b.text) - warningSeverity(a.text))

  for (const card of cards) {
    perCard.set(
      card.id,
      card.warnings.filter((w) => !sharedTexts.has(w.text)),
    )
  }

  return { banner, perCard }
}
