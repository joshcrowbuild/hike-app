import { describe, expect, it } from 'vitest'

import type { CardVM, ConditionStatusVM, LineVM } from './vm'
import {
  conditionStateKey,
  foldLineValue,
  lineKey,
  providerShort,
  splitFeedConditions,
  unclaimedLines,
} from './feedConditions'

const line = (over: Partial<LineVM> = {}): LineVM => ({
  text: 'Mostly Cloudy 61°F · NWS, just now',
  source: 'NWS api.weather.gov',
  confidence: 'stated',
  provenance: 'live',
  ...over,
})

const status = (over: Partial<ConditionStatusVM> = {}): ConditionStatusVM => ({
  kind: 'fire',
  state: 'no-hazard',
  source: 'NASA FIRMS',
  checkedAgo: 'just now',
  ...over,
})

function card(id: string, over: Partial<CardVM> = {}): CardVM {
  return { id, name: id, distanceMi: 2, conditionLines: [], warnings: [], ...over }
}

describe('splitFeedConditions (F3: region-scope facts stated once, per-trail deltas stay on cards)', () => {
  it('hoists a verbatim-identical condition line shared across most cards', () => {
    const weather = line()
    const cards = [
      card('a', { conditionLines: [weather] }),
      card('b', { conditionLines: [weather] }),
      card('c', { conditionLines: [weather] }),
    ]

    const { sharedLines, sharedLineKeys } = splitFeedConditions(cards)

    expect(sharedLines).toEqual([weather])
    expect(sharedLineKeys).toEqual(new Set([lineKey(weather)]))
  })

  it('keeps a differing reading on its own card — a microclimate delta is never averaged away', () => {
    const modal = line()
    const delta = line({ text: 'Mostly Cloudy 64°F · NWS, just now' })
    const cards = [
      card('a', { conditionLines: [modal] }),
      card('b', { conditionLines: [modal] }),
      card('c', { conditionLines: [delta] }),
    ]

    const { sharedLines, sharedLineKeys } = splitFeedConditions(cards)

    expect(sharedLines).toEqual([modal])
    expect(sharedLineKeys.has(lineKey(delta))).toBe(false)
  })

  it('hoists identical silent-state dispositions (checked-clear, couldn’t-verify, not-checked) shared across most cards', () => {
    const fireClear = status()
    const airOut = status({ kind: 'air', state: 'unavailable', source: undefined, checkedAgo: undefined })
    const closuresQuiet = status({ kind: 'closures', state: 'not-fetched', source: undefined, checkedAgo: undefined })
    const conditions = [fireClear, airOut, closuresQuiet]
    const cards = [card('a', { conditions }), card('b', { conditions }), card('c', { conditions })]

    const { sharedStates, sharedStateKeys } = splitFeedConditions(cards)

    expect(sharedStates).toEqual(conditions)
    expect(sharedStateKeys).toEqual(new Set(conditions.map(conditionStateKey)))
  })

  it('never hoists value-bearing states — present/stale ride their condition lines, not the state list', () => {
    const present = status({ kind: 'weather', state: 'present', source: 'NWS' })
    const stale = status({ kind: 'water', state: 'stale-degraded', source: 'USGS', checkedAgo: '3h ago' })
    const cards = [
      card('a', { conditions: [present, stale] }),
      card('b', { conditions: [present, stale] }),
    ]

    const { sharedStates } = splitFeedConditions(cards)

    expect(sharedStates).toEqual([])
  })

  it('keeps a per-trail state on its card — a closure on THIS trail is a delta, not region scope', () => {
    const shared = status()
    const own = status({ kind: 'closures', state: 'no-data', source: 'NPS', detail: 'outside NPS range' })
    const cards = [
      card('a', { conditions: [shared, own] }),
      card('b', { conditions: [shared] }),
      card('c', { conditions: [shared] }),
    ]

    const { sharedStates, sharedStateKeys } = splitFeedConditions(cards)

    expect(sharedStates).toEqual([shared])
    expect(sharedStateKeys.has(conditionStateKey(own))).toBe(false)
  })

  it('hoists neither side of an exact-half disposition tie — a ribbon never contradicts itself (M1)', () => {
    // 2 cards fire checked-clear + 2 cards fire couldn't-verify: at >= 0.5 both
    // would hoist, and the ribbon's checked-clear would hang over the two cards
    // whose fire probe actually failed while their own rows were suppressed.
    const fireClear = status()
    const fireOut = status({ state: 'unavailable', source: undefined, checkedAgo: undefined })
    const cards = [
      card('a', { conditions: [fireClear] }),
      card('b', { conditions: [fireClear] }),
      card('c', { conditions: [fireOut] }),
      card('d', { conditions: [fireOut] }),
    ]

    const { sharedStates, sharedStateKeys } = splitFeedConditions(cards)

    expect(sharedStates).toEqual([])
    expect(sharedStateKeys.size).toBe(0)
  })

  it('hoists neither of two exact-half-tied readings — one area, one stated sky', () => {
    const north = line({ text: 'Sunny 60°F · NWS, just now' })
    const south = line({ text: 'Rain 55°F · NWS, just now' })
    const cards = [
      card('a', { conditionLines: [north] }),
      card('b', { conditionLines: [north] }),
      card('c', { conditionLines: [south] }),
      card('d', { conditionLines: [south] }),
    ]

    const { sharedLines } = splitFeedConditions(cards)

    expect(sharedLines).toEqual([])
  })

  it('treats near-identical dispositions as distinct — the key carries source, age and detail', () => {
    const fresh = status({ checkedAgo: 'just now' })
    const older = status({ checkedAgo: '2h ago' })
    const cards = [card('a', { conditions: [fresh] }), card('b', { conditions: [older] })]

    const { sharedStates } = splitFeedConditions(cards)

    // Hoisting "just now" as the region stamp over a card whose own answer is
    // 2h old would fabricate freshness — verbatim-identical only.
    expect(sharedStates).toEqual([])
  })

  it('hoists nothing from a single-card feed', () => {
    const cards = [card('a', { conditionLines: [line()], conditions: [status()] })]

    const split = splitFeedConditions(cards)

    expect(split.sharedLines).toEqual([])
    expect(split.sharedStates).toEqual([])
  })

  it('returns empty results for an empty feed', () => {
    const split = splitFeedConditions([])
    expect(split.sharedLines).toEqual([])
    expect(split.sharedStates).toEqual([])
    expect(split.sharedLineKeys.size).toBe(0)
    expect(split.sharedStateKeys.size).toBe(0)
  })

  it('counts a repeated line once per card so one card cannot vote a text into region scope', () => {
    const weather = line()
    const cards = [card('a', { conditionLines: [weather, weather] }), card('b', { conditionLines: [] }), card('c', { conditionLines: [] })]

    const { sharedLines } = splitFeedConditions(cards)

    expect(sharedLines).toEqual([])
  })
})

