/**
 * Human labels for the tuning facets. UI-facing, mock-or-live agnostic.
 *
 * Origin/region labels are NOT here (Phase 2: config-driven origins) — they come
 * from the fetched region catalog (`regionsCatalog.ts`'s `useOrigins`), since the
 * set of origins is runtime config, not a compile-time list.
 */
import type { EffortKey, PartyKey, TodayKey, WhenKey } from '../types'

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
