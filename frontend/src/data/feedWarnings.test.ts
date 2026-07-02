import { describe, expect, it } from 'vitest'

import type { CardVM, WarningVM } from './vm'
import { splitFeedWarnings, warningSeverity } from './feedWarnings'

function warning(text: string, over: Partial<WarningVM> = {}): WarningVM {
  return { text, source: 'NWS api.weather.gov', observedAgo: '2h ago', kind: 'weather', provenance: 'live', ...over }
}

function card(id: string, warnings: WarningVM[]): CardVM {
  return { id, name: id, distanceMi: 2, conditionLines: [], warnings }
}

describe('warningSeverity', () => {
  it('ranks Warning above Watch above Advisory above unrecognized text', () => {
    expect(warningSeverity('Extreme Heat Warning')).toBeGreaterThan(warningSeverity('Heat Watch'))
    expect(warningSeverity('Heat Watch')).toBeGreaterThan(warningSeverity('Heat Advisory'))
    expect(warningSeverity('Heat Advisory')).toBeGreaterThan(warningSeverity('Trail closed for maintenance'))
  })
})

describe('splitFeedWarnings (report #1: dedupe the region-wide alert wall)', () => {
  it('hoists a warning shared across most cards to the banner and clears it off every card', () => {
    const shared = warning('weather alert: Extreme Heat Warning — NWS')
    const cards = [card('a', [shared]), card('b', [shared]), card('c', [shared])]

    const { banner, perCard } = splitFeedWarnings(cards)

    expect(banner).toEqual([shared])
    for (const c of cards) expect(perCard.get(c.id)).toEqual([])
  })

  it('leaves a trail-specific warning on its own card untouched, even alongside a hoisted one', () => {
    const shared = warning('weather alert: Extreme Heat Warning — NWS')
    const specific = warning('flash flood warning — creek crossing')
    const cards = [card('a', [shared, specific]), card('b', [shared]), card('c', [shared])]

    const { banner, perCard } = splitFeedWarnings(cards)

    expect(banner).toEqual([shared])
    expect(perCard.get('a')).toEqual([specific])
    expect(perCard.get('b')).toEqual([])
  })

  it('never stacks two near-identical shared alerts — only the higher-severity one survives', () => {
    const strong = warning('weather alert: Extreme Heat Warning — NWS')
    const weak = warning('weather alert: Heat Advisory — NWS')
    const cards = [card('a', [strong, weak]), card('b', [strong, weak])]

    const { banner, perCard } = splitFeedWarnings(cards)

    expect(banner).toEqual([strong])
    expect(perCard.get('a')).toEqual([])
    expect(perCard.get('b')).toEqual([])
  })

  it('does not hoist a warning that only one card carries, even in a small feed', () => {
    const lone = warning('flash flood warning — creek crossing')
    const cards = [card('a', [lone]), card('b', [])]

    const { banner, perCard } = splitFeedWarnings(cards)

    expect(banner).toEqual([])
    expect(perCard.get('a')).toEqual([lone])
  })

  it('does not hoist the only warning on a single-card feed', () => {
    const only = warning('weather alert: Extreme Heat Warning — NWS')
    const cards = [card('a', [only])]

    const { banner, perCard } = splitFeedWarnings(cards)

    expect(banner).toEqual([])
    expect(perCard.get('a')).toEqual([only])
  })

  it('returns empty results for an empty feed', () => {
    expect(splitFeedWarnings([])).toEqual({ banner: [], perCard: new Map() })
  })
})
