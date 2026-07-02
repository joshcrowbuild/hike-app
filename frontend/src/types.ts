import type { TrailGeo } from './data/vm'

export type OriginKey =
  | 'frontRoyal'
  | 'luray'
  | 'charlottesville'
  | 'richmond'
  | 'duck'
  | 'nagsHead'
  | 'hatteras'
  | 'ocracoke'
export type WhenKey = 'tomorrowMorning' | 'weekendMorning' | 'weekendAfternoon' | 'fullDay'
export type EffortKey = 'easy' | 'moderate' | 'bigDay'
export type PartyKey = 'solo' | 'ruby' | 'friends'
export type TodayKey = 'standard' | 'seekShade' | 'bigViews' | 'quieter'

export type Trail = {
  id: string
  name: string
  area: string
  routeShape: string
  archetype: 'ridge' | 'forest' | 'bigDay' | 'waterfall'
  placeCue: string
  detailCharacter: string
  distanceMiles: number
  ascentFeet: number
  durationHours: string
  effort: EffortKey
  tags: string[]
  conditionValue: string
  caution?: string
  freshness: string
  fitBase: string
  reasons: Record<TodayKey, string>
  practicalNote: string
  sources: string[]
  drives: Record<OriginKey, number>
  partyFit: Record<PartyKey, number>
  whenFit: Record<WhenKey, number>
  effortFit: Record<EffortKey, number>
  promptTerms: string[]
  /** Route geometry + trailhead + elevation profile (Epic 016). */
  geo: TrailGeo
}

export type TuningState = {
  origin: OriginKey
  when: WhenKey
  effort: EffortKey
  party: PartyKey
  today: TodayKey
  readinessOn: boolean
  prompt: string
}
