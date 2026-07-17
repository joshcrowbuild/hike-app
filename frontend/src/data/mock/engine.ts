/**
 * Mock curation engine — the quarantined throwaway. Everything here duplicates
 * server-side logic (Scout→Verifier→Curator) and is deletable wholesale once
 * `/plan` is authoritative; no screen imports it directly (only MockPlannerClient
 * does). It doubles as the test fixture set.
 *
 * Two corrections from the persona review live here, on purpose:
 *  - R2: readiness is NEVER a ranking penalty. `scoreTrail` has no readiness
 *    term; readiness is applied (when a reading exists) as a post-rank filter.
 *  - R6: Ruby's constraint is an explicit hard GATE with a reason, distinct
 *    from the soft `partyFit` taste term, so an excluded option can be disclosed
 *    ("set aside") rather than silently vanishing.
 */
import type { Trail, TuningState } from '../../types'
import type { ConditionStatusVM, RegionConditionsVM, WarningVM } from '../vm'
import { buildTrailGeo } from './geoFixtures'

/** Base trail records; the sample route + elevation profile is attached below. */
const SAMPLE_TRAILS: Omit<Trail, 'geo'>[] = [
  {
    id: 'stony-man',
    name: 'Stony Man Loop',
    area: 'Skyline Drive · Shenandoah',
    routeShape: 'Loop · Ridge overlook',
    archetype: 'ridge',
    placeCue: 'A high open ridge that earns its views fast.',
    detailCharacter: 'A short ridge outing with immediate orientation, exposed rock, and a clean summit reward.',
    distanceMiles: 3.7,
    ascentFeet: 1050,
    durationHours: '2–2.5 hr',
    effort: 'moderate',
    tags: ['ridge', 'views', 'short', 'classic'],
    conditionValue: '54°F · breezy · clear',
    freshness: 'Conditions 2h old.',
    fitBase: 'Short enough for a morning, with a big payoff for the climb.',
    reasons: {
      standard: 'Short climb, wide views — an easy yes for a half day.',
      seekShade: 'Exposed up top; better when it is cool than hot.',
      bigViews: 'The most view for the least walking here.',
      quieter: 'Go early and the overlook is still yours.',
    },
    practicalNote: 'Parking usually behaves best before mid-morning.',
    sources: ['NPS trail status', 'NWS point forecast'],
    drives: { frontRoyal: 28, luray: 32, charlottesville: 74, richmond: 135, duck: 288, nagsHead: 300, hatteras: 348, ocracoke: 372 },
    partyFit: { solo: 6, ruby: 5, friends: 4 },
    whenFit: { tomorrowMorning: 6, weekendMorning: 6, weekendAfternoon: 3, fullDay: 2 },
    effortFit: { easy: 1, moderate: 6, bigDay: 2 },
    promptTerms: ['ridge', 'views', 'short', 'classic'],
  },
  {
    id: 'whiteoak-canyon',
    name: 'Whiteoak Canyon Falls',
    area: 'Old Rag foothills · Shenandoah',
    routeShape: 'Out-and-back · Water + forest',
    archetype: 'waterfall',
    placeCue: 'A shaded creek climb that stays cool when everything else bakes.',
    detailCharacter: 'A shaded, creek-driven route with strong summer relief and a softer rhythm than the ridge hikes.',
    distanceMiles: 5.2,
    ascentFeet: 1420,
    durationHours: '3–4 hr',
    effort: 'moderate',
    tags: ['shade', 'water', 'forest', 'cooler'],
    conditionValue: '49°F · damp · creek running high',
    caution: 'Verify creek crossings — running high after rain.',
    freshness: 'Streamflow 48m old.',
    fitBase: 'Good with Ruby, and shaded the whole way up.',
    reasons: {
      standard: 'Steady shade and water — a reliable half day.',
      seekShade: 'The coolest option in today’s set.',
      bigViews: 'Trades big views for cover and creek.',
      quieter: 'Calms down past the first falls.',
    },
    practicalNote: 'Recent rain makes the creek feel more present than usual.',
    sources: ['USGS streamflow', 'NPS trail status', 'NWS point forecast'],
    drives: { frontRoyal: 52, luray: 29, charlottesville: 49, richmond: 118, duck: 296, nagsHead: 308, hatteras: 356, ocracoke: 380 },
    partyFit: { solo: 5, ruby: 6, friends: 4 },
    whenFit: { tomorrowMorning: 5, weekendMorning: 5, weekendAfternoon: 6, fullDay: 4 },
    effortFit: { easy: 2, moderate: 6, bigDay: 2 },
    promptTerms: ['shade', 'water', 'cool', 'forest', 'ruby'],
  },
  {
    id: 'old-rag',
    name: 'Old Rag Circuit',
    area: 'Syria · Shenandoah',
    routeShape: 'Circuit · Scramble + ridge',
    archetype: 'bigDay',
    placeCue: 'A full granite day with a scramble that commits you to the ridge.',
    detailCharacter: 'A longer, more committed outing with a clear sense of consequence and a stronger planning threshold.',
    distanceMiles: 9.4,
    ascentFeet: 2580,
    durationHours: '6–7.5 hr',
    effort: 'bigDay',
    tags: ['big day', 'scramble', 'views', 'iconic'],
    conditionValue: '51°F · gusty · dry rock',
    freshness: 'Permit info 1h old.',
    fitBase: 'A whole day on the mountain — plan around it, not into it.',
    reasons: {
      standard: 'The one to pick when the hike is the whole plan.',
      seekShade: 'Open rock and sun — not the cool choice.',
      bigViews: 'The biggest ridge payoff here, by a lot.',
      quieter: 'Popular and exposed; quiet it is not.',
    },
    practicalNote: 'Best when you have time for the full loop without rushing.',
    sources: ['NPS permit guidance', 'NWS point forecast'],
    drives: { frontRoyal: 64, luray: 43, charlottesville: 51, richmond: 120, duck: 304, nagsHead: 316, hatteras: 364, ocracoke: 388 },
    partyFit: { solo: 4, ruby: 0, friends: 6 },
    whenFit: { tomorrowMorning: 2, weekendMorning: 3, weekendAfternoon: 0, fullDay: 6 },
    effortFit: { easy: 0, moderate: 1, bigDay: 7 },
    promptTerms: ['big day', 'ridge', 'iconic', 'views'],
  },
  {
    id: 'dark-hollow',
    name: 'Dark Hollow Falls',
    area: 'Byrd Visitor Center · Shenandoah',
    routeShape: 'Out-and-back · Falls access',
    archetype: 'waterfall',
    placeCue: 'A quick walk down to falling water and back.',
    detailCharacter: 'A compact outing with immediate payoff and a useful fallback posture when the day wants something lighter.',
    distanceMiles: 1.6,
    ascentFeet: 440,
    durationHours: '1–1.5 hr',
    effort: 'easy',
    tags: ['easy', 'water', 'shade', 'short'],
    conditionValue: '52°F · still · misty near the falls',
    freshness: 'Trail status 3h old.',
    fitBase: 'Short and easy — leaves the rest of the day open.',
    reasons: {
      standard: 'The quick, grounded option when time is short.',
      seekShade: 'Short and shaded — fine for a warm afternoon.',
      bigViews: 'Water, not vistas — but it is the easy one.',
      quieter: 'Best early; it is small and fills up.',
    },
    practicalNote: 'Short enough to pair with a longer drive or other stops.',
    sources: ['NPS trail status', 'NWS point forecast'],
    drives: { frontRoyal: 54, luray: 31, charlottesville: 42, richmond: 112, duck: 292, nagsHead: 304, hatteras: 352, ocracoke: 376 },
    partyFit: { solo: 5, ruby: 6, friends: 3 },
    whenFit: { tomorrowMorning: 4, weekendMorning: 4, weekendAfternoon: 5, fullDay: 1 },
    effortFit: { easy: 7, moderate: 2, bigDay: 0 },
    promptTerms: ['short', 'water', 'shade', 'easy', 'ruby'],
  },
  {
    id: 'hawksbill',
    name: 'Hawksbill Summit',
    area: 'Central District · Shenandoah',
    routeShape: 'Out-and-back · Summit push',
    archetype: 'ridge',
    placeCue: 'The high point of the park, reached in under an hour up.',
    detailCharacter: 'A clean summit target with a bit more verticality than it first appears, but without full-day sprawl.',
    distanceMiles: 2.9,
    ascentFeet: 860,
    durationHours: '1.75–2.25 hr',
    effort: 'moderate',
    tags: ['views', 'summit', 'short', 'ridge'],
    conditionValue: '50°F · windy · clear',
    freshness: 'Forecast 58m old.',
    fitBase: 'A fast summit when you want height without a full day.',
    reasons: {
      standard: 'A direct climb to the best summit-per-mile here.',
      seekShade: 'Exposed near the top; better cool than hot.',
      bigViews: 'Sharpest summit view for the time spent.',
      quieter: 'Quieter early, before the summit gathers.',
    },
    practicalNote: 'Best used when you want a fast summit rather than a long day.',
    sources: ['NWS point forecast', 'NPS trail status'],
    drives: { frontRoyal: 56, luray: 28, charlottesville: 46, richmond: 116, duck: 300, nagsHead: 312, hatteras: 360, ocracoke: 384 },
    partyFit: { solo: 6, ruby: 4, friends: 4 },
    whenFit: { tomorrowMorning: 6, weekendMorning: 6, weekendAfternoon: 3, fullDay: 2 },
    effortFit: { easy: 2, moderate: 6, bigDay: 1 },
    promptTerms: ['views', 'summit', 'ridge', 'short'],
  },
]

