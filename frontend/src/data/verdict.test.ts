import { describe, expect, it } from 'vitest'

import type { CardVM, ConditionStatusVM, LineVM, WarningVM } from './vm'
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

  // F2 (ux-review 2026-07): the go-detail claims only what was VERIFIED. "Clear"
  // is a weather word — asserted beside a sourced "Showers And Thunderstorms
  // Likely" line it was an unsourced editorial claim (Invariant 1). The detail
  // now counts the checks that actually answered (the six-state vocabulary),
  // never characterising the sky on its own authority.
  describe('the go-detail never asserts an unverified sky-state (F2, Invariant 1)', () => {
    const status = (over: Partial<ConditionStatusVM>): ConditionStatusVM => ({
      kind: 'weather',
      state: 'present',
      ...over,
    })

    it('never says "clear" as a default string', () => {
      const v = deriveVerdict(card({ conditionLines: [line({ text: 'Showers And Thunderstorms Likely 77°F' })] }))
      expect(v.tone).toBe('go')
      expect(v.detail).not.toMatch(/clear/i)
    })

    it('counts only the checks a source actually answered', () => {
      const v = deriveVerdict(
        card({
          conditionLines: [line()],
          conditions: [
            status({ kind: 'weather', state: 'present', source: 'NWS' }),
            status({ kind: 'fire', state: 'no-hazard', source: 'NASA FIRMS' }),
            status({ kind: 'water', state: 'no-data', source: 'USGS' }),
            status({ kind: 'air', state: 'unavailable' }),
            status({ kind: 'closures', state: 'not-fetched' }),
          ],
        }),
      )
      // 3 answered (present + no-hazard + no-data); unavailable/not-fetched are
      // NOT checks — counting them would dress an outage as a completed sweep.
      expect(v.detail).toBe('nothing flagged across 3 checks')
    })

    it('uses the singular for one answered check', () => {
      const v = deriveVerdict(
        card({ conditionLines: [line()], conditions: [status({ kind: 'weather', state: 'present', source: 'NWS' })] }),
      )
      expect(v.detail).toBe('nothing flagged in 1 check')
    })

    it('claims only "nothing flagged" when no six-state payload exists (older backend)', () => {
      const v = deriveVerdict(card({ conditionLines: [line()] }))
      expect(v.detail).toBe('nothing flagged')
    })

    it('still quotes a merged reading verbatim when enrichment supplies one', () => {
      const v = deriveVerdict(
        card({
          conditionLines: [line()],
          enrichment: { provenance: 'live', conditionValue: 'Showers likely 77°F' },
        }),
      )
      expect(v.detail).toBe('Showers likely 77°F')
    })
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
    // Six-state vocabulary, not a sky-word: the source answered "nothing to
    // flag" — that is the whole claim (F2).
    expect(v.detail).toBe('checked — nothing to flag')
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
