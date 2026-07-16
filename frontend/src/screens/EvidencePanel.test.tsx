import { describe, expect, test } from 'vitest'
import { deriveConclusion, cleanEvidenceBody } from './EvidencePanel'
import type { ConditionTier } from '../design/contracts'

describe('EvidencePanel logic', () => {
  describe('deriveConclusion', () => {
    test('returns blocked if any tier is blocked', () => {
      expect(deriveConclusion(['clear', 'blocked', 'unknown'])).toBe('This trail is closed right now.')
    })

    test('returns headsUp if no blocked but has headsUp', () => {
      expect(deriveConclusion(['clear', 'headsUp', 'unknown'])).toBe('Two things to know before you go.')
    })

    test('returns clear if only clear and unknown', () => {
      expect(deriveConclusion(['clear', 'unknown'])).toBe('Conditions look clear.')
    })

    test('returns clear if empty', () => {
      expect(deriveConclusion([])).toBe('Conditions look clear.')
    })
  })

  describe('cleanEvidenceBody', () => {
    test('cleans gauge unavailable phrase', () => {
      expect(cleanEvidenceBody('flow reading unavailable at Pass Run Trib 2 To Trib 2 gauge')).toBe('No gauge near this route')
    })

    test('cleans permit missing phrase', () => {
      expect(cleanEvidenceBody('Permit info not checked — 10 nearby facilities')).toBe('None required here')
    })

    test('passes other phrases unchanged', () => {
      expect(cleanEvidenceBody('Sunny 90°F')).toBe('Sunny 90°F')
    })
  })
})