// Dev-gate (Phase B "kill dummy messaging"): on a production build
// `import.meta.env.PROD` is statically replaced with `true`, this folds to `[]`,
// and the now-unreferenced SAMPLE_TRAILS literal is dead-code-eliminated from
// the bundle — so sample trails structurally cannot render as verified ones,
// even if a misconfigured deploy reached the mock engine.
const BASE_TRAILS: Omit<Trail, 'geo'>[] = import.meta.env.PROD ? [] : SAMPLE_TRAILS

/**
 * The mock trail set — each base record enriched with its sample route geometry
 * + elevation profile (AC-1.4). Attaching `geo` here, from `geoFixtures`, keeps
 * the profile tied to the trail's own `distanceMiles`/`ascentFeet` with no
 * duplicated figures.
 */
export const trails: Trail[] = BASE_TRAILS.map((trail) => ({
  ...trail,
  geo: buildTrailGeo(trail.id, trail.distanceMiles, trail.ascentFeet),
}))

export interface Scored {
  trail: Trail
  score: number
}

const promptBoost = (trail: Trail, prompt: string): number => {
  const normalized = prompt.trim().toLowerCase()
  if (!normalized) return 0
  return trail.promptTerms.reduce((score, term) => score + (normalized.includes(term) ? 2 : 0), 0)
}

