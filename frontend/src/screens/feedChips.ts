/**
 * Presentation mapping: feed/card view-models → `ConditionChipModel[]` for the
 * scannable conditions strip (frame-conditions-wave §3). Pure, screens-owned
 * (the data layer is frozen this wave): it only READS `feedConditions.ts`'s
 * hoist + fold helpers, never mutates a VM.
 *
 * Two producers:
 *  - `feedCurrentChips` — the This-feed card's right-now zone: the
 *    region-shared current readings (`splitFeedConditions`), values + silences.
 *  - `detailConditionChips` — Detail's per-kind strip for ONE trail.
 * Both share the coverage→chip rules so the two surfaces can never disagree.
 */
import { foldLineValue, lineKey, providerShort, splitFeedConditions } from '../data/feedConditions'
import type { CardVM, ConditionStatusVM, HeldBackVM, LineVM } from '../data/vm'
import type { ConditionChipModel, ConditionTier, ReceiptModel } from '../design/contracts'
import { conditionKindLabels } from './ConditionStates'

/**
 * Cleans raw wire strings into human copy (gauge / permit phrases) — relocated
 * from the retired EvidencePanel so the chip value + Detail receipt read the
 * same cleaned text.
 */
export function cleanEvidenceBody(body: string): string {
  if (body.includes('flow reading unavailable at')) return 'No gauge near this route'
  if (body.includes('Permit info not checked')) return 'None required here'
  return body
}

/**
 * The terse chip value — the leading reading of a possibly-compound line
 * ("54°F · breezy · clear" → "54°F"), so the strip stays scannable. The full
 * line stays reachable (Detail's receipt / the card's own copy); nothing is
 * fabricated — an empty lead falls back to the whole cleaned string.
 */
export function chipValueText(raw: string): string {
  const cleaned = cleanEvidenceBody(raw)
  const lead = cleaned.split(' · ')[0]?.trim()
  return lead || cleaned
}

/** A checked-clear reading's value word, per kind (mock: "open" / "none" / "clear"). */
function clearWord(kind: string): string {
  if (kind === 'closures') return 'open'
  if (kind === 'permits') return 'none'
  return 'clear'
}

/** A present (sourced-fact) reading's value word when no value line was folded —
 *  never "open"/"clear" for a present closure (that would flip the meaning). */
function presentWord(kind: string): string {
  if (kind === 'closures') return 'closed'
  if (kind === 'permits') return 'required'
  return conditionKindLabels[kind] ?? kind
}

/**
 * Corroboration in plain words for the receipt (Q6). Derived from the live
 * source count (Epic 026a `sources`), which is populated ONLY on live lines —
 * a mock/sample line has no count and reads as "single source", never a
 * fabricated "N agree".
 */
function confidenceText(line: LineVM | undefined): string | undefined {
  if (!line) return undefined
  const n = line.sources?.length ?? 0
  return n >= 2 ? `${n} sources agree` : 'single source'
}

/**
 * A best-effort kind for a region-shared value line, whose `LineVM` carries no
 * explicit kind on the wire. Used only to choose the chip's glyph + match a
 * warning tint; the value + source shown are always the real ones. Preferred
 * source is the fold-pairing across the feed (below); this is the fallback.
 */
export function inferKindFromSource(source: string): string {
  const s = source.toLowerCase()
  if (s.includes('airnow') || s.includes('aqi')) return 'air'
  if (s.includes('firms') || s.includes('fire')) return 'fire'
  if (s.includes('usgs') || s.includes('streamflow') || s.includes('flow')) return 'water'
  if (s.includes('nps') || s.includes('closure')) return 'closures'
  // The real backend constant is "Recreation.gov RIDB" — 'rec.gov' alone does
  // NOT match it (review CRITICAL: a permits line fell through to 'weather',
  // wrong glyph + a blocked permit tint silently skipped).
  if (s.includes('recreation.gov') || s.includes('ridb') || s.includes('rec.gov') || s.includes('permit'))
    return 'permits'
  return 'weather'
}

/**
 * Per-kind warning tier across a set of cards (Q5/Q7): the max severity of any
 * warning owning that kind. `blocked` wins; an absent `severity` grades as
 * `headsUp` (never louder than the backend graded it, Law 6).
 */
export function warningTierByKind(cards: CardVM[]): Map<string, ConditionTier> {
  const map = new Map<string, ConditionTier>()
  for (const card of cards) {
    for (const w of card.warnings) {
      const tier: ConditionTier = w.severity === 'blocked' ? 'blocked' : 'headsUp'
      if (map.get(w.kind) === 'blocked') continue
      if (tier === 'blocked' || !map.has(w.kind)) map.set(w.kind, tier)
    }
  }
  return map
}

/** The value line each present/stale condition kind claims, keyed by line identity,
 *  so a region-shared value line can recover its kind + freshness. */
function lineKindInfo(cards: CardVM[]): Map<string, { kind: string; stale: boolean }> {
  const info = new Map<string, { kind: string; stale: boolean }>()
  for (const card of cards) {
    const claimed = new Set<LineVM>()
    for (const status of card.conditions ?? []) {
      if (status.state !== 'present' && status.state !== 'stale-degraded') continue
      const matched = foldLineValue(status, card.conditionLines, claimed)
      if (matched) info.set(lineKey(matched), { kind: status.kind, stale: status.state === 'stale-degraded' })
    }
  }
  return info
}

