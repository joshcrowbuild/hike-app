/**
 * The one-line trail character + a derived difficulty estimate (product voice,
 * 2026-07-03). Both are DERIVED from the same verified data a card already
 * carries — its mapped geometry, its 3DEP elevation profile, its summit marker —
 * so each is a *summary of sourced facts*, never a new qualitative claim
 * (source-or-silence, Rule #1). We never invent texture ("exposed rock", "clean
 * summit reward"): if the data doesn't back a clause, the clause is dropped and
 * the line simply says less. Both are presentation only — neither touches
 * ranking (Rule #2). This mirrors `deriveVerdict`: a pure function over the VM.
 */
import { deriveRouteShape, isDrawableRoute, mappedLengthMeters, metersToFeet, metersToMiles } from './geo'
import { deriveVerdict } from './verdict'
import type { CardVM, Provenance } from './vm'

/** Below this the climb isn't worth stating as a number (rounding noise). */
const CLIMB_FLOOR_FT = 50

// ---- Feature 1: the honest one-line summary -------------------------------

/**
 * A single honest sentence describing a trail's physical character, or `null`
 * when there isn't enough verified data to say anything (the card then shows
 * nothing rather than padding). Built ONLY from: mapped length, route shape
 * (loop/out-and-back from the geometry endpoints), profile climb, whether a
 * summit is marked, and — only when TODAY's conditions verify as clear and live
 * — a "clear today" tail. Conditions are otherwise the Verdict's job, shown
 * right above; a flagged/absent reading never becomes a false all-clear here.
 */
export function deriveSummary(card: CardVM): string | null {
  const miles = resolveMiles(card)
  const gainFeet = resolveGainFeet(card)
  const lossFeet = resolveLossFeet(card)
  const shape = deriveRouteShape(card.geo?.geometry ?? null)
  const hasSummit = card.geo?.summit != null

  // "flat" is only honest when BOTH directions barely move — a one-way line that
  // only descends (gain≈0 but real loss) is NOT flat, it's a descent, so we stay
  // silent on grade there rather than mislabel it.
  const flat = gainFeet != null && lossFeet != null && gainFeet < CLIMB_FLOOR_FT && lossFeet < CLIMB_FLOOR_FT
  const statedClimb = !flat && gainFeet != null && gainFeet >= CLIMB_FLOOR_FT ? gainFeet : null

  // Nothing verified worth a sentence → say nothing (Rule #1).
  if (miles == null && statedClimb == null && !hasSummit && !flat) return null

  const subject: string[] = []
  if (flat) subject.push('flat')
  if (miles != null) subject.push(`${formatMiles(miles)}-mile`)
  subject.push(shape ?? 'trail')
  const subjectText = subject.join(' ')

  let predicate = ''
  if (statedClimb != null && hasSummit) predicate = `, climbing ${statedClimb.toLocaleString()} ft to a summit`
  else if (statedClimb != null) predicate = `, climbing ${statedClimb.toLocaleString()} ft`
  else if (hasSummit) predicate = ' to a summit'

  const tail = clearConditionTail(card)

  return `${indefiniteArticle(subjectText)} ${subjectText}${predicate}${tail}.`
}

/**
 * A " — clear today" tail, added ONLY when the card's own verdict is a live
 * "good to go" (`deriveVerdict` returns `go` only from a verified, unflagged
 * reading). Any hazard, flagged, or non-live signal → no tail: the trail is
 * never dressed as clear when it isn't (Rule #1), and sample data wears its
 * "sample" tag on the Verdict instead of a fake "today".
 */
function clearConditionTail(card: CardVM): string {
  const v = deriveVerdict(card)
  return v.tone === 'go' && v.provenance === 'live' ? ' — clear today' : ''
}

// ---- Feature 2: the derived difficulty estimate ---------------------------

export type DifficultyBand = 'easy' | 'moderate' | 'strenuous' | 'very-strenuous'

export interface DifficultyVM {
  band: DifficultyBand
  /** Human label, e.g. "Moderate". */
  label: string
  /** The numeric rating it came from — inspectable, so the estimate is transparent. */
  score: number
  /** Provenance of the underlying figures, so a sample estimate demotes/tags (R1). */
  provenance: Provenance
}

const BAND_LABEL: Record<DifficultyBand, string> = {
  easy: 'Easy',
  moderate: 'Moderate',
  strenuous: 'Strenuous',
  'very-strenuous': 'Very strenuous',
}

/**
 * The documented rating formula (Shenandoah NPS style): `√(2 · climb_ft ·
 * miles)`, banded easy → very-strenuous. It is an ESTIMATE, labeled as such on
 * the surface, derived transparently from distance × climb — the same two
 * verified figures the card already shows. Deliberately NOT a ranking input
 * (Rule #2): the caller renders it, the engine never sorts by it.
 *
 * `miles` is already the round-trip figure for a confidently-detected
 * out-and-back (`resolveMiles`, Josh's call 2026-07-03) — the real distance
 * walked. `climb_ft` remains the profile's ONE-WAY figure, though: the return
 * leg of an out-and-back re-climbs whatever it just descended, so this still
 * under-rates one-directional descents (a gain≈0 line reads "Easy"). We take
 * the sourced climb figure verbatim rather than infer a round-trip climb —
 * open for Josh to decide.
 */
