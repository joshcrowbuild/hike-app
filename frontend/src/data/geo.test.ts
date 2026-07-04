import { describe, expect, it } from 'vitest'

import {
  boundsOf,
  cumulativeDistances,
  deriveRouteShape,
  expandBounds,
  elevationAtFraction,
  flattenGeometry,
  haversineMeters,
  mappedLengthMeters,
  metersToFeet,
  nearestFractionToPoint,
  pointAtFraction,
  routeLengthMeters,
  summarizeProfile,
  trailheadDirectionsUrl,
} from './geo'
import type { ElevationSample, RouteGeometry } from './vm'

// A simple east-west line near the equator-ish; ~111 km per degree of lat,
// ~87 km per degree of lon at 38°N. We assert on ratios/ordering, not exact m.
const LINE: RouteGeometry = {
  type: 'LineString',
  coordinates: [
    [-78.4, 38.5],
    [-78.3, 38.5],
    [-78.3, 38.6],
  ],
}

describe('flattenGeometry', () => {
  it('returns LineString coordinates as-is', () => {
    expect(flattenGeometry(LINE)).toHaveLength(3)
  })

  it('concatenates MultiLineString segments in order', () => {
    const multi: RouteGeometry = {
      type: 'MultiLineString',
      coordinates: [
        [
          [-78.4, 38.5],
          [-78.3, 38.5],
        ],
        [
          [-78.2, 38.6],
          [-78.1, 38.6],
        ],
      ],
    }
    expect(flattenGeometry(multi)).toEqual([
      [-78.4, 38.5],
      [-78.3, 38.5],
      [-78.2, 38.6],
      [-78.1, 38.6],
    ])
  })
})

describe('haversineMeters', () => {
  it('is zero for identical points', () => {
    expect(haversineMeters([-78.4, 38.5], [-78.4, 38.5])).toBe(0)
  })

  it('measures ~111 km for one degree of latitude', () => {
    const d = haversineMeters([-78.4, 38.5], [-78.4, 39.5])
    expect(d).toBeGreaterThan(110_000)
    expect(d).toBeLessThan(112_000)
  })
})

describe('cumulativeDistances', () => {
  it('starts at 0 and increases monotonically', () => {
    const cum = cumulativeDistances(flattenGeometry(LINE))
    expect(cum).toHaveLength(3)
    expect(cum[0]).toBe(0)
    expect(cum[1]).toBeGreaterThan(0)
    expect(cum[2]).toBeGreaterThan(cum[1])
  })

  it('returns an empty array for no coordinates', () => {
    expect(cumulativeDistances([])).toEqual([])
  })
})

describe('routeLengthMeters', () => {
  it('equals the last cumulative distance', () => {
    const cum = cumulativeDistances(flattenGeometry(LINE))
    expect(routeLengthMeters(LINE)).toBeCloseTo(cum[cum.length - 1], 5)
  })
})

describe('mappedLengthMeters', () => {
  it('matches routeLengthMeters for a single LineString', () => {
    expect(mappedLengthMeters(LINE)).toBeCloseTo(routeLengthMeters(LINE), 5)
  })

  it('never counts the phantom connector between disjoint MultiLineString segments', () => {
    // Two far-apart segments: concatenating them (routeLengthMeters) adds a long
    // phantom jump; per-segment (mappedLengthMeters) does not.
    const multi: RouteGeometry = {
      type: 'MultiLineString',
      coordinates: [
        [[-78.4, 38.5], [-78.39, 38.5]],
        [[-78.2, 38.5], [-78.19, 38.5]],
      ],
    }
    expect(mappedLengthMeters(multi)).toBeLessThan(routeLengthMeters(multi))
  })
})

describe('deriveRouteShape', () => {
  it('reads a closed geometry as a loop', () => {
    const loop: RouteGeometry = {
      type: 'LineString',
      coordinates: [[-78.4, 38.5], [-78.395, 38.508], [-78.39, 38.5], [-78.4, 38.5]],
    }
    expect(deriveRouteShape(loop)).toBe('loop')
  })

  it('reads an open line as an out-and-back', () => {
    const open: RouteGeometry = {
      type: 'LineString',
      coordinates: [[-78.4, 38.5], [-78.39, 38.505], [-78.38, 38.51]],
    }
    expect(deriveRouteShape(open)).toBe('out-and-back')
  })

  it('returns null for a missing or undrawable route (degrade, never guess)', () => {
    expect(deriveRouteShape(null)).toBeNull()
    expect(deriveRouteShape({ type: 'LineString', coordinates: [[-78.4, 38.5]] })).toBeNull()
  })
})

