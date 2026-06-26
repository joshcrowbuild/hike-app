/**
 * The single obvious relaxation for an over-tuned frame (R9): "show moderate
 * too", "drop the shade/views/quiet lean", etc. One tap to a viable set, never
 * a trip back through the sheets. Pure and source-agnostic so the empty/sparse
 * states can propose it regardless of mock vs live.
 */
import type { TuningState } from '../types'

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
