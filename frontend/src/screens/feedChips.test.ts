import { describe, expect, it } from 'vitest'

import type { CardVM, ConditionStatusVM, LineVM, WarningVM } from '../data/vm'
import {
  chipValueText,
  cleanEvidenceBody,
  detailConditionChips,
  feedCurrentChips,
  heldBackChips,
  inferKindFromSource,
  warningTierByKind,
} from './feedChips'

function card(over: Partial<CardVM> = {}): CardVM {
  return { id: 'c', name: 'C', distanceMi: null, conditionLines: [], warnings: [], ...over }
}

const liveLine = (text: string, source: string, over: Partial<LineVM> = {}): LineVM => ({
  text,
  source,
  confidence: 'stated',
  provenance: 'live',
  ...over,
})

describe('cleanEvidenceBody (relocated from EvidencePanel)', () => {
  it('cleans the gauge-unavailable phrase', () => {
    expect(cleanEvidenceBody('flow reading unavailable at Pass Run gauge')).toBe('No gauge near this route')
  })
  it('cleans the permit-missing phrase', () => {
    expect(cleanEvidenceBody('Permit info not checked — 10 nearby facilities')).toBe('None required here')
  })
  it('passes other phrases unchanged', () => {
    expect(cleanEvidenceBody('Sunny 90°F')).toBe('Sunny 90°F')
  })
})

describe('chipValueText — a terse, scannable lead', () => {
  it('keeps the leading reading of a compound line', () => {
    expect(chipValueText('54°F · breezy · clear')).toBe('54°F')
    expect(chipValueText('AQI 54 · good')).toBe('AQI 54')
  })
  it('never fabricates: an empty lead falls back to the whole cleaned string', () => {
    expect(chipValueText('No gauge near this route')).toBe('No gauge near this route')
  })
})

describe('inferKindFromSource — a glyph hint only, never a claim', () => {
  it('maps known providers to their kind', () => {
    expect(inferKindFromSource('AirNow')).toBe('air')
    expect(inferKindFromSource('NASA FIRMS')).toBe('fire')
    expect(inferKindFromSource('USGS streamflow')).toBe('water')
    expect(inferKindFromSource('NPS closure feed')).toBe('closures')
    expect(inferKindFromSource('Rec.gov')).toBe('permits')
    expect(inferKindFromSource('NWS point forecast')).toBe('weather')
  })

  it('matches the REAL backend permits constant, not just a fictional one', () => {
    // Review CRITICAL: "Recreation.gov RIDB" (ridb.py's actual SOURCE) does
    // not contain 'rec.gov', so a permits line fell through to 'weather' —
    // wrong glyph AND a blocked permit tint silently skipped (Q5).
    expect(inferKindFromSource('Recreation.gov RIDB')).toBe('permits')
    expect(inferKindFromSource('RIDB')).toBe('permits')
  })
})

describe('warningTierByKind — blocked wins, absent grades headsUp (Q7)', () => {
  const warn = (kind: string, severity?: WarningVM['severity']): WarningVM => ({
    text: 't',
    source: 's',
    kind,
    provenance: 'live',
    severity,
  })

  it('grades an absent severity as headsUp (never louder than the backend)', () => {
    const m = warningTierByKind([card({ warnings: [warn('weather')] })])
    expect(m.get('weather')).toBe('headsUp')
  })

  it('lets a blocked warning win over a heads-up of the same kind', () => {
    const m = warningTierByKind([
      card({ warnings: [warn('closures', 'headsUp')] }),
      card({ warnings: [warn('closures', 'blocked')] }),
    ])
    expect(m.get('closures')).toBe('blocked')
  })
})

describe('feedCurrentChips — region-shared readings + silences', () => {
  // A region-shared reading appears verbatim on a strict majority of cards.
  const shared = (over: Partial<CardVM> = {}): CardVM =>
    card({
      conditionLines: [liveLine('AQI 54 · good', 'AirNow', { sources: ['AirNow'] })],
      conditions: [
        { kind: 'air', state: 'present', source: 'AirNow', checkedAgo: '2m ago' },
        { kind: 'fire', state: 'no-hazard', source: 'NASA FIRMS', checkedAgo: '6m ago' },
        { kind: 'water', state: 'unavailable' },
      ],
      ...over,
    })

  it('maps a shared value line to a fresh chip with its kind (via the fold) and a receipt', () => {
    const chips = feedCurrentChips([shared({ id: 'a' }), shared({ id: 'b' }), shared({ id: 'c' })])
    const air = chips.find((c) => c.kind === 'air')
    expect(air?.state).toBe('fresh')
    expect(air?.valueText).toBe('AQI 54')
    expect(air?.receipt?.source).toBe('AirNow')
  })

  it('maps a shared no-hazard sweep to a fresh chip and an unavailable probe to a dashed "—"', () => {
    const chips = feedCurrentChips([shared({ id: 'a' }), shared({ id: 'b' }), shared({ id: 'c' })])
    expect(chips.find((c) => c.kind === 'fire')?.state).toBe('fresh')
    const water = chips.find((c) => c.kind === 'water')
    expect(water?.state).toBe('unavailable')
    expect(water?.valueText).toBe('—')
  })

  it('tints a chip whose kind a warning owns (Q5)', () => {
    const withWarn = (id: string): CardVM =>
      shared({ id, warnings: [{ text: 'AQI high', source: 'AirNow', kind: 'air', provenance: 'live', severity: 'headsUp' }] })
    const chips = feedCurrentChips([withWarn('a'), withWarn('b'), withWarn('c')])
    expect(chips.find((c) => c.kind === 'air')?.tier).toBe('headsUp')
  })
})