describe('boundsOf', () => {
  it('spans the route, trailhead, and summit', () => {
    const [[minLon, minLat], [maxLon, maxLat]] = boundsOf({
      geometry: LINE,
      trailhead: { lat: 38.5, lon: -78.4 },
      summit: { lat: 38.7, lon: -78.25 },
    })
    expect(minLon).toBeCloseTo(-78.4)
    expect(maxLon).toBeCloseTo(-78.25)
    expect(minLat).toBeCloseTo(38.5)
    expect(maxLat).toBeCloseTo(38.7)
  })

  it('degenerates to the trailhead when geometry is null', () => {
    const b = boundsOf({ geometry: null, trailhead: { lat: 38.5, lon: -78.4 } })
    expect(b).toEqual([
      [-78.4, 38.5],
      [-78.4, 38.5],
    ])
  })
})

describe('expandBounds', () => {
  it('grows the box to include a fix far off the route', () => {
    const routeBounds = boundsOf({ geometry: LINE, trailhead: { lat: 38.5, lon: -78.4 } })
    // A viewer 100+ mi east and south of the trail — the plan-from-home case.
    const [[minLon, minLat], [maxLon, maxLat]] = expandBounds(routeBounds, { lat: 37.5, lon: -77.4 })
    expect(minLon).toBeCloseTo(-78.4)
    expect(maxLon).toBeCloseTo(-77.4)
    expect(minLat).toBeCloseTo(37.5)
    expect(maxLat).toBeCloseTo(38.6)
  })

  it('leaves the box unchanged when the fix is already inside it', () => {
    const routeBounds = boundsOf({ geometry: LINE, trailhead: { lat: 38.5, lon: -78.4 } })
    expect(expandBounds(routeBounds, { lat: 38.55, lon: -78.35 })).toEqual(routeBounds)
  })
})

describe('pointAtFraction', () => {
  it('returns the first point at fraction 0 and the last at 1', () => {
    expect(pointAtFraction(LINE, 0)).toEqual([-78.4, 38.5])
    expect(pointAtFraction(LINE, 1)).toEqual([-78.3, 38.6])
  })

  it('clamps out-of-range fractions', () => {
    expect(pointAtFraction(LINE, -5)).toEqual([-78.4, 38.5])
    expect(pointAtFraction(LINE, 5)).toEqual([-78.3, 38.6])
  })

  it('interpolates to a point strictly inside the route', () => {
    const [lon, lat] = pointAtFraction(LINE, 0.5)
    expect(lon).toBeGreaterThanOrEqual(-78.4)
    expect(lon).toBeLessThanOrEqual(-78.3)
    expect(lat).toBeGreaterThanOrEqual(38.5)
    expect(lat).toBeLessThanOrEqual(38.6)
  })
})

describe('nearestFractionToPoint', () => {
  it('snaps a point near the start to ~0', () => {
    expect(nearestFractionToPoint(LINE, [-78.4, 38.5])).toBeCloseTo(0, 2)
  })

  it('snaps a point near the end to ~1', () => {
    expect(nearestFractionToPoint(LINE, [-78.3, 38.6])).toBeCloseTo(1, 2)
  })

  it('projects an off-route point onto the nearest segment', () => {
    // Slightly north of the first (east-west) segment's midpoint → ~0.25 along.
    const f = nearestFractionToPoint(LINE, [-78.35, 38.51])
    expect(f).toBeGreaterThan(0)
    expect(f).toBeLessThan(0.5)
  })
})

describe('elevationAtFraction / summarizeProfile', () => {
  const samples: ElevationSample[] = [
    { distanceMeters: 0, elevationMeters: 100 },
    { distanceMeters: 100, elevationMeters: 200 },
    { distanceMeters: 200, elevationMeters: 150 },
  ]
  const profile = summarizeProfile(samples, 'USGS 3DEP', 10)

  it('computes gain, loss, and max grade', () => {
    expect(profile.totalGainMeters).toBe(100)
    expect(profile.totalLossMeters).toBe(50)
    // 100 m rise over 100 m run = 100% on the first leg.
    expect(profile.maxGradePercent).toBe(100)
    expect(profile.source).toBe('USGS 3DEP')
    expect(profile.resolutionMeters).toBe(10)
  })

  it('interpolates elevation at a mid fraction', () => {
    // Fraction 0.25 → 50 m along → halfway up the first leg → 150 m.
    expect(elevationAtFraction(profile, 0.25)).toBeCloseTo(150)
  })

  it('returns the endpoints at 0 and 1', () => {
    expect(elevationAtFraction(profile, 0)).toBe(100)
    expect(elevationAtFraction(profile, 1)).toBe(150)
  })
})

describe('metersToFeet', () => {
  it('converts metres to feet', () => {
    expect(metersToFeet(1000)).toBeCloseTo(3280.84, 1)
  })
})

describe('trailheadDirectionsUrl', () => {
  it('builds a driving deep-link to the trailhead coordinate', () => {
    const url = trailheadDirectionsUrl({ lat: 38.5928, lon: -78.3736 })
    expect(url).toContain('https://www.google.com/maps/dir/')
    expect(url).toContain('travelmode=driving')
    expect(url).toContain(encodeURIComponent('38.5928,-78.3736'))
  })
})
