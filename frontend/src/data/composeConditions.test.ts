import { describe, expect, it } from 'vitest'

import { composeConditions } from './composeConditions'
import type { CardVM, ConditionsPatchVM, ConditionStatusVM, FeedVM, RegionConditionsVM } from './vm'

const NOT_FETCHED: ConditionStatusVM[] = [
  { kind: 'weather', state: 'not-fetched' },
  { kind: 'air', state: 'not-fetched' },
]

function card(id: string): CardVM {
  return {
    id,
    name: id.toUpperCase(),
    distanceMi: 3,
    conditionLines: [],
    conditions: [...NOT_FETCHED],
    warnings: [],
  }
}

function phase1(ids: string[]): FeedVM {
  return {
    query: '',
    cards: ids.map(card),
    notices: ['Drive times unavailable'],
    setAside: [],
    heldBack: [],
    readiness: { on: false, state: 'off' },
    dataSource: 'live',
    conditionsPending: true,
  }
}

const WEATHER_PRESENT: ConditionStatusVM[] = [
  { kind: 'weather', state: 'present', source: 'NWS', checkedAgo: 'just now' },
  { kind: 'air', state: 'no-data', source: 'AirNow', checkedAgo: 'just now' },
]

describe('composeConditions (Epic 040 S3 — in place, remove-never-reorder)', () => {
  it('patches condition fields onto cards in place without changing order', () => {
    const patch: ConditionsPatchVM = {
      patches: [
        {
          id: 'b',
          conditionLines: [
            { text: 'Clear skies', source: 'nws', confidence: 'stated', provenance: 'live', sources: ['NWS'] },
          ],
          conditions: WEATHER_PRESENT,
          warnings: [],
        },
      ],
      heldBack: [],
    }
    const composed = composeConditions(phase1(['a', 'b', 'c']), patch)

    expect(composed.cards.map((c) => c.id)).toEqual(['a', 'b', 'c']) // order untouched
    expect(composed.cards[1].conditionLines[0].text).toBe('Clear skies')
    expect(composed.cards[1].conditions).toEqual(WEATHER_PRESENT)
    // Feed-level identity fields ride through unchanged.
    expect(composed.notices).toEqual(['Drive times unavailable'])
    expect(composed.conditionsPending).toBeUndefined() // composed = complete
  })

  it('removes a held-back card and discloses it — never reorders the rest', () => {
    const patch: ConditionsPatchVM = {
      patches: [],
      heldBack: [
        { id: 'b', name: 'B', reasons: [{ text: 'air quality hazardous (AirNow)', source: 'AirNow', kind: 'air' }] },
      ],
    }
    const composed = composeConditions(phase1(['a', 'b', 'c']), patch)

    expect(composed.cards.map((c) => c.id)).toEqual(['a', 'c'])
    expect(composed.heldBack.map((h) => h.id)).toEqual(['b'])
    expect(composed.heldBack[0].reasons[0].source).toBe('AirNow')
  })

  it('keeps honest not-fetched silence for a card the patch does not cover', () => {
    const patch: ConditionsPatchVM = { patches: [], heldBack: [] }
    const composed = composeConditions(phase1(['a']), patch)

    // No patch entry → the card keeps its phase-1 silence, never a guess.
    expect(composed.cards[0].conditions).toEqual(NOT_FETCHED)
    expect(composed.cards[0].conditionLines).toEqual([])
  })

  it('appends patch heldBack after existing feed-level heldBack (both disclosed)', () => {
    const base = phase1(['a', 'b'])
    base.heldBack = [{ id: 'x', name: 'X', reasons: [{ text: 'earlier', source: 's', kind: 'air' }] }]
    const patch: ConditionsPatchVM = {
      patches: [],
      heldBack: [{ id: 'b', name: 'B', reasons: [{ text: 'later', source: 's', kind: 'air' }] }],
    }
    const composed = composeConditions(base, patch)
    expect(composed.heldBack.map((h) => h.id)).toEqual(['x', 'b'])
  })
})

describe('composeConditions divergent-payload guard', () => {
  it('keeps the phase-1 per-kind states when a patch entry carries none', () => {
    const patch: ConditionsPatchVM = {
      patches: [{ id: 'a', conditionLines: [], conditions: undefined, warnings: [] }],
      heldBack: [],
    }
    const composed = composeConditions(phase1(['a']), patch)
    // Never trade real silence for a blank: the honest not-fetched states stay.
    expect(composed.cards[0].conditions).toEqual(NOT_FETCHED)
  })
})

describe('composeConditions — regionConditions/personalizationDegraded (Epic 056 S3 AC-3.2/3.3)', () => {
  const REGION_CONDITIONS: RegionConditionsVM = {
    forecast: { days: [{ key: 'today', label: 'Today', highF: 70, precipPct: 10 }], targetKey: 'today', source: 'NWS' },
    recentPrecip: null,
    mud: null,
  }

  it('the patch wins when it carries a regionConditions value', () => {
    const base = phase1(['a'])
    const patch: ConditionsPatchVM = { patches: [], heldBack: [], regionConditions: REGION_CONDITIONS }
    const composed = composeConditions(base, patch)
    expect(composed.regionConditions).toBe(REGION_CONDITIONS)
  })

  it('an explicit null on the patch (a real "unavailable" signal) still wins over a phase-1 value', () => {
    const base: FeedVM = { ...phase1(['a']), regionConditions: REGION_CONDITIONS }
    const patch: ConditionsPatchVM = { patches: [], heldBack: [], regionConditions: null }
    const composed = composeConditions(base, patch)
    expect(composed.regionConditions).toBeNull()
  })

  it('falls back to the phase-1 value when the patch genuinely omits the field', () => {
    const base: FeedVM = { ...phase1(['a']), regionConditions: REGION_CONDITIONS }
    const patch: ConditionsPatchVM = { patches: [], heldBack: [] }
    const composed = composeConditions(base, patch)
    expect(composed.regionConditions).toBe(REGION_CONDITIONS)
  })

  it('the patch wins for personalizationDegraded, including flipping true→false', () => {
    const base: FeedVM = { ...phase1(['a']), personalizationDegraded: true }
    const patch: ConditionsPatchVM = { patches: [], heldBack: [], personalizationDegraded: false }
    const composed = composeConditions(base, patch)
    expect(composed.personalizationDegraded).toBe(false)
  })

  it('falls back to the phase-1 personalizationDegraded when the patch omits it', () => {
    const base: FeedVM = { ...phase1(['a']), personalizationDegraded: true }
    const patch: ConditionsPatchVM = { patches: [], heldBack: [] }
    const composed = composeConditions(base, patch)
    expect(composed.personalizationDegraded).toBe(true)
  })
})
