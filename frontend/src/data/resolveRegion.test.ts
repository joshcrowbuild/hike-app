import { describe, expect, it } from 'vitest'

import type { OriginOption } from './regionsCatalog'
import { resolveRegionLabel } from './resolveRegion'
import type { CardVM } from './vm'
import type { TuningState } from '../types'

const TUNING: TuningState = {
  origin: 'frontRoyal',
  when: 'weekendMorning',
  effort: 'moderate',
  party: 'solo',
  today: 'standard',
  readinessOn: false,
  prompt: '',
}

// A small origins fixture standing in for the fetched region catalog (Phase 2:
// config-driven — resolveRegionLabel takes it as a parameter rather than
// importing a static map).
const ORIGINS: OriginOption[] = [
  { key: 'frontRoyal', label: 'Front Royal', lat: 38.918, lon: -78.194, regionLabel: 'Shenandoah' },
  { key: 'richmond', label: 'Richmond', lat: 37.5407, lon: -77.436, regionLabel: 'Richmond' },
  { key: 'duck', label: 'Duck', lat: 36.166, lon: -75.75, regionLabel: 'Outer Banks' },
]
const FRONT_ROYAL = ORIGINS[0]
const DUCK = ORIGINS[2]

function cardAt(id: string, lat: number, lon: number): CardVM {
  return {
    id,
    name: id,
    distanceMi: 2,
    conditionLines: [],
    warnings: [],
    geo: { geometry: null, trailhead: { lat, lon }, quality: 'confident', elevationProfile: null },
  }
}

function cardWithNoGeo(id: string): CardVM {
  return { id, name: id, distanceMi: 2, conditionLines: [], warnings: [] }
}

describe('resolveRegionLabel (report #3: never display a region that contradicts the results)', () => {
  it('derives the region from the served trailheads, not the picker\'s assumption', () => {
    // Picked Nags Head (Outer Banks) but every served trail actually sits at
    // the Front Royal / Shenandoah coordinate — the label must say so.
    const tuning: TuningState = { ...TUNING, origin: 'nagsHead' }
    const cards = [cardAt('a', FRONT_ROYAL.lat, FRONT_ROYAL.lon)]

    expect(resolveRegionLabel(cards, tuning, ORIGINS)).toBe('Shenandoah')
  })

  it('shows the region the results are actually in, regardless of the picked origin', () => {
    const cards = [cardAt('a', DUCK.lat, DUCK.lon)]

    // TUNING.origin is frontRoyal (Shenandoah), but the served trail is on the
    // Outer Banks — the label must follow the trail, not the picker.
    expect(resolveRegionLabel(cards, TUNING, ORIGINS)).toBe('Outer Banks')
  })

  it('takes the majority region when served trailheads span more than one area', () => {
    const cards = [
      cardAt('a', FRONT_ROYAL.lat, FRONT_ROYAL.lon),
      cardAt('b', FRONT_ROYAL.lat, FRONT_ROYAL.lon),
      cardAt('c', DUCK.lat, DUCK.lon),
    ]

    expect(resolveRegionLabel(cards, TUNING, ORIGINS)).toBe('Shenandoah')
  })

  it('falls back to the queried origin when no served card discloses a coordinate', () => {
    const tuning: TuningState = { ...TUNING, origin: 'richmond' }
    expect(resolveRegionLabel([cardWithNoGeo('a')], tuning, ORIGINS)).toBe('Richmond')
  })

  it('falls back to "Near you" for a geolocation fix when no card discloses a coordinate', () => {
    const tuning: TuningState = { ...TUNING, originCoords: { lat: 38.9, lon: -78.2 } }
    expect(resolveRegionLabel([cardWithNoGeo('a')], tuning, ORIGINS)).toBe('Near you')
  })
})
