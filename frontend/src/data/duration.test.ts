import { describe, expect, it } from 'vitest'
import { formatEstimatedDuration } from './duration'

describe('formatEstimatedDuration', () => {
  it('renders minutes under an hour', () => {
    expect(formatEstimatedDuration(26)).toContain('25 min')
  })

  it('renders hours plus minutes when nonzero', () => {
    expect(formatEstimatedDuration(155)).toContain('2 hr 35 min')
  })

  it('renders bare hours when minutes are zero', () => {
    expect(formatEstimatedDuration(120)).toContain('2 hr')
  })

  it('no longer bakes the "est." disclosure into the string (ux-review 2026-07 Finding 1) — that moves to DecisionItem\'s own badge, so the fact\'s value stays the narrowest it can be', () => {
    expect(formatEstimatedDuration(155)).not.toContain('est')
    expect(formatEstimatedDuration(26)).not.toContain('est')
  })

  it('starts with an approximation marker', () => {
    expect(formatEstimatedDuration(26)).toMatch(/^~/)
  })

  it('never shows false-precision decimals', () => {
    expect(formatEstimatedDuration(25.9)).not.toMatch(/\d\.\d/)
  })

  it('floors a small positive value at 5 minutes, never 0', () => {
    expect(formatEstimatedDuration(2)).toContain('5 min')
    expect(formatEstimatedDuration(2)).not.toContain('0 min')
  })
})