/** One silent disposition (no value line) → its chip. */
function silentChip(status: ConditionStatusVM, tier: ConditionTier): ConditionChipModel {
  if (status.state === 'no-hazard') {
    return {
      kind: status.kind,
      valueText: clearWord(status.kind),
      state: 'fresh',
      tier,
      receipt: status.source ? { source: status.source, ageText: status.checkedAgo } : undefined,
    }
  }
  // no-data | unavailable | not-fetched — probed/uncovered, never a guessed value.
  return {
    kind: status.kind,
    valueText: '—',
    state: 'unavailable',
    tier,
    receipt: status.state === 'no-data' && status.source ? { source: status.source } : undefined,
  }
}

/**
 * The right-now zone's chips: the region-shared current readings hoisted by
 * `splitFeedConditions`. Value lines render fresh (or stale, from their paired
 * disposition); silences render their own honest state. `pending` is the
 * caller's concern (phase 2 in flight) — this maps only resolved data.
 */
export function feedCurrentChips(cards: CardVM[]): ConditionChipModel[] {
  const { sharedLines, sharedStates } = splitFeedConditions(cards)
  const warnTier = warningTierByKind(cards)
  const info = lineKindInfo(cards)
  const chips: ConditionChipModel[] = []

  for (const line of sharedLines) {
    const paired = info.get(lineKey(line))
    const kind = paired?.kind ?? inferKindFromSource(line.source)
    const stale = paired?.stale ?? false
    const receipt: ReceiptModel = {
      source: providerShort(line.source),
      ageText: line.age,
      confidenceText: confidenceText(line),
    }
    chips.push({
      kind,
      valueText: chipValueText(line.body ?? line.text),
      state: stale ? 'stale' : 'fresh',
      tier: warnTier.get(kind) ?? 'clear',
      ageText: stale ? line.age : undefined,
      receipt,
    })
  }

  for (const status of sharedStates) {
    chips.push(silentChip(status, warnTier.get(status.kind) ?? 'clear'))
  }

  return chips
}

/** One trail's per-kind chip (Detail). Present/stale claim their value line; the
 *  four silences render their own honest state. */
function detailChip(
  status: ConditionStatusVM,
  line: LineVM | undefined,
  tier: ConditionTier,
): ConditionChipModel {
  if (status.state === 'present' || status.state === 'stale-degraded') {
    const stale = status.state === 'stale-degraded'
    const rawValue = line?.body ?? line?.text
    return {
      kind: status.kind,
      valueText: rawValue ? chipValueText(rawValue) : presentWord(status.kind),
      state: stale ? 'stale' : 'fresh',
      tier,
      ageText: stale ? status.checkedAgo : undefined,
      receipt: {
        source: status.source ?? providerShort(line?.source ?? ''),
        ageText: status.checkedAgo ?? line?.age,
        confidenceText: confidenceText(line),
      },
    }
  }
  return silentChip(status, tier)
}

/**
 * Detail's per-kind conditions strip for ONE trail: every `card.conditions`
 * disposition, folding its matching value line (`foldLineValue`, same rule the
 * feed hoist uses). Tinted by this trail's own warnings (Q5). Any value line no
 * disposition claimed (an older/mock payload with lines but no `conditions`) is
 * appended as its own fresh chip so a real reading is never silently dropped
 * (Rule #1). Empty only when the card carries neither — the caller renders
 * nothing, never a fabricated row.
 */
export function detailConditionChips(card: CardVM): ConditionChipModel[] {
  const conditions = card.conditions ?? []
  const lines = card.conditionLines ?? []
  const warnTier = warningTierByKind([card])
  const claimed = new Set<LineVM>()

  const chips = conditions.map((status) => {
    // Mirror ConditionStates' fold so a present/stale row claims exactly one
    // value line; a warning tint (Q5) overrides only when a warning owns the kind.
    const line =
      status.state === 'present' || status.state === 'stale-degraded'
        ? foldLineValue(status, lines, claimed)
        : undefined
    return detailChip(status, line, warnTier.get(status.kind) ?? 'clear')
  })

  for (const line of lines) {
    if (claimed.has(line)) continue
    const kind = inferKindFromSource(line.source)
    chips.push({
      kind,
      valueText: chipValueText(line.body ?? line.text),
      state: 'fresh',
      tier: warnTier.get(kind) ?? 'clear',
      receipt: { source: providerShort(line.source), ageText: line.age, confidenceText: confidenceText(line) },
    })
  }

  return chips
}

/**
 * The blocked-day strip (live finding, the AQI-276 smoke day 2026-07-17):
 * when a hazard holds EVERY card back, the hoist above has no cards to read
 * and the strip would go empty exactly when it matters most — the reading
 * that emptied the feed vanished from the scan layer. Derive the blocking
 * readings from the held-back reasons themselves: one chip per kind, tinted
 * `blocked` (they ARE the barrier that emptied the feed), value = the terse
 * parenthetical when the reason carries one ("AQI 276"), else the cleaned
 * reason lead. Sourced receipt; held-back reasons carry no timestamp, so the
 * receipt shows the source alone rather than fabricating an age (§7.2).
 */
export function heldBackChips(heldBack: HeldBackVM[]): ConditionChipModel[] {
  const byKind = new Map<string, { text: string; source: string }>()
  for (const trail of heldBack)
    for (const r of trail.reasons) if (!byKind.has(r.kind)) byKind.set(r.kind, r)
  return Array.from(byKind.entries()).map(([kind, r]) => ({
    kind,
    valueText: parentheticalValue(r.text) ?? chipValueText(cleanEvidenceBody(r.text)),
    state: 'fresh',
    tier: 'blocked',
    receipt: { source: providerShort(r.source) },
  }))
}

/** "air quality hazardous (AQI 276)" → "AQI 276"; null when no terse paren exists. */
function parentheticalValue(text: string): string | null {
  const m = text.match(/\(([^)]{1,16})\)/)
  return m ? m[1] : null
}