const shadeBoost = (trail: Trail, state: TuningState): number => {
  if (state.today !== 'seekShade') return 0
  return trail.tags.includes('shade') || trail.tags.includes('water')
    ? 3
    : trail.tags.includes('ridge')
      ? -2
      : 0
}

const viewBoost = (trail: Trail, state: TuningState): number => {
  if (state.today !== 'bigViews') return 0
  return trail.tags.includes('views') || trail.tags.includes('summit') ? 3 : 0
}

const quietBoost = (trail: Trail, state: TuningState): number => {
  if (state.today !== 'quieter') return 0
  return trail.id === 'whiteoak-canyon' ? 2 : trail.id === 'stony-man' || trail.id === 'hawksbill' ? -1 : 0
}

const driveScore = (trail: Trail, state: TuningState): number => {
  const drive = trail.drives[state.origin]
  if (drive <= 30) return 4
  if (drive <= 50) return 2
  if (drive <= 70) return 0
  return -2
}

/**
 * Pure taste/viability score. No readiness term (R2): readiness is a gate, not
 * a penalty, so it can never reorder this list.
 */
export const scoreTrail = (trail: Trail, state: TuningState): number => {
  const baseline = 6
  return (
    baseline +
    trail.partyFit[state.party] +
    trail.whenFit[state.when] +
    trail.effortFit[state.effort] +
    driveScore(trail, state) +
    promptBoost(trail, state.prompt) +
    shadeBoost(trail, state) +
    viewBoost(trail, state) +
    quietBoost(trail, state)
  )
}