export function deriveDifficulty(card: CardVM): DifficultyVM | null {
  const miles = resolveMiles(card)
  const gainFeet = resolveGainFeet(card)
  // Null-safe: with no verified climb OR no length, we don't estimate at all.
  if (miles == null || gainFeet == null || miles <= 0) return null
  const score = Math.sqrt(2 * gainFeet * miles)
  const band: DifficultyBand = score < 50 ? 'easy' : score < 100 ? 'moderate' : score < 150 ? 'strenuous' : 'very-strenuous'
  return { band, label: BAND_LABEL[band], score: Math.round(score), provenance: provenanceOf(card) }
}

// ---- shared resolution over the VM ----------------------------------------

/**
 * Trail length in miles: the curated `distanceMiles` when present (mock), else
 * the honest per-segment mapped length of the live geometry — NEVER the API's
 * `distanceMi`, which is the crow-flies origin→trailhead hop, not the trail.
 * This is the ONE geometry SSOT for every distance-shaped fact a card or
 * Detail shows (H4/F7, ux-review 2026-07 — `cardParts.DecisionFacts` and this
 * module's own `deriveSummary`/`deriveDifficulty` all resolve through it), so
 * the Character line and the Distance/Duration facts can never disagree about
 * how long the trail is.
 *
 * For a confidently-detected out-and-back (Josh's call, 2026-07-03) this is the
 * ROUND-TRIP figure — 2× the one-way path length — because that's what the
 * hiker actually walks. A loop's path length already IS the full walk, so it is
 * never doubled; when the shape can't be read (no geometry) we stay
 * conservative and report the one-way figure rather than guess.
 */
export function resolveMiles(card: CardVM): number | null {
  const oneWay = resolveOneWayMiles(card)
  if (oneWay == null) return null
  return isConfidentOutAndBack(card) ? oneWay * 2 : oneWay
}

/** Below this, an estimate's implied pace is no longer a plausible hike —
 *  the two figures describing it (distance vs. duration) don't hold together,
 *  most often because they were read off two different geometries (H4/F7). */
const MIN_PLAUSIBLE_PACE_MPH = 0.5
const MAX_PLAUSIBLE_PACE_MPH = 4

/**
 * Duration estimate (minutes), resolved over the SAME geometry `resolveMiles`
 * used for the Distance fact (H4/F7, ux-review 2026-07): the backend's
 * `estimatedDurationMin` is a Naismith integral over the profile's own
 * samples, which — like the mapped geometry length — cover only the ONE-WAY
 * path for an out-and-back. Doubling it here for a confident out-and-back
 * mirrors `resolveMiles`'s own doubling, so the two facts always describe the
 * same walk; a loop's estimate already covers its one full circuit and is
 * never doubled.
 *
 * As a backstop, a pace outside `[MIN_PLAUSIBLE_PACE_MPH, MAX_PLAUSIBLE_PACE_MPH]`
 * signals the two figures don't hold together (e.g. a stale/mismatched
 * profile) — the honest move is to drop the fact rather than publish a 13 mph
 * "hike" (Rule #1), so this returns `null` rather than a number nobody should
 * trust.
 */
export function resolveDurationMinutes(card: CardVM): number | null {
  const oneWayMin = card.geo?.elevationProfile?.estimatedDurationMin
  if (oneWayMin == null) return null
  const minutes = isConfidentOutAndBack(card) ? oneWayMin * 2 : oneWayMin
  if (minutes <= 0) return null
  const miles = resolveMiles(card)
  if (miles != null) {
    const paceMph = miles / (minutes / 60)
    if (paceMph < MIN_PLAUSIBLE_PACE_MPH || paceMph > MAX_PLAUSIBLE_PACE_MPH) return null
  }
  return minutes
}

function resolveOneWayMiles(card: CardVM): number | null {
  const e = card.enrichment
  if (e?.distanceMiles != null) return e.distanceMiles
  const g = card.geo?.geometry ?? null
  return isDrawableRoute(g) ? metersToMiles(mappedLengthMeters(g)) : null
}

function isConfidentOutAndBack(card: CardVM): boolean {
  return deriveRouteShape(card.geo?.geometry ?? null) === 'out-and-back'
}

/** Climb in feet: curated `ascentFeet` when present, else the live 3DEP profile. */
function resolveGainFeet(card: CardVM): number | null {
  const e = card.enrichment
  if (e?.ascentFeet != null) return e.ascentFeet
  const gain = card.geo?.elevationProfile?.totalGainMeters
  return gain != null ? Math.round(metersToFeet(gain)) : null
}

/** Descent in feet, from the live profile only (curated records carry no loss). */
function resolveLossFeet(card: CardVM): number | null {
  const loss = card.geo?.elevationProfile?.totalLossMeters
  return loss != null ? Math.round(metersToFeet(loss)) : null
}

function provenanceOf(card: CardVM): Provenance {
  return card.enrichment?.provenance ?? 'live'
}

/** One decimal, dropping a trailing `.0` so "3.0" reads "3" and "1.15" reads "1.2". */
function formatMiles(miles: number): string {
  const rounded = Math.round(miles * 10) / 10
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1)
}

/**
 * "A" vs "An" for the subject phrase — by the spoken sound of its first word.
 * Numbers matter: "8-mile" → "an" (eight), "11-/18-mile" too; and among our
 * words only "out-and-back" opens on a vowel sound.
 */
function indefiniteArticle(subject: string): string {
  const first = subject.split(' ')[0]
  const digits = first.match(/^\d+/)
  if (digits) {
    const n = Number(digits[0])
    const vowelSound = n === 8 || n === 11 || n === 18 || (n >= 80 && n < 90)
    return vowelSound ? 'An' : 'A'
  }
  return /^out-and-back/.test(first) ? 'An' : 'A'
}
