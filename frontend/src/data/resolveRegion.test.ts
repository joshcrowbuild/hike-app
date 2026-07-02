import { describe, expect, it } from 'vitest'

import { originCoords } from './origins'
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
    const cards = [cardAt('a', originCoords.frontRoyal.lat, originCoords.frontRoyal.lon)]

    expect(resolveRegionLabel(cards, tuning)).toBe('Shenandoah')
  })

  it('shows the region the results are actually in, regardless of the picked origin', () => {
    const cards = [cardAt('a', originCoords.duck.lat, originCoords.duck.lon)]

    // TUNING.origin is frontRoyal (Shenandoah), but the served trail is on the
    // Outer Banks — the label must follow the trail, not the picker.
    expect(resolveRegionLabel(cards, TUNING)).toBe('Outer Banks')
  })

  it('takes the majority region when served trailheads span more than one area', () => {
    const cards = [
      cardAt('a', originCoords.frontRoyal.lat, originCoords.frontRoyal.lon),
      cardAt('b', originCoords.frontRoyal.lat, originCoords.frontRoyal.lon),
      cardAt('c', originCoords.duck.lat, originCoords.duck.lon),
    ]

    expect(resolveRegionLabel(cards, TUNING)).toBe('Shenandoah')
  })

  it('falls back to the queried origin when no served card discloses a coordinate', () => {
    const tuning: TuningState = { ...TUNING, origin: 'richmond' }
    expect(resolveRegionLabel([cardWithNoGeo('a')], tuning)).toBe('Richmond')
  })

  it('falls back to "Near you" for a geolocation fix when no card discloses a coordinate', () => {
    const tuning: TuningState = { ...TUNING, originCoords: { lat: 38.9, lon: -78.2 } }
    expect(resolveRegionLabel([cardWithNoGeo('a')], tuning)).toBe('Near you')
  })
})
