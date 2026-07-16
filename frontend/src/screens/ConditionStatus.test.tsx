import { describe, expect, it } from 'vitest'
import { toTier } from './ConditionStatus'
import type { ConditionStatusVM } from '../data/vm'

describe('ConditionStatus engine', () => {
  describe('toTier()', () => {
    it('maps no-hazard to clear', () => {
      const status: ConditionStatusVM = { kind: 'weather', state: 'no-hazard' }
      expect(toTier(status)).toBe('clear')
    })

    it('maps present closures to blocked', () => {
      const status: ConditionStatusVM = { kind: 'closures', state: 'present' }
      expect(toTier(status)).toBe('blocked')
    })

    it('maps present permits to blocked', () => {
      const status: ConditionStatusVM = { kind: 'permits', state: 'present' }
      expect(toTier(status)).toBe('blocked')
    })

    it('maps present weather to headsUp', () => {
      const status: ConditionStatusVM = { kind: 'weather', state: 'present' }
      expect(toTier(status)).toBe('headsUp')
    })

    it('maps present air to headsUp', () => {
      const status: ConditionStatusVM = { kind: 'air', state: 'present' }
      expect(toTier(status)).toBe('headsUp')
    })

    it('maps no-data to unknown', () => {
      const status: ConditionStatusVM = { kind: 'weather', state: 'no-data' }
      expect(toTier(status)).toBe('unknown')
    })

    it('maps unavailable to unknown', () => {
      const status: ConditionStatusVM = { kind: 'weather', state: 'unavailable' }
      expect(toTier(status)).toBe('unknown')
    })

    it('maps not-fetched to unknown', () => {
      const status: ConditionStatusVM = { kind: 'weather', state: 'not-fetched' }
      expect(toTier(status)).toBe('unknown')
    })

    it('maps stale-degraded to unknown', () => {
      const status: ConditionStatusVM = { kind: 'weather', state: 'stale-degraded' }
      expect(toTier(status)).toBe('unknown')
    })
  })
})
