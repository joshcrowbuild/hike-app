/** Human labels for the tuning facets. UI-facing, mock-or-live agnostic. */
import type { EffortKey, OriginKey, PartyKey, TodayKey, WhenKey } from '../types'

export const originLabels: Record<OriginKey, string> = {
  frontRoyal: 'Front Royal',
  luray: 'Luray',
  charlottesville: 'Charlottesville',
  richmond: 'Richmond',
  duck: 'Duck',
  nagsHead: 'Nags Head',
  hatteras: 'Hatteras',
  ocracoke: 'Ocracoke',
}

/** Which region an origin anchors — drives the region tag on Home so it tracks
 *  the selected origin instead of assuming the Shenandoah pilot region. */
export const regionLabels: Record<OriginKey, string> = {
  frontRoyal: 'Shenandoah',
  luray: 'Shenandoah',
  charlottesville: 'Shenandoah',
  richmond: 'Richmond',
  duck: 'Outer Banks',
  nagsHead: 'Outer Banks',
  hatteras: 'Outer Banks',
  ocracoke: 'Outer Banks',
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
