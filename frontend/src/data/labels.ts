/** Human labels for the tuning facets. UI-facing, mock-or-live agnostic. */
import type { EffortKey, OriginKey, PartyKey, TodayKey, WhenKey } from '../types'

export const originLabels: Record<OriginKey, string> = {
  frontRoyal: 'Front Royal',
  luray: 'Luray',
  charlottesville: 'Charlottesville',
  duck: 'Duck',
  nagsHead: 'Nags Head',
  hatteras: 'Hatteras',
  ocracoke: 'Ocracoke',
}

export const whenLabels: Record<WhenKey, string> = {
  tomorrowMorning: 'Tomorrow morning',
  weekendMorning: 'Weekend morning',
  weekendAfternoon: 'Weekend afternoon',
  fullDay: 'Full day',
}

export const effortLabels: Record<EffortKey, string> = {
  easy: 'Easy',
  moderate: 'Moderate',
  bigDay: 'Big day',
}

export const partyLabels: Record<PartyKey, string> = {
  solo: 'Solo',
  ruby: 'Solo + Ruby',
  friends: 'With friends',
}

export const todayLabels: Record<TodayKey, string> = {
  standard: 'Standard',
  seekShade: 'Seek shade',
  bigViews: 'Big views',
  quieter: 'Quieter',
}
