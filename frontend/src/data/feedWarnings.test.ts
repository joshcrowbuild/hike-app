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

describe('splitFeedWarnings (report #1: dedupe the region-wide alert wall; F1: never rewrite the card)', () => {
  it('hoists a warning shared across most cards to the banner and names its text as shared', () => {
    const shared = warning('weather alert: Extreme Heat Warning — NWS')
    const cards = [card('a', [shared]), card('b', [shared]), card('c', [shared])]

    const { banner, sharedTexts } = splitFeedWarnings(cards)

    expect(banner).toEqual([shared])
    expect(sharedTexts).toEqual(new Set([shared.text]))
  })

  it('leaves a trail-specific warning off the shared set, even alongside a hoisted one', () => {
    const shared = warning('weather alert: Extreme Heat Warning — NWS')
    const specific = warning('flash flood warning — creek crossing')
    const cards = [card('a', [shared, specific]), card('b', [shared]), card('c', [shared])]

    const { banner, sharedTexts } = splitFeedWarnings(cards)

    expect(banner).toEqual([shared])
    expect(sharedTexts.has(specific.text)).toBe(false)
  })

  it('never stacks two near-identical shared alerts — only the higher-severity one survives the banner, both count as shared', () => {
    const strong = warning('weather alert: Extreme Heat Warning — NWS')
    const weak = warning('weather alert: Heat Advisory — NWS')
    const cards = [card('a', [strong, weak]), card('b', [strong, weak])]

    const { banner, sharedTexts } = splitFeedWarnings(cards)

    expect(banner).toEqual([strong])
    // The weak near-duplicate is still shared (so no card re-renders it as its
    // own block) — it is simply not stacked in the banner.
    expect(sharedTexts).toEqual(new Set([strong.text, weak.text]))
  })

  it('does not hoist a warning that only one card carries, even in a small feed', () => {
    const lone = warning('flash flood warning — creek crossing')
    const cards = [card('a', [lone]), card('b', [])]

    const { banner, sharedTexts } = splitFeedWarnings(cards)

    expect(banner).toEqual([])
    expect(sharedTexts.size).toBe(0)
  })

  it('does not hoist the only warning on a single-card feed', () => {
    const only = warning('weather alert: Extreme Heat Warning — NWS')
    const cards = [card('a', [only])]

    const { banner, sharedTexts } = splitFeedWarnings(cards)

    expect(banner).toEqual([])
    expect(sharedTexts.size).toBe(0)
  })

  it('returns empty results for an empty feed', () => {
    expect(splitFeedWarnings([])).toEqual({ banner: [], sharedTexts: new Set() })
  })
})
