/**
 * Pure geometry + elevation math over the Epic 016/017 contract shapes. No
 * React, no map library — just the domain functions the map, the elevation
 * profile, and the mock fixtures all share, so the heavy lifting is unit-tested
 * once and the map component stays thin. Coordinates are GeoJSON order
 * (`[lon, lat]`, WGS84) throughout, matching the wire contract.
 */
import type { ElevationProfile, ElevationSample, GeoPosition, RouteGeometry } from './vm'

/** Mean Earth radius (m), IUGG. */
const EARTH_RADIUS_M = 6371008.8
const toRad = (deg: number): number => (deg * Math.PI) / 180

export const metersToFeet = (m: number): number => m * 3.28084
export const metersToMiles = (m: number): number => m / 1609.344

/** Ordered `[lon, lat]` vertices of a route. A `MultiLineString`'s segments are
 *  concatenated in order (a small phantom gap between disjoint segments is
 *  acceptable for distance/marker math at trail scale). */
export function flattenGeometry(geometry: RouteGeometry): [number, number][] {
  return geometry.type === 'LineString' ? geometry.coordinates : geometry.coordinates.flat()
}

/** Great-circle distance between two `[lon, lat]` points, in metres. */
export function haversineMeters(a: [number, number], b: [number, number]): number {
  const dLat = toRad(b[1] - a[1])
  const dLon = toRad(b[0] - a[0])
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a[1])) * Math.cos(toRad(b[1])) * Math.sin(dLon / 2) ** 2
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(h)))
}

/** Cumulative along-route distance (m) at each vertex; `[0]` is `0`, length
 *  matches `coords`. */
export function cumulativeDistances(coords: [number, number][]): number[] {
  const out: number[] = coords.length > 0 ? [0] : []
  for (let i = 1; i < coords.length; i++) {
    out.push(out[i - 1] + haversineMeters(coords[i - 1], coords[i]))
  }
  return out
}

/** Total along-route length of a geometry, in metres. */
export function routeLengthMeters(geometry: RouteGeometry): number {
  const cum = cumulativeDistances(flattenGeometry(geometry))
  return cum.length > 0 ? cum[cum.length - 1] : 0
}

/** `[[minLon, minLat], [maxLon, maxLat]]`. */
export type Bounds = [[number, number], [number, number]]

/**
 * Bounding box over a trip's route + trailhead (+ summit). With `geometry: null`
 * it returns a degenerate box at the trailhead — the caller pads/zooms it for
 * the trailhead-only state.
 */
export function boundsOf(geo: {
  geometry: RouteGeometry | null
  trailhead: GeoPosition
  summit?: GeoPosition
}): Bounds {
  const pts: [number, number][] = [[geo.trailhead.lon, geo.trailhead.lat]]
  if (geo.summit) pts.push([geo.summit.lon, geo.summit.lat])
  if (geo.geometry) pts.push(...flattenGeometry(geo.geometry))

  let minLon = Infinity
  let minLat = Infinity
  let maxLon = -Infinity
  let maxLat = -Infinity
  for (const [lon, lat] of pts) {
    if (lon < minLon) minLon = lon
    if (lon > maxLon) maxLon = lon
    if (lat < minLat) minLat = lat
    if (lat > maxLat) maxLat = lat
  }
  return [
    [minLon, minLat],
    [maxLon, maxLat],
  ]
}

/** Interpolated `[lon, lat]` at a fraction (`0..1`, clamped) of total length. */
export function pointAtFraction(geometry: RouteGeometry, fraction: number): [number, number] {
  const coords = flattenGeometry(geometry)
  if (coords.length === 0) throw new Error('pointAtFraction: empty geometry')
  if (coords.length === 1) return coords[0]

  const cum = cumulativeDistances(coords)
  const total = cum[cum.length - 1]
  const target = clamp01(fraction) * total
  for (let i = 1; i < cum.length; i++) {
    if (cum[i] >= target) {
      const segLen = cum[i] - cum[i - 1]
      const t = segLen === 0 ? 0 : (target - cum[i - 1]) / segLen
      return lerpPoint(coords[i - 1], coords[i], t)
    }
  }
  return coords[coords.length - 1]
}