describe('foldLineValue / unclaimedLines (ux-review 2026-07 Finding 4/7 — Detail states each condition once)', () => {
  it('folds a present row\'s matching-source line and marks it claimed', () => {
    const weather = line({ text: 'Sunny 90°F', source: 'NWS' })
    const claimed = new Set<LineVM>()
    const match = foldLineValue(status({ kind: 'weather', state: 'present', source: 'NWS' }), [weather], claimed)
    expect(match).toBe(weather)
    expect(claimed.has(weather)).toBe(true)
  })

  it('folds a FULL line source against a SHORT status source via the shared short-provider identity (Epic 046 S1 AC-1.2 — the regression that would have caught A1)', () => {
    // A1's live-data defect: engine.py sets the status source to the SHORT name
    // (`provider_short(fact.source)` → "NWS") while present.py sets the line
    // source to the FULL label — a naive `line.source === status.source`
    // compare NEVER matches on live data, so this MUST still fold.
    const weather = line({
      text: 'Sunny 90°F · NWS, just now',
      source: 'NWS api.weather.gov · single authoritative source (NWS LWX 56,65)',
    })
    const claimed = new Set<LineVM>()
    const match = foldLineValue(status({ kind: 'weather', state: 'present', source: 'NWS' }), [weather], claimed)
    expect(match).toBe(weather)
    expect(claimed.has(weather)).toBe(true)
  })

  it('folds a stale-degraded row the same way as present', () => {
    const weather = line({ text: 'Sunny 90°F', source: 'NWS' })
    const match = foldLineValue(
      status({ kind: 'weather', state: 'stale-degraded', source: 'NWS' }),
      [weather],
      new Set(),
    )
    expect(match).toBe(weather)
  })

  it('never folds for no-hazard/no-data/unavailable/not-fetched — those states carry no value', () => {
    const weather = line({ text: 'Sunny 90°F', source: 'NWS' })
    for (const state of ['no-hazard', 'no-data', 'unavailable', 'not-fetched'] as const) {
      expect(foldLineValue(status({ kind: 'weather', state, source: 'NWS' }), [weather], new Set())).toBeUndefined()
    }
  })

  it('matches by source, not position — order-independent', () => {
    const air = line({ text: 'AQI 45 (Good)', source: 'EPA' })
    const weather = line({ text: 'Sunny 90°F', source: 'NWS' })
    const match = foldLineValue(status({ kind: 'weather', state: 'present', source: 'NWS' }), [air, weather], new Set())
    expect(match).toBe(weather)
  })

  it('a source with no matching line folds nothing — never fabricates a value', () => {
    const air = line({ text: 'AQI 45 (Good)', source: 'EPA' })
    expect(foldLineValue(status({ kind: 'weather', state: 'present', source: 'NWS' }), [air], new Set())).toBeUndefined()
  })

  it('a repeated source is exhausted by the first claim — a second row sharing it gets no match', () => {
    const weather = line({ text: 'Sunny 90°F', source: 'NWS' })
    const claimed = new Set<LineVM>()
    const first = foldLineValue(status({ kind: 'weather', state: 'present', source: 'NWS' }), [weather], claimed)
    const second = foldLineValue(status({ kind: 'fire', state: 'present', source: 'NWS' }), [weather], claimed)
    expect(first).toBe(weather)
    expect(second).toBeUndefined()
  })

  it('unclaimedLines returns lines no condition row claimed, in original order', () => {
    const weather = line({ text: 'Sunny 90°F', source: 'NWS' })
    const air = line({ text: 'AQI 45 (Good)', source: 'EPA' })
    const conditions = [status({ kind: 'weather', state: 'present', source: 'NWS' })]
    expect(unclaimedLines(conditions, [weather, air])).toEqual([air])
  })

  it('unclaimedLines returns everything when no condition kind matches any line', () => {
    const weather = line({ text: 'Sunny 90°F', source: 'NWS' })
    const conditions = [status({ kind: 'fire', state: 'no-hazard', source: 'NASA FIRMS' })]
    expect(unclaimedLines(conditions, [weather])).toEqual([weather])
  })

  it('unclaimedLines returns nothing when every line is claimed', () => {
    const weather = line({ text: 'Sunny 90°F', source: 'NWS' })
    const conditions = [status({ kind: 'weather', state: 'present', source: 'NWS' })]
    expect(unclaimedLines(conditions, [weather])).toEqual([])
  })

  it('unclaimedLines returns [] for a normal live payload — the fold covers every kind (AC-1.3)', () => {
    // A realistic live shape: FULL line sources against SHORT status sources,
    // one kind each — no residual list should ever surface for this shape.
    const weather = line({
      text: 'Sunny 90°F · NWS, just now',
      source: 'NWS api.weather.gov · single authoritative source (NWS LWX 56,65)',
    })
    const air = line({
      text: 'AQI 45 (Good) · AirNow, just now',
      source: 'AirNow · single aggregated source',
    })
    const conditions = [
      status({ kind: 'weather', state: 'present', source: 'NWS' }),
      status({ kind: 'air', state: 'present', source: 'AirNow' }),
    ]
    expect(unclaimedLines(conditions, [weather, air])).toEqual([])
  })
})

describe('providerShort (Epic 046 S1 AC-1.2 — the shared identity the fold matches on)', () => {
  it('takes the leading token of a full source label', () => {
    expect(providerShort('NWS api.weather.gov · single authoritative source (NWS LWX 56,65)')).toBe('NWS')
  })

  it('is a no-op on an already-short source', () => {
    expect(providerShort('NWS')).toBe('NWS')
  })

  it('falls back to the input for an empty string', () => {
    expect(providerShort('')).toBe('')
  })
})
