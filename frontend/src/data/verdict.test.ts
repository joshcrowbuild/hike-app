import { describe, expect, it } from 'vitest'

import type { CardVM, LineVM, WarningVM } from './vm'
import { deriveVerdict } from './verdict'

/** A minimal live card; override the fact-bearing bits per case. */
function card(over: Partial<CardVM> = {}): CardVM {
  return {
    id: 't1',
    name: 'Old Rag',
    distanceMi: null,
    conditionLines: [],
    warnings: [],
    ...over,
  }
}

const line = (over: Partial<LineVM> = {}): LineVM => ({
  text: 'Sunny 72°F · NWS, just now',
  source: 'NWS api.weather.gov · single authoritative source',
  confidence: 'stated',
  provenance: 'live',
  ...over,
})

const warning = (over: Partial<WarningVM> = {}): WarningVM => ({
  text: 'Extreme Heat Warning',
  source: 'NWS',
  observedAgo: '20m ago',
  kind: 'weather',
  provenance: 'live',
  ...over,
})

describe('deriveVerdict — the go/no-go headline (presentation only, R2)', () => {
  it('a verified hazard is the headline: caution, naming the alert', () => {
    const v = deriveVerdict(card({ warnings: [warning()] }))
    expect(v.tone).toBe('caution')
    expect(v.lead).toBe('Caution')
    expect(v.detail).toBe('active Extreme Heat Warning')
    expect(v.provenance).toBe('live')
  })

  it('multiple hazards summarise the first and count the rest', () => {
    const v = deriveVerdict(
      card({ warnings: [warning(), warning({ text: 'Red Flag Warning', kind: 'fire' })] }),
    )
    expect(v.detail).toBe('active Extreme Heat Warning (+1 more)')
  })

  it('a warning wins even when a clear reading is also present', () => {
    const v = deriveVerdict(card({ warnings: [warning()], conditionLines: [line()] }))
    expect(v.tone).toBe('caution')
  })

  it('a verified, unflagged reading → good to go, summarised from the value', () => {
    const v = deriveVerdict(card({ conditionLines: [line()] }))
    expect(v.tone).toBe('go')
    expect(v.lead).toBe('Good to go')
  })

  it('a flagged reading is never dressed as clear — heads up (Rule #1)', () => {
    const v = deriveVerdict(card({ conditionLines: [line({ confidence: 'flagged' })] }))
    expect(v.tone).toBe('unverified')
    expect(v.lead).toBe('Heads up')
    expect(v.detail).toMatch(/couldn’t be verified/)
  })

  it('no probe run yet (not-fetched) → heads up, never a false all-clear', () => {
    const v = deriveVerdict(card({ conditionSilence: { state: 'not-fetched' } }))
    expect(v.tone).toBe('unverified')
  })

  it('an explicit checked-clear silence is a real positive → good to go', () => {
    const v = deriveVerdict(card({ conditionSilence: { state: 'checked-clear' } }))
    expect(v.tone).toBe('go')
    expect(v.provenance).toBe('live')
  })

  it('carries the driving signal’s provenance so a sample verdict can demote (R1)', () => {
    const v = deriveVerdict(
      card({
        conditionLines: [line({ provenance: 'mock' })],
        enrichment: { provenance: 'mock', conditionValue: '54°F · breezy · clear' },
      }),
    )
    expect(v.tone).toBe('go')
    expect(v.detail).toBe('54°F · breezy · clear')
    expect(v.provenance).toBe('mock')
  })
})
