/**
 * Pure copy derivation for the water answer (Epic 041) — no React, so the
 * pluralization, distance formatting, basis wording, and the seasonal hedge
 * are unit-tested once and the Detail surface stays thin.
 *
 * Honesty rules encoded here:
 * - The distance claim names its BASIS ("of the route" / "of the start") —
 *   `water_sources_near` measures from a point; route proximity was computed
 *   server-side and `basis` says which claim was actually earned.
 * - Corpus data, not a live probe: the note always hedges "not verified live"
 *   and never claims flow, let alone potability (Epic 035 Guard 2). No ingest
 *   timestamp exists on these nodes today, so none is shown (never fabricated).
 * - The answered-empty ('none-nearby') is a calm ANSWER, not a warning.
 */
import { metersToFeet, metersToMiles } from './geo'
import type { TrailWaterVM, WaterSourceVM } from './vm'

/** Canonical presentation order — springs first (the backpacking headline). */
const TYPE_ORDER = ['spring', 'drinking_water', 'water_tap', 'water_well'] as const

/** OSM category → noun, singular/plural. `drinking_water` stays visibly a
 *  CATEGORY noun ("drinking-water point"), never an adjective like "drinkable". */
const TYPE_NOUNS: Record<string, [string, string]> = {
  spring: ['spring', 'springs'],
  drinking_water: ['drinking-water point', 'drinking-water points'],
  water_tap: ['tap', 'taps'],
  water_well: ['well', 'wells'],
}

const FALLBACK_NOUN: [string, string] = ['water point', 'water points']

export function waterTypeNoun(type: string, count = 1): string {
  const [one, many] = TYPE_NOUNS[type] ?? FALLBACK_NOUN
  return count === 1 ? one : many
}

/**
 * "~650 ft" under ~1000 ft (rounded to 50 ft — these are map-derived
 * distances, not survey figures; false precision is the inverse honesty
 * failure), else "~0.4 mi" (one decimal).
 */
export function formatWaterDistance(meters: number): string {
  const feet = metersToFeet(meters)
  if (feet < 1000) {
    const rounded = Math.max(50, Math.round(feet / 50) * 50)
    return `~${rounded} ft`
  }
  return `~${metersToMiles(meters).toFixed(1)} mi`
}

/** "2 springs, 1 tap" — grouped by type in canonical order, unknown types last. */
export function summarizeWaterCounts(sources: WaterSourceVM[]): string {
  const counts = new Map<string, number>()
  for (const w of sources) counts.set(w.type, (counts.get(w.type) ?? 0) + 1)
  const known: string[] = []
  for (const t of TYPE_ORDER) {
    const n = counts.get(t)
    if (n) {
      known.push(`${n} ${waterTypeNoun(t, n)}`)
      counts.delete(t)
    }
  }
  for (const [t, n] of counts) known.push(`${n} ${waterTypeNoun(t, n)}`)
  return known.join(', ')
}

const basisWord = (basis: TrailWaterVM['basis']): string =>
  basis === 'route' ? 'the route' : 'the start'

/**
 * The effective state, folding an empty `sources` array into `none-nearby`
 * (Epic 046 S4 AC-4.3 / D4): an answered `'sources'` VM with zero sources is
 * the same fact as an explicit `none-nearby` and must render identically —
 * never a composed-but-empty headline (`summarizeWaterCounts` returns `''`
 * for an empty array, which otherwise leaves a leading-space fragment).
 * Checked once, before either string is composed, so the headline and the
 * note can never disagree about whether the answer is "none" or "some".
 */
function effectiveState(vm: TrailWaterVM): TrailWaterVM['state'] {
  return vm.sources.length === 0 ? 'none-nearby' : vm.state
}

/** The one answer line for the Detail facts area. No "Water" prefix — the row
 *  label (glyph + the word, DecisionItem-style) carries that exactly once. */
export function waterHeadline(vm: TrailWaterVM): string {
  const dist = formatWaterDistance(vm.radiusM)
  if (effectiveState(vm) === 'none-nearby') {
    return `No mapped water within ${dist} of ${basisWord(vm.basis)} — carry what you need.`
  }
  return `${summarizeWaterCounts(vm.sources)} within ${dist} of ${basisWord(vm.basis)}`
}

/** The one-line provenance hedge under the answer. */
export function waterNote(vm: TrailWaterVM): string {
  const from = vm.source || 'OpenStreetMap'
  const attribution = from === 'OSM' ? 'OpenStreetMap' : from
  if (effectiveState(vm) === 'none-nearby') {
    return `Checked against ${attribution}'s water mapping for this area — not verified live.`
  }
  const hasSpring = vm.sources.some((w) => w.type === 'spring')
  const hasSeasonalTag = vm.sources.some((w) => w.seasonal != null)
  const seasonal = hasSpring
    ? ' · springs may be seasonal'
    : hasSeasonalTag
      ? ' · some may be seasonal'
      : ''
  return `From ${attribution} — not verified live${seasonal}`
}

/** Accessible name + hover label for one map marker. */
export function waterMarkerLabel(w: WaterSourceVM, basis: TrailWaterVM['basis']): string {
  const noun = waterTypeNoun(w.type, 1)
  const label = noun.charAt(0).toUpperCase() + noun.slice(1)
  const named = w.name ? `${label} — ${w.name}` : label
  const seasonal = w.seasonal != null || w.type === 'spring' ? ', may be seasonal' : ''
  return `${named}, about ${formatWaterDistance(w.distanceM).replace('~', '')} from ${basisWord(basis)}${seasonal} · OSM`
}