/**
 * Ruby's hard constraint (R6): a dog-incompatible trail is GATED for the whole
 * party with a stated reason, distinct from the soft `partyFit` taste term.
 * Returns the disclosure reason, or null when Ruby can come.
 */
export const rubyGate = (trail: Trail): string | null => {
  if (trail.tags.includes('scramble')) return 'the scramble isn’t a Ruby hike'
  if (trail.distanceMiles > 7) return 'too long a day for Ruby'
  return null
}

export const buildFitLine = (trail: Trail, state: TuningState): string => {
  if (state.today !== 'standard') return trail.reasons[state.today]
  return trail.fitBase
}

const SCORE_FLOOR = 7

function capWithVariety(eligible: Scored[]): Scored[] {
  const limited = eligible.slice(0, 3)
  if (limited.length <= 1) return limited

  const hasBigDay = limited.some(({ trail }) => trail.archetype === 'bigDay')
  if (!hasBigDay) {
    const ambitious = eligible.find(({ trail }) => trail.archetype === 'bigDay')
    if (ambitious && ambitious.score >= limited[limited.length - 1].score - 1) {
      return [...limited.slice(0, 2), ambitious].sort((a, b) => b.score - a.score)
    }
  }
  return limited
}

export interface FeedComputation {
  kept: Scored[]
  /** Excluded by the Ruby party gate, disclosed and restorable. */
  partySetAside: Array<Scored & { reason: string }>
}

/**
 * The full curation pass for a frame: rank everything (no gating in the score),
 * then apply the score floor and the Ruby hard gate, then cap to a peer set.
 *
 * Set-aside discloses exactly the options the gate removed *from the visible
 * set* — i.e. trails that would have appeared but for Ruby (R6). A low-ranked
 * dog-incompatible trail that wouldn't have shown anyway is not surfaced as
 * "set aside" (that would be noise, not disclosure).
 */
export function runFeed(state: TuningState): FeedComputation {
  const ranked: Scored[] = trails
    .map((trail) => ({ trail, score: scoreTrail(trail, state) }))
    .sort((a, b) => b.score - a.score)

  const viable = ranked.filter(({ score }) => score > SCORE_FLOOR)

  // What the user would see if the party gate did not apply.
  const keptIfUngated = capWithVariety(viable)

  const gated = (s: Scored): string | null => (state.party === 'ruby' ? rubyGate(s.trail) : null)

  const eligible = viable.filter((s) => gated(s) === null)
  const kept = capWithVariety(eligible)

  // Disclose only the gated options that were actually in the visible set.
  const partySetAside = keptIfUngated
    .map((s) => ({ s, reason: gated(s) }))
    .filter((x): x is { s: Scored; reason: string } => x.reason !== null)
    .map(({ s, reason }) => ({ ...s, reason }))

  return { kept, partySetAside }
}

// ---- frame-conditions-wave mock fixtures (Epic 055 S6) ---------------------
//
// The mock DATA for the "This feed" card + strip states. These are the seam
// the mock adapter (`mockPlanner.ts`, owned by the data lane / Epic 056)
// consumes to surface `FeedVM.regionConditions` and per-card `conditions` /
// `warnings` in `npm run dev` — the card lane (055) owns the DATA and the
// components; the adapter WIRING lives in the data layer this same wave. Kept
// here (the engine "doubles as the test fixture set") so every card state has
// one honest home, locked by `engine.test.ts`.

// The target forecast day the `when` facet points at (§5).
function forecastDaysForWhen(when: TuningState['when']): { days: RegionConditionsVM['forecast'] } {
  // Deliberately illustrative (mock provenance): today is warm, the weekend
  // mild — so the "going Saturday, not today" temporal split is visible.
  const today = { key: 'today', label: 'Today', highF: 88, precipPct: 0, short: 'Sunny' as string | null }
  const tomorrow = { key: 'tomorrow', label: 'Tomorrow', highF: 79, precipPct: 10, short: 'Partly sunny' }
  const sat = { key: 'sat', label: 'Sat', highF: 68, precipPct: 20, short: 'Partly sunny' }
  const sun = { key: 'sun', label: 'Sun', highF: 71, precipPct: 10, short: 'Mostly sunny' }
  if (when === 'tomorrowMorning') {
    return { days: { days: [today, tomorrow], targetKey: 'tomorrow', source: 'NWS', fetchedAgo: 'just now' } }
  }
  if (when === 'fullDay') {
    return { days: { days: [today, sat, sun], targetKey: 'today', source: 'NWS', fetchedAgo: 'just now' } }
  }
  return { days: { days: [today, sat, sun], targetKey: 'sat', source: 'NWS', fetchedAgo: 'just now' } }
}

