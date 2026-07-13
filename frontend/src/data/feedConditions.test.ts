import { describe, expect, it } from 'vitest'

import type { CardVM, ConditionStatusVM, LineVM } from './vm'
import { conditionStateKey, lineKey, splitFeedConditions } from './feedConditions'

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
