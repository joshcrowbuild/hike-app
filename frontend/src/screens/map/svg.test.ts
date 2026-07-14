import { describe, expect, it } from 'vitest'

import type { ElevationSample, RouteGeometry } from '../../data/vm'
import { fractionToX, profilePoints, profileScale, projectRoute, xToFraction, type Box } from './svg'

const BOX: Box = { width: 300, height: 100, padX: 10, padY: 10 }

const SAMPLES: ElevationSample[] = [
  { distanceMeters: 0, elevationMeters: 100 },
  { distanceMeters: 500, elevationMeters: 200 },
  { distanceMeters: 1000, elevationMeters: 150 },
]

describe('profileScale / profilePoints', () => {
  it('maps the first sample to the left and the highest sample to the top', () => {
    const pts = profilePoints(SAMPLES, BOX)
    expect(pts).toHaveLength(3)
    expect(pts[0][0]).toBe(10) // padX, distance 0
    expect(pts[2][0]).toBe(290) // width - padX, max distance
    // The 200 m sample is the peak → smallest y (top), inside the padding.
    const ys = pts.map((p) => p[1])
    expect(Math.min(...ys)).toBe(pts[1][1])
    expect(pts[1][1]).toBe(10) // padY (peak pinned to the top edge)
  })

  it('returns an empty list for no samples', () => {
    expect(profilePoints([], BOX)).toEqual([])
  })

  it('exposes a consistent distance/elevation scale', () => {
    const scale = profileScale(SAMPLES, BOX)
    expect(scale.maxD).toBe(1000)
    expect(scale.minE).toBe(100)
    expect(scale.maxE).toBe(200)
    expect(scale.x(0)).toBe(10)
    expect(scale.x(1000)).toBe(290)
  })

  it('with no minSpanMeters, the peak fills the frame regardless of its own real relief (the prior, auto-ranging behaviour)', () => {
    const pts = profilePoints(SAMPLES, BOX)
    expect(pts[1][1]).toBe(10) // padY — the 100 m relief is stretched to fill the box
  })

  it('minSpanMeters (H3, ux-review-craft 2026-07) floors the scale so small relief draws small', () => {
    // Real relief here is 100 m; a 1000 m reference means this profile only
    // occupies 1/10th of the available height instead of the full frame.
    const withFloor = profilePoints(SAMPLES, BOX, 1000)
    const withoutFloor = profilePoints(SAMPLES, BOX)
    const peakY = (pts: [number, number][]) => pts[1][1]
    // The peak sits much lower (larger y) in the floored version — it no
    // longer reaches the top of the frame the way the un-floored one does.
    expect(peakY(withFloor)).toBeGreaterThan(peakY(withoutFloor))
    expect(peakY(withoutFloor)).toBe(10) // padY — fills the frame
    expect(peakY(withFloor)).toBeGreaterThan(10) // floored — does not
  })

  it('a bigger relief than the floor still fills the frame — the floor only raises small relief, never clips large relief', () => {
    const bigRelief: ElevationSample[] = [
      { distanceMeters: 0, elevationMeters: 0 },
      { distanceMeters: 500, elevationMeters: 2000 },
    ]
    const pts = profilePoints(bigRelief, BOX, 100) // floor (100 m) « actual relief (2000 m)
    expect(pts[1][1]).toBe(10) // padY — still pinned to the top
  })
})

describe('fractionToX / xToFraction round-trip', () => {
  it('inverts within the padded inner width', () => {
    for (const f of [0, 0.25, 0.5, 0.75, 1]) {
      expect(xToFraction(fractionToX(f, BOX), BOX)).toBeCloseTo(f, 6)
    }
  })

  it('clamps out-of-range input', () => {
    expect(xToFraction(-50, BOX)).toBe(0)
    expect(xToFraction(9999, BOX)).toBe(1)
  })
})

describe('projectRoute', () => {
  const geometry: RouteGeometry = {
    type: 'LineString',
    coordinates: [
      [-78.4, 38.5],
      [-78.3, 38.55],
      [-78.2, 38.5],
    ],
  }

  it('fits every projected point inside the box', () => {
    const { route, trailhead, project } = projectRoute(geometry, { lat: 38.5, lon: -78.4 }, BOX)
    for (const [x, y] of [...route, trailhead, project([-78.3, 38.55])]) {
      expect(x).toBeGreaterThanOrEqual(0)
      expect(x).toBeLessThanOrEqual(BOX.width)
      expect(y).toBeGreaterThanOrEqual(0)
      expect(y).toBeLessThanOrEqual(BOX.height)
    }
  })

  it('returns an empty route but a placed trailhead when geometry is null', () => {
    const { route, trailhead } = projectRoute(null, { lat: 38.5, lon: -78.4 }, BOX)
    expect(route).toEqual([])
    expect(trailhead[0]).toBeGreaterThanOrEqual(0)
    expect(trailhead[1]).toBeGreaterThanOrEqual(0)
  })
})
