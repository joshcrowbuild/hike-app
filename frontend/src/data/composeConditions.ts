/**
 * Phase-1 feed × phase-2 patch → the composed feed (Epic 040 S3 AC-3.4).
 *
 * A pure transform with the D5 contract built in:
 *   - patches apply IN PLACE, keyed by card id — the phase-1 order is never
 *     changed (nothing reshuffles under the user's eyes);
 *   - a held-back id is REMOVED from the cards and disclosed on `heldBack`
 *     (the standard set-aside surface — a safety gate, not a demotion);
 *   - a card the patch doesn't cover keeps its honest phase-1 `not-fetched`
 *     silence — never a guessed disposition (Rule #1);
 *   - `conditionsPending` clears: the composed feed is the verified truth and
 *     is the ONLY shape `writeFeedCache`/`feedSnapshot` may persist (D4).
 *   - `regionConditions`/`personalizationDegraded` (frame-conditions-wave §5,
 *     Epic 056 S3 AC-3.2/3.3): the patch wins whenever it carries a value
 *     (including an explicit `null` — a real "unavailable" signal from
 *     phase 2), so a phase-1 shell's own value never survives past a phase-2
 *     answer; only a field the patch genuinely omits (`undefined`) falls
 *     back to whatever phase 1 already carried.
 */
import type { ConditionsPatchVM, FeedVM } from './vm'

export function composeConditions(phase1: FeedVM, patch: ConditionsPatchVM): FeedVM {
  const byId = new Map(patch.patches.map((p) => [p.id, p]))
  const removed = new Set(patch.heldBack.map((h) => h.id))
  return {
    ...phase1,
    cards: phase1.cards
      .filter((c) => !removed.has(c.id))
      .map((c) => {
        const p = byId.get(c.id)
        if (!p) return c
        return {
          ...c,
          conditionLines: p.conditionLines,
          // A patch entry without per-kind dispositions (a divergent payload)
          // keeps the card's own honest phase-1 states rather than blanking
          // them — never trade real silence for a guess (Rule #1).
          conditions: p.conditions ?? c.conditions,
          warnings: p.warnings,
          // The per-kind payload is now authoritative; the blanket fallback
          // (older-payload rendering) must not linger under real dispositions.
          conditionSilence: undefined,
        }
      }),
    heldBack: [...phase1.heldBack, ...patch.heldBack],
    conditionsPending: undefined,
    regionConditions: patch.regionConditions !== undefined ? patch.regionConditions : phase1.regionConditions,
    personalizationDegraded:
      patch.personalizationDegraded !== undefined ? patch.personalizationDegraded : phase1.personalizationDegraded,
  }
}
