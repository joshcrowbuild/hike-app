import { describe, expect, it } from 'vitest'

import { orderOrigins, type OriginOption } from './regionsCatalog'

// Deliberately NOT in alphabetical or proximity order in the fixture, so a
// passing test can't be an accident of insertion order (mirrors the real
// per-region geojson origin arrays, which aren't alphabetical either).
const ORIGINS: OriginOption[] = [
  { key: 'luray', label: 'Luray', lat: 38.665, lon: -78.459, regionLabel: 'Shenandoah' },
  { key: 'frontRoyal', label: 'Front Royal', lat: 38.918, lon: -78.194, regionLabel: 'Shenandoah' },
  {
    key: 'charlottesville',
    label: 'Charlottesville',
    lat: 38.029,
    lon: -78.477,
    regionLabel: 'Shenandoah',
  },
]

describe('orderOrigins', () => {
  it('orders alphabetically by label when no location is available (default)', () => {
    expect(orderOrigins(ORIGINS).map((o) => o.label)).toEqual(['Charlottesville', 'Front Royal', 'Luray'])
  })

  it('orders nearest-first by haversine distance once a location is available', () => {
    // A fix right on top of Front Royal — Luray is the next-closest of the
    // three (Charlottesville sits furthest south, well past Luray).
    const location = { lat: 38.918, lon: -78.194 }
    expect(orderOrigins(ORIGINS, location).map((o) => o.label)).toEqual([
      'Front Royal',
      'Luray',
      'Charlottesville',
    ])
  })

  it('re-orders when the location is nearer a different origin', () => {
    // A fix right on top of Charlottesville flips the order versus the
    // Front-Royal-anchored case above — proof this is live proximity math,
    // not a fixed priority list.
    const location = { lat: 38.029, lon: -78.477 }
    expect(orderOrigins(ORIGINS, location).map((o) => o.label)).toEqual([
      'Charlottesville',
      'Luray',
      'Front Royal',
    ])
  })

  it('falls back to alphabetical gracefully — never mutates the input array', () => {
    const copy = [...ORIGINS]
    orderOrigins(ORIGINS)
    expect(ORIGINS).toEqual(copy)
  })
})
