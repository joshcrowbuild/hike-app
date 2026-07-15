/**
 * Splits a feed's per-card condition signals by their TRUE scope
 * (ux-review-conditions-2026-07 F3/F9a): region-scope facts — one NWS zone's
 * weather, one AirNow region's reading or outage, a fire/closure sweep — were
 * repeated verbatim on every card (~35% of each card's height), teaching the
 * eye to skip the condition block entirely, which is exactly where the one
 * card that differs will someday put its warning. Facts shared verbatim across
 * most of the feed are stated ONCE in the feed-level conditions ribbon, with
 * their source + stamp; cards keep only their per-trail deltas.
 *
 * Same posture as `feedWarnings` (F1): this returns rendering suppression
 * KEYS, never a rewritten card — the verdict and Detail keep reading the full
 * CardVM. Only verbatim-identical signals hoist (text + source + confidence +
 * provenance for a line; kind + state + source + age + detail for a state):
 * choosing a "representative" value for readings that differ would average
 * away a real microclimate delta, and hoisting a fresher stamp over a card
 * whose own answer is older would fabricate freshness. Presentation only —
 * never a ranking input, never a dropped fact (Rule #2, R6).
 */
import type { CardVM, ConditionStatusVM, LineVM } from './vm'

// A signal counts as region-scope once at least two cards carry it AND a
// STRICT majority of the feed does. Strictness is load-bearing (self-review
// finding M1): a card carries exactly one disposition per kind and one reading
// per fact, so an exact-half tie (2 cards fire checked-clear + 2 cards fire
// couldn't-verify) would, at >= 0.5, hoist BOTH — a self-contradicting ribbon
// hanging its checked-clear over the cards whose probe actually failed. Two
// variants of one partitioned signal can never BOTH exceed a strict half.
const SHARED_MIN_CARDS = 2
const SHARED_MIN_SHARE = 0.5

/** NUL can't occur in rendered copy, so joined fields can never collide the way
 *  a plain space join would ("a b"+"c" vs "a"+"b c"). */
const SEP = '\u0000'

/** Identity of one condition line for hoisting — the full fact, not just its text. */
export const lineKey = (l: LineVM): string =>
  [l.text, l.source, l.confidence, l.provenance].join(SEP)

/** Identity of one per-kind disposition — verbatim, including its stamp + detail. */
export const conditionStateKey = (s: ConditionStatusVM): string =>
  [s.kind, s.state, s.source ?? '', s.checkedAgo ?? '', s.detail ?? ''].join(SEP)

/** The states a card renders as its silent compact summary — the only ones the
 *  ribbon may hoist. Value-bearing states (present / stale-degraded) ride their
 *  condition LINES, which hoist by line identity instead. */
const SILENT_STATES: ReadonlySet<ConditionStatusVM['state']> = new Set([
  'no-hazard',
  'no-data',
  'unavailable',
  'not-fetched',
])

export interface FeedConditions {
  /** Region-shared condition readings, stated once at feed level (first-seen order). */
  sharedLines: LineVM[]
  /** Region-shared silent dispositions — the three silences stay distinct in rendering. */
  sharedStates: ConditionStatusVM[]
  /** Suppression keys (`lineKey`) for the card's own line rendering. */
  sharedLineKeys: ReadonlySet<string>
  /** Suppression keys (`conditionStateKey`) for the card's compact state rendering. */
  sharedStateKeys: ReadonlySet<string>
}

const EMPTY: FeedConditions = {
  sharedLines: [],
  sharedStates: [],
  sharedLineKeys: new Set(),
  sharedStateKeys: new Set(),
}

/** Tally distinct keys per card (a card votes once per key), then keep the keys
 *  shared across a strict feed majority, in first-seen order. */
function shared<T>(cards: CardVM[], pick: (c: CardVM) => T[], key: (t: T) => string): T[] {
  const total = cards.length
  const byKey = new Map<string, { item: T; count: number }>()
  for (const card of cards) {
    const seenOnCard = new Set<string>()
    for (const item of pick(card)) {
      const k = key(item)
      if (seenOnCard.has(k)) continue
      seenOnCard.add(k)
      const entry = byKey.get(k)
      if (entry) entry.count += 1
      else byKey.set(k, { item, count: 1 })
    }
  }
  return [...byKey.values()]
    .filter((v) => v.count >= SHARED_MIN_CARDS && v.count / total > SHARED_MIN_SHARE)
    .map((v) => v.item)
}

/**
 * Defence-in-depth behind the strict-majority rule (M1): if more than one
 * distinct disposition of the SAME kind ever qualifies (only reachable if a
 * payload carried duplicate kind entries — the partition assumption broken),
 * hoist NONE of that kind. A ribbon must never state two truths about one
 * kind while the cards that disagree are silenced; the per-card rows are the
 * honest rendering of a conflict.
 */
function dropConflictingKinds(states: ConditionStatusVM[]): ConditionStatusVM[] {
  const kindsSeen = new Map<string, number>()
  for (const s of states) kindsSeen.set(s.kind, (kindsSeen.get(s.kind) ?? 0) + 1)
  return states.filter((s) => kindsSeen.get(s.kind) === 1)
}