/**
 * Fraction (`0..1`) of the route nearest a clicked `[lon, lat]` — projects the
 * point onto each segment and returns the cumulative-distance fraction of the
 * closest projection. Drives the tap-route → profile-cursor direction of sync.
 */
export function nearestFractionToPoint(geometry: RouteGeometry, point: [number, number]): number {
  const coords = flattenGeometry(geometry)
  if (coords.length < 2) return 0
  const cum = cumulativeDistances(coords)
  const total = cum[cum.length - 1]
  if (total === 0) return 0

  let bestDist = Infinity
  let bestAlong = 0
  for (let i = 1; i < coords.length; i++) {
    const { t, dist } = projectOntoSegment(point, coords[i - 1], coords[i])
    if (dist < bestDist) {
      bestDist = dist
      bestAlong = cum[i - 1] + t * (cum[i] - cum[i - 1])
    }
  }
  return bestAlong / total
}

/** Linear-interpolated elevation (m) at a fraction (`0..1`) of the profile span. */
export function elevationAtFraction(profile: ElevationProfile, fraction: number): number | null {
  const s = profile.samples
  if (s.length === 0) return null
  if (s.length === 1) return s[0].elevationMeters

  const total = s[s.length - 1].distanceMeters
  const target = clamp01(fraction) * total
  for (let i = 1; i < s.length; i++) {
    if (s[i].distanceMeters >= target) {
      const seg = s[i].distanceMeters - s[i - 1].distanceMeters
      const t = seg === 0 ? 0 : (target - s[i - 1].distanceMeters) / seg
      return s[i - 1].elevationMeters + (s[i].elevationMeters - s[i - 1].elevationMeters) * t
    }
  }
  return s[s.length - 1].elevationMeters
}

/**
 * Gain / loss / max-grade summary from raw samples — mirrors the backend's
 * 3DEP precompute so the mock fixture and the live API produce identical shapes.
 */
export function summarizeProfile(
  samples: ElevationSample[],
  source: string,
  resolutionMeters: number,
): ElevationProfile {
  let gain = 0
  let loss = 0
  let maxGrade = 0
  for (let i = 1; i < samples.length; i++) {
    const dz = samples[i].elevationMeters - samples[i - 1].elevationMeters
    const dx = samples[i].distanceMeters - samples[i - 1].distanceMeters
    if (dz > 0) gain += dz
    else loss += -dz
    if (dx > 0) maxGrade = Math.max(maxGrade, Math.abs(dz / dx) * 100)
  }
  return {
    samples,
    totalGainMeters: Math.round(gain),
    totalLossMeters: Math.round(loss),
    maxGradePercent: Math.round(maxGrade * 10) / 10,
    source,
    resolutionMeters,
  }
}

/**
 * A native-maps deep link for DRIVING directions to the trailhead (S6 AC-6.4).
 * The universal Google Maps URL is honoured by iOS and Android and degrades to
 * the browser. On-trail navigation is explicitly out of scope.
 */
export function trailheadDirectionsUrl(trailhead: GeoPosition): string {
  const destination = encodeURIComponent(`${trailhead.lat},${trailhead.lon}`)
  return `https://www.google.com/maps/dir/?api=1&destination=${destination}&travelmode=driving`
}

// ---- internals -----------------------------------------------------------

const clamp01 = (n: number): number => Math.max(0, Math.min(1, n))

function lerpPoint(a: [number, number], b: [number, number], t: number): [number, number] {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]
}

/**
 * Project `p` onto segment `a→b` in a local equirectangular frame (metres),
 * accurate at trail scale. Returns the clamped parameter `t ∈ [0, 1]` and the
 * perpendicular distance in metres.
 */
function projectOntoSegment(
  p: [number, number],
  a: [number, number],
  b: [number, number],
): { t: number; dist: number } {
  const k = Math.cos(toRad(a[1]))
  const toXY = (c: [number, number]): [number, number] => [
    toRad(c[0] - a[0]) * k * EARTH_RADIUS_M,
    toRad(c[1] - a[1]) * EARTH_RADIUS_M,
  ]
  const [px, py] = toXY(p)
  const [bx, by] = toXY(b) // `a` is the origin
  const len2 = bx * bx + by * by
  const t = len2 === 0 ? 0 : clamp01((px * bx + py * by) / len2)
  return { t, dist: Math.hypot(px - bx * t, py - by * t) }
}
