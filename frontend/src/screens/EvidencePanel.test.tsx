import { describe, expect, test } from 'vitest'
import { cleanEvidenceBody } from './EvidencePanel'
import { summarizeConditions } from './ConditionStatus'
import type { ConditionStatusVM } from '../data/vm'

describe('EvidencePanel logic', () => {
  describe('cleanEvidenceBody', () => {
    test('cleans gauge unavailable phrase', () => {
      expect(cleanEvidenceBody('flow reading unavailable at Pass Run Trib 2 To Trib 2 gauge')).toBe(
        'No gauge near this route',
      )
    })

    test('cleans permit missing phrase', () => {
      expect(cleanEvidenceBody('Permit info not checked — 10 nearby facilities')).toBe('None required here')
    })

    test('passes other phrases unchanged', () => {
      expect(cleanEvidenceBody('Sunny 90°F')).toBe('Sunny 90°F')
    })
  })

  // Regression guard for the detail honesty bug: the conclusion now comes from
  // the shared summarizeConditions engine, which must NEVER fabricate a "closed"
  // claim (or an actionable "N things to know") from unverified conditions.
  describe('detail conclusion (via summarizeConditions)', () => {
    const notChecked: ConditionStatusVM[] = [
      { kind: 'weather', state: 'not-fetched' },
      { kind: 'air', state: 'not-fetched' },
      { kind: 'closures', state: 'not-fetched' },
      { kind: 'permits', state: 'not-fetched' },
    ]

    test('all-unknown never reads "closed" or "N things to know"', () => {
      const s = summarizeConditions(notChecked, [], 'detail')
      expect(s?.tier).toBe('unknown')
      expect(s?.conclusion).not.toMatch(/closed/i)
      expect(s?.conclusion).not.toMatch(/things to know/i)
      expect(s?.conclusion).toBe('Conditions couldn’t be verified right now.')
    })

    test('a real present closure still reads as blocked', () => {
      const s = summarizeConditions([{ kind: 'closures', state: 'present' }], [], 'detail')
      expect(s?.tier).toBe('blocked')
    })

    test('all no-hazard reads clear', () => {
      const s = summarizeConditions([{ kind: 'weather', state: 'no-hazard' }], [], 'detail')
      expect(s?.conclusion).toBe('Conditions look clear.')
    })
  })
})