export function splitFeedConditions(cards: CardVM[]): FeedConditions {
  if (cards.length === 0) return EMPTY
  const sharedLines = shared(cards, (c) => c.conditionLines, lineKey)
  const sharedStates = dropConflictingKinds(
    shared(cards, (c) => (c.conditions ?? []).filter((s) => SILENT_STATES.has(s.state)), conditionStateKey),
  )
  return {
    sharedLines,
    sharedStates,
    sharedLineKeys: new Set(sharedLines.map(lineKey)),
    sharedStateKeys: new Set(sharedStates.map(conditionStateKey)),
  }
}

/**
 * The value shared by at least two items — collapse-when-agree,
 * expand-when-diverge (binding decision 2, Epic 045 S1 AC-1.4/1.5): a block,
 * compact group, or section states this value ONCE instead of once per item;
 * an item whose value diverges still renders its own (never silently
 * dropped). A single item, or a fully-divergent set (every value distinct),
 * yields no shared value — nothing is claimed as "the" answer unless at least
 * two items actually agree, so that set keeps its honest, unchanged per-item
 * display. Shared by `ConditionStates` (the freshness stamp/compact-group age,
 * AC-1.4/A4) and `Detail`'s Sources section (the descriptor note, A5) — one
 * collapse rule, not three copies of it.
 */
export function sharedAmong(values: (string | undefined)[]): string | undefined {
  const counts = new Map<string, number>()
  for (const v of values) {
    if (!v) continue
    counts.set(v, (counts.get(v) ?? 0) + 1)
  }
  let best: string | undefined
  let bestCount = 0
  for (const [v, count] of counts) {
    if (count > bestCount) {
      best = v
      bestCount = count
    }
  }
  return bestCount >= 2 ? best : undefined
}

/**
 * The recognizable short provider name for a source label — the leading
 * whitespace-delimited token ("NWS api.weather.gov · single authoritative
 * source (…)" → "NWS"; "NWS" (already short) → "NWS", unchanged). A TS mirror
 * of `provider_short` in `orchestration/present.py`/`engine.py` (binding
 * decision 1, Epic 045 S1 AC-1.2): the fold below must compare a shared
 * identity both a `LineVM` (which carries the FULL label in `source`) and a
 * `ConditionStatusVM` (which carries the SHORT name, `engine.py`'s
 * `provider_short(fact.source)`) can produce, never widen the status side to
 * the full label (that would re-bloat the condition row).
 */
export const providerShort = (source: string): string => {
  const [first] = source.trim().split(/\s+/)
  return first || source
}

/**
 * Detail's per-kind coverage row for a `present`/`stale-degraded` kind carries
 * no human-readable VALUE of its own — only the sourced fact's disposition
 * (state/source/age). The prose in `card.conditionLines` (e.g. "Sunny 90°F")
 * is that same fact's value, just shaped as a sentence instead of a table
 * cell. Rendering both was Finding 4/7 (ux-review 2026-07): the commitment
 * view stated every condition TWICE, once as prose and again as a table row —
 * redundant, and the two framed the SAME fact differently ("Likely: AQI 45"
 * hedged in prose vs. "✓ reported" confident in the table).
 *
 * The fix folds the line's value into its row instead of dropping either
 * representation. There is no explicit per-line `kind` on the wire (this stays
 * client-side rather than adding one — presentation only, Rule #2), but a
 * `present`/`stale-degraded` row and its line both come from the SAME answered
 * fact, so they share a provider identity — matched here by the SHORT provider
 * name both sides can produce (`providerShort(line.source) === status.source`,
 * Epic 045 S1 AC-1.2; A1 found this inert on live data because a naive
 * `line.source === status.source` compares the line's FULL label against the
 * status's SHORT name, which never matches). One line consumed per row
 * (`claimed` exhausts a matched line so a repeated source never fans one
 * line's value to every row that shares it).
 */
export function foldLineValue(
  status: ConditionStatusVM,
  lines: LineVM[],
  claimed: Set<LineVM>,
): LineVM | undefined {
  if (status.state !== 'present' && status.state !== 'stale-degraded') return undefined
  const match = lines.find((l) => !claimed.has(l) && providerShort(l.source) === status.source)
  if (match) claimed.add(match)
  return match
}

/**
 * The Rule #1 safety net for the Finding 4/7 merge: runs the exact same
 * source-matching claim `ConditionStates` performs (so the two can never
 * disagree about what got folded) and returns whichever lines NO row claimed —
 * never expected from today's backend (which builds `conditions` and `lines`
 * from the same per-kind loop), but a divergent/older payload must still
 * surface its fact somewhere rather than have the merge silently drop it.
 */
export function unclaimedLines(conditions: ConditionStatusVM[], lines: LineVM[]): LineVM[] {
  const claimed = new Set<LineVM>()
  for (const status of conditions) foldLineValue(status, lines, claimed)
  return lines.filter((l) => !claimed.has(l))
}
