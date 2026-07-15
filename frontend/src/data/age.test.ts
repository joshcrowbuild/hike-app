import { describe, expect, it } from 'vitest'

import { relativeAge, TIME_UNKNOWN } from './age'

const NOW = Date.parse('2026-07-01T22:00:00Z')

describe('relativeAge (§7.2 — relative time, never a raw datetime)', () => {
  it('reads sub-minute ages as "just now"', () => {
    expect(relativeAge('2026-07-01T21:59:30Z', NOW)).toBe('just now')
  })

  it('humanises minutes, hours and days', () => {
    expect(relativeAge('2026-07-01T21:48:00Z', NOW)).toBe('12m ago')
    expect(relativeAge('2026-07-01T20:00:00Z', NOW)).toBe('2h ago')
    expect(relativeAge('2026-06-28T22:00:00Z', NOW)).toBe('3d ago')
  })

  it('degrades an unparseable timestamp to the disclosed TIME_UNKNOWN token, never a fabricated age', () => {
    expect(relativeAge('not-a-date', NOW)).toBe(TIME_UNKNOWN)
    expect(TIME_UNKNOWN).toBe('time unknown')
  })
})