describe('detailConditionChips — one trail, per-kind', () => {
  const conditions: ConditionStatusVM[] = [
    { kind: 'weather', state: 'present', source: 'NWS', checkedAgo: 'just now' },
    { kind: 'closures', state: 'present', source: 'NPS', checkedAgo: '1h ago' },
    { kind: 'air', state: 'unavailable' },
  ]
  const detailCard = card({
    conditionLines: [liveLine('73°F · partly cloudy', 'NWS'), liveLine('closed', 'NPS')],
    conditions,
    warnings: [{ text: 'Ridge closed', source: 'NPS', kind: 'closures', provenance: 'live', severity: 'blocked' }],
  })

  it('renders a chip per condition kind, folding the value line and honouring the state', () => {
    const chips = detailConditionChips(detailCard)
    expect(chips.map((c) => c.kind)).toEqual(['weather', 'closures', 'air'])
    expect(chips.find((c) => c.kind === 'weather')?.valueText).toBe('73°F')
    expect(chips.find((c) => c.kind === 'air')?.state).toBe('unavailable')
  })

  it('tints the closures chip terracotta (blocked) because a warning owns it (Q5/Q7)', () => {
    const chips = detailConditionChips(detailCard)
    expect(chips.find((c) => c.kind === 'closures')?.tier).toBe('blocked')
  })

  it('never drops a value line no disposition claimed — appends it as a fresh chip', () => {
    const linesOnly = card({ conditionLines: [liveLine('AQI 32 · good', 'AirNow')] }) // no `conditions`
    const chips = detailConditionChips(linesOnly)
    expect(chips).toHaveLength(1)
    expect(chips[0].kind).toBe('air')
    expect(chips[0].valueText).toBe('AQI 32')
  })

  it('is empty when the card carries neither conditions nor lines (silence is a state)', () => {
    expect(detailConditionChips(card())).toEqual([])
  })
})

describe('unchecked closures/permits never wear a present word (honesty regression)', () => {
  it('not-fetched / unavailable / no-data render as silence, never "closed"/"required"', () => {
    // Successor to the deleted EvidencePanel guard: an UNVERIFIED kind must
    // never read as a stated present fact (the live bug behind PR #251).
    const card = {
      id: 't',
      name: 'T',
      distanceMi: null,
      conditionLines: [],
      warnings: [],
      conditions: [
        { kind: 'closures', state: 'not-fetched' as const, source: '', checkedAgo: undefined },
        { kind: 'permits', state: 'unavailable' as const, source: 'Recreation.gov RIDB', checkedAgo: undefined },
        { kind: 'water', state: 'no-data' as const, source: 'USGS', checkedAgo: undefined },
      ],
    }
    const chips = detailConditionChips(card as never)
    const values = chips.map((c) => c.valueText.toLowerCase())
    expect(values.some((v) => v.includes('closed'))).toBe(false)
    expect(values.some((v) => v.includes('required'))).toBe(false)
    for (const chip of chips) expect(['unavailable', 'stale', 'fresh', 'pending']).toContain(chip.state)
  })
})

describe('heldBackChips — the blocked day still scans (AQI-276 live finding)', () => {
  const held = [
    { id: 'a', name: 'A', reasons: [{ text: 'air quality hazardous (AQI 276)', source: 'AirNow (EPA)', kind: 'air' }] },
    { id: 'b', name: 'B', reasons: [{ text: 'air quality hazardous (AQI 276)', source: 'AirNow (EPA)', kind: 'air' }] },
  ]
  it('derives one blocked-tinted chip per kind from the held-back reasons', () => {
    const chips = heldBackChips(held as never)
    expect(chips).toHaveLength(1)
    expect(chips[0].kind).toBe('air')
    expect(chips[0].valueText).toBe('AQI 276')
    expect(chips[0].tier).toBe('blocked')
    expect(chips[0].receipt?.source).toBeTruthy()
    // No timestamp exists on a held-back reason — none may be fabricated.
    expect(chips[0].receipt?.ageText).toBeUndefined()
  })
  it('is empty when nothing is held back (silence stays a state)', () => {
    expect(heldBackChips([])).toEqual([])
  })
})
