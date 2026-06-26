/**
 * Folds the structured tuning frame into the single free-text `query` the
 * backend's mechanical intent parser understands. This is the lossy seam the
 * plan flags (§5.4): until the backend grows structured facet fields (backend
 * ask #2), when/effort/party/today/prompt all round-trip through text.
 *
 * The mock does NOT rely on this (it honors the structured `TuningState`
 * directly and deterministically, per R-plan §5.4) — this exists for the HTTP
 * adapter so a real `/plan` call still receives the user's intent.
 */
import type { TuningState } from '../types'

const effortTerms: Record<TuningState['effort'], string> = {
  easy: 'easy short',
  moderate: 'moderate',
  bigDay: 'big day long',
}

const whenTerms: Record<TuningState['when'], string> = {
  tomorrowMorning: 'tomorrow morning',
  weekendMorning: 'weekend morning',
  weekendAfternoon: 'weekend afternoon',
  fullDay: 'full day',
}

const todayTerms: Record<TuningState['today'], string> = {
  standard: '',
  seekShade: 'shade cooler',
  bigViews: 'big views',
  quieter: 'quiet less crowded',
}

const partyTerms: Record<TuningState['party'], string> = {
  solo: '',
  ruby: 'dog-friendly with my dog',
  friends: 'with friends',
}

export function buildQuery(tuning: TuningState): string {
  return [
    tuning.prompt.trim(),
    whenTerms[tuning.when],
    effortTerms[tuning.effort],
    partyTerms[tuning.party],
    todayTerms[tuning.today],
  ]
    .filter(Boolean)
    .join(' ')
    .trim()
}