/**
 * The area-level conditions for the This-feed card (§5): a frame-aligned
 * forecast with a working day toggle, the recent-rain reveal, and the hedged
 * mud read. Mud is present only because the sample 48h total clears the rule —
 * an inference, always hedged, never a stated fact (Rule #7).
 */
export function mockRegionConditions(state: TuningState): RegionConditionsVM {
  const { days } = forecastDaysForWhen(state.when)
  return {
    forecast: days,
    recentPrecip: {
      days: [
        { label: 'Thu', amountIn: 0.8 },
        { label: 'Fri', amountIn: 0.4 },
        { label: 'Today', amountIn: 0 },
      ],
      total48hIn: 1.2,
      source: 'NWS observations',
    },
    mud: {
      statement: 'Trails may be muddy',
      evidence: '1.2" of rain in the last 48h, dry today',
      source: 'NWS observations',
      provenance: 'inferred',
    },
  }
}

/**
 * Per-trail condition coverage + warnings, spread across the sample set so the
 * strip exercises every state in `npm run dev`: all-fresh, one-stale, one
 * unavailable, an amber heads-up, and a terracotta closure. Trails not listed
 * carry no conditions (the honest thin default). Provenance is `mock` on the
 * lines the adapter builds — the surface always discloses sample data (R1).
 */
export const mockTrailConditions: Record<string, { conditions: ConditionStatusVM[]; warnings: WarningVM[] }> = {
  // All fresh — a clean row you skim in one look.
  'stony-man': {
    conditions: [
      { kind: 'weather', state: 'present', source: 'NWS', checkedAgo: 'just now' },
      { kind: 'air', state: 'present', source: 'AirNow', checkedAgo: '2m ago' },
      { kind: 'fire', state: 'no-hazard', source: 'NASA FIRMS', checkedAgo: '6m ago' },
      { kind: 'closures', state: 'no-hazard', source: 'NPS', checkedAgo: '1h ago' },
    ],
    warnings: [],
  },
  // One stale reading + an amber heads-up (creek running high, passable).
  'whiteoak-canyon': {
    conditions: [
      { kind: 'weather', state: 'present', source: 'NWS', checkedAgo: 'just now' },
      { kind: 'water', state: 'stale-degraded', source: 'USGS', checkedAgo: '3h ago' },
      { kind: 'air', state: 'present', source: 'AirNow', checkedAgo: '2m ago' },
    ],
    warnings: [
      {
        text: 'Creek running high — verify crossings',
        source: 'USGS',
        observedAgo: '40m ago',
        kind: 'water',
        provenance: 'mock',
        severity: 'headsUp',
      },
    ],
  },
  // A terracotta closure — a genuine barrier (Q7 blocked).
  'old-rag': {
    conditions: [
      { kind: 'weather', state: 'present', source: 'NWS', checkedAgo: 'just now' },
      { kind: 'closures', state: 'present', source: 'NPS', checkedAgo: '1h ago' },
      { kind: 'air', state: 'present', source: 'AirNow', checkedAgo: '2m ago' },
    ],
    warnings: [
      {
        text: 'Ridge trail closed — rockfall',
        source: 'NPS',
        observedAgo: '1h ago',
        kind: 'closures',
        provenance: 'mock',
        severity: 'blocked',
      },
    ],
  },
  // One unavailable (a probe that answered nothing — never "clear").
  'dark-hollow': {
    conditions: [
      { kind: 'weather', state: 'present', source: 'NWS', checkedAgo: 'just now' },
      { kind: 'air', state: 'unavailable' },
      { kind: 'water', state: 'no-data', source: 'USGS', detail: 'no gauge near this route' },
    ],
    warnings: [],
  },
}
