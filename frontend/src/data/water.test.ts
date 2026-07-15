import { describe, expect, it } from 'vitest'

import type { TrailWaterVM, WaterSourceVM } from './vm'
import {
  formatWaterDistance,
  summarizeWaterCounts,
  waterHeadline,
  waterMarkerLabel,
  waterNote,
  waterTypeNoun,
} from './water'

const src = (over: Partial<WaterSourceVM> = {}): WaterSourceVM => ({
  id: 'water:osm:node/1',
  type: 'spring',
  lat: 38.5,
  lon: -78.4,
  distanceM: 64,
  ...over,
})

const vm = (over: Partial<TrailWaterVM> = {}): TrailWaterVM => ({
  state: 'sources',
  basis: 'route',
  radiusM: 200,
  source: 'OSM',
  sources: [src()],
  provenance: 'live',
  ...over,
})

describe('formatWaterDistance — rounded, never precision theater', () => {
  it('rounds sub-1000ft distances to 50 ft with the ~ hedge', () => {
    expect(formatWaterDistance(200)).toBe('~650 ft') // 656.2 ft
    expect(formatWaterDistance(64)).toBe('~200 ft') // 210 ft
  })
  it('floors at 50 ft so a 5 m distance never reads "~0 ft"', () => {
    expect(formatWaterDistance(5)).toBe('~50 ft')
  })
  it('switches to miles at ~1000 ft', () => {
    expect(formatWaterDistance(650)).toBe('~0.4 mi')
  })
})

describe('summarizeWaterCounts — grouped, ordered, pluralized', () => {
  it('orders springs first and pluralizes per type', () => {
    const out = summarizeWaterCounts([
      src({ type: 'water_tap' }),
      src({ type: 'spring' }),
      src({ type: 'spring' }),
    ])
    expect(out).toBe('2 springs, 1 tap')
  })
  it('names drinking_water as a category noun, never an adjective', () => {
    expect(summarizeWaterCounts([src({ type: 'drinking_water' })])).toBe('1 drinking-water point')
    expect(waterTypeNoun('drinking_water', 2)).toBe('drinking-water points')
  })
  it('degrades an unknown type to a generic noun instead of crashing', () => {
    expect(summarizeWaterCounts([src({ type: 'cistern' })])).toBe('1 water point')
  })
})

describe('waterHeadline — the answer, named to its basis', () => {
  it('states the answer with counts, radius, and the route basis (no prefix — the row label owns "Water")', () => {
    const out = waterHeadline(vm({ sources: [src(), src({ type: 'water_tap' })] }))
    expect(out).toBe('1 spring, 1 tap within ~650 ft of the route')
  })
  it('names the start basis when no route was drawable — never claims "route"', () => {
    expect(waterHeadline(vm({ basis: 'start' }))).toContain('of the start')
    expect(waterHeadline(vm({ basis: 'start' }))).not.toContain('route')
  })
  it('renders the answered-empty as a calm answer, not a warning', () => {
    const out = waterHeadline(vm({ state: 'none-nearby', sources: [] }))
    expect(out).toBe('No mapped water within ~650 ft of the route — carry what you need.')
  })

  it('treats an empty sources array as none-nearby even when state says "sources" (Epic 046 S4 AC-4.3 / D4) — never a leading-space fragment', () => {
    const out = waterHeadline(vm({ state: 'sources', sources: [] }))
    expect(out).toBe('No mapped water within ~650 ft of the route — carry what you need.')
    expect(out.startsWith(' ')).toBe(false)
  })
})

describe('waterNote — provenance hedge, no fabricated stamp, no potability claim', () => {
  it('always hedges that corpus water is not verified live', () => {
    expect(waterNote(vm())).toContain('not verified live')
    expect(waterNote(vm({ state: 'none-nearby', sources: [] }))).toContain('not verified live')
  })

  it('agrees with the headline\'s none-nearby reading for a "sources" state with an empty array (Epic 046 S4 AC-4.3 / D4)', () => {
    const out = waterNote(vm({ state: 'sources', sources: [] }))
    expect(out).toBe(waterNote(vm({ state: 'none-nearby', sources: [] })))
    expect(out).toContain('not verified live')
  })
  it('adds the seasonal hedge when a spring is present', () => {
    expect(waterNote(vm())).toContain('springs may be seasonal')
  })
  it('hedges seasonally-tagged non-springs without inventing springs', () => {
    const out = waterNote(vm({ sources: [src({ type: 'water_tap', seasonal: 'yes' })] }))
    expect(out).toContain('some may be seasonal')
    expect(out).not.toContain('springs')
  })
  it('omits the seasonal hedge for untagged non-springs', () => {
    expect(waterNote(vm({ sources: [src({ type: 'water_tap' })] }))).not.toContain('seasonal')
  })
  it('spells out the OSM attribution (ODbL) rather than the bare acronym only', () => {
    expect(waterNote(vm())).toContain('OpenStreetMap')
  })
  it('never claims potability in either direction', () => {
    for (const state of ['sources', 'none-nearby'] as const) {
      const text = (waterHeadline(vm({ state })) + waterNote(vm({ state }))).toLowerCase()
      for (const banned of ['potable', 'drinkable', 'safe']) {
        expect(text).not.toContain(banned)
      }
    }
  })
})

describe('waterMarkerLabel — an accessible name that carries the fact', () => {
  it('carries type, name, distance basis, seasonality, and source', () => {
    const label = waterMarkerLabel(src({ name: 'Furnace Spring', seasonal: 'yes' }), 'route')
    expect(label).toBe('Spring — Furnace Spring, about 200 ft from the route, may be seasonal · OSM')
  })
  it('stays whole without a name and marks springs seasonal by default', () => {
    expect(waterMarkerLabel(src(), 'start')).toBe(
      'Spring, about 200 ft from the start, may be seasonal · OSM',
    )
  })
  it('does not hedge a plain tap as seasonal', () => {
    expect(waterMarkerLabel(src({ type: 'water_tap' }), 'route')).toBe(
      'Tap, about 200 ft from the route · OSM',
    )
  })
})
