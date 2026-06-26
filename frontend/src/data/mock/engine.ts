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

export const trails: Trail[] = [
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
    drives: { frontRoyal: 28, luray: 32, charlottesville: 74 },
    partyFit: { solo: 6, ruby: 5, friends: 4 },
    whenFit: { tomorrowMorning: 6, weekendMorning: 6, weekendAfternoon: 3, fullDay: 2 },
    effortFit: { easy: 1, moderate: 6, bigDay: 2 },
    promptTerms: ['ridge', 'views', 'short', 'classic'],
    terrainPath: [18, 35, 48, 62, 57, 71, 80, 66, 44],
    profilePath: [12, 18, 32, 46, 58, 66, 71, 72, 70],
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
    drives: { frontRoyal: 52, luray: 29, charlottesville: 49 },
    partyFit: { solo: 5, ruby: 6, friends: 4 },
    whenFit: { tomorrowMorning: 5, weekendMorning: 5, weekendAfternoon: 6, fullDay: 4 },
    effortFit: { easy: 2, moderate: 6, bigDay: 2 },
    promptTerms: ['shade', 'water', 'cool', 'forest', 'ruby'],
    terrainPath: [22, 24, 28, 33, 40, 43, 48, 52, 58],
    profilePath: [8, 16, 21, 29, 35, 45, 56, 59, 60],
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
    drives: { frontRoyal: 64, luray: 43, charlottesville: 51 },
    partyFit: { solo: 4, ruby: 0, friends: 6 },
    whenFit: { tomorrowMorning: 2, weekendMorning: 3, weekendAfternoon: 0, fullDay: 6 },
    effortFit: { easy: 0, moderate: 1, bigDay: 7 },
    promptTerms: ['big day', 'ridge', 'iconic', 'views'],
    terrainPath: [10, 28, 44, 67, 80, 72, 84, 63, 40],
    profilePath: [6, 18, 30, 43, 57, 69, 77, 74, 62],
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
    drives: { frontRoyal: 54, luray: 31, charlottesville: 42 },
    partyFit: { solo: 5, ruby: 6, friends: 3 },
    whenFit: { tomorrowMorning: 4, weekendMorning: 4, weekendAfternoon: 5, fullDay: 1 },
    effortFit: { easy: 7, moderate: 2, bigDay: 0 },
    promptTerms: ['short', 'water', 'shade', 'easy', 'ruby'],
    terrainPath: [15, 18, 23, 29, 37, 41, 42, 40, 36],
    profilePath: [10, 16, 20, 27, 33, 35, 36, 31, 26],
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
    drives: { frontRoyal: 56, luray: 28, charlottesville: 46 },
    partyFit: { solo: 6, ruby: 4, friends: 4 },
    whenFit: { tomorrowMorning: 6, weekendMorning: 6, weekendAfternoon: 3, fullDay: 2 },
    effortFit: { easy: 2, moderate: 6, bigDay: 1 },
    promptTerms: ['views', 'summit', 'ridge', 'short'],
    terrainPath: [24, 30, 40, 51, 59, 67, 72, 61, 46],
    profilePath: [12, 19, 28, 40, 54, 62, 68, 67, 61],
  },
]

export interface Scored {
  trail: Trail
  score: number
  promptMiss: boolean
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

const promptFallback = (trail: Trail, state: TuningState): boolean => {
  if (!state.prompt.trim()) return false
  return promptBoost(trail, state.prompt) === 0
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
  /** Excluded by a fresh readiness reading (none tonight — see MockPlannerClient). */
  readinessHidden: Scored[]
}

/**
 * The full curation pass for a frame: rank everything (no gating in the score),
 * then apply the score floor and the Ruby hard gate, then cap to a peer set.
 *
 * Set-aside discloses exactly the options the gate removed *from the visible
 * set* — i.e. trails that would have appeared but for Ruby (R6). A low-ranked
 * dog-incompatible trail that wouldn't have shown anyway is not surfaced as
 * "set aside" (that would be noise, not disclosure).
 *
 * Readiness is intentionally NOT applied here — there is no reading in the mock,
 * so MockPlannerClient fails the filter open and discloses it (R2). The hook is
 * left (`readinessHidden`) for when a real reading exists.
 */
export function runFeed(state: TuningState): FeedComputation {
  const ranked: Scored[] = trails
    .map((trail) => ({ trail, score: scoreTrail(trail, state), promptMiss: promptFallback(trail, state) }))
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

  return { kept, partySetAside, readinessHidden: [] }
}

/**
 * The single obvious relaxation for an over-tuned frame (R9): "show moderate
 * too", "drop the shade/views/quiet lean", etc. One tap to a viable set, never
 * a trip back through the sheets. Returns null when the frame is already broad.
 */
export function widenFrame(state: TuningState): { next: TuningState; label: string } | null {
  if (state.today !== 'standard') {
    return { next: { ...state, today: 'standard' }, label: 'Drop the “today” lean' }
  }
  if (state.effort === 'easy') {
    return { next: { ...state, effort: 'moderate' }, label: 'Show moderate too' }
  }
  if (state.effort === 'moderate') {
    return { next: { ...state, effort: 'bigDay' }, label: 'Include a bigger day' }
  }
  return null
}
