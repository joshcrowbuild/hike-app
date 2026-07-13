import { describe, expect, it } from 'vitest'

import { groupOrigins, orderOrigins, type OriginOption, type RegionCatalogEntry } from './regionsCatalog'

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

// A two-region catalog, deliberately unsorted within each region, plus an
// empty region (a region file with no named origins yet) to prove it drops.
const REGIONS: RegionCatalogEntry[] = [
  { regionId: 'shenandoah-gwj', label: 'Shenandoah', origins: ORIGINS },
  { regionId: 'no-origins-yet', label: 'Empty Region', origins: [] },
  {
    regionId: 'outer-banks',
    label: 'Outer Banks',
    origins: [
      { key: 'nagsHead', label: 'Nags Head', lat: 35.957, lon: -75.624, regionLabel: 'Outer Banks' },
      { key: 'duck', label: 'Duck', lat: 36.166, lon: -75.75, regionLabel: 'Outer Banks' },
    ],
  },
]

describe('groupOrigins (craft review C1 — the picker gets scannable structure)', () => {
  it('keeps catalog region order and sorts alphabetically within each region when no location exists', () => {
    const groups = groupOrigins(REGIONS)
    expect(groups.map((g) => g.label)).toEqual(['Shenandoah', 'Outer Banks'])
    expect(groups[0].origins.map((o) => o.label)).toEqual(['Charlottesville', 'Front Royal', 'Luray'])
    expect(groups[1].origins.map((o) => o.label)).toEqual(['Duck', 'Nags Head'])
  })

  it('drops regions with no origins — a header with nothing to pick is noise', () => {
    expect(groupOrigins(REGIONS).some((g) => g.regionId === 'no-origins-yet')).toBe(false)
  })

  it('re-ranks regions by their nearest origin and origins within a region by distance once a fix lands', () => {
    // A fix right on top of Duck: Outer Banks leads, Duck before Nags Head;
    // within Shenandoah, Charlottesville (southernmost) is nearest the coast,
    // Front Royal (northernmost) furthest — proof both levels re-rank.
    const groups = groupOrigins(REGIONS, { lat: 36.166, lon: -75.75 })
    expect(groups.map((g) => g.label)).toEqual(['Outer Banks', 'Shenandoah'])
    expect(groups[0].origins.map((o) => o.label)).toEqual(['Duck', 'Nags Head'])
    expect(groups[1].origins.map((o) => o.label)).toEqual(['Charlottesville', 'Luray', 'Front Royal'])
  })

  it('never mutates the catalog it groups', () => {
    const regionOrder = REGIONS.map((r) => r.regionId)
    const shenandoahOrder = REGIONS[0].origins.map((o) => o.key)
    groupOrigins(REGIONS, { lat: 36.166, lon: -75.75 })
    expect(REGIONS.map((r) => r.regionId)).toEqual(regionOrder)
    expect(REGIONS[0].origins.map((o) => o.key)).toEqual(shenandoahOrder)
  })
})
