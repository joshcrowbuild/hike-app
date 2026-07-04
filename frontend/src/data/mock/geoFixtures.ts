/**
 * Sample geometry + elevation profiles for the mock trails (Epic 016 AC-1.4:
 * "the mock fixture gains real sample coordinates so the map renders before
 * live-data wiring"). Quarantined throwaway like the rest of the mock engine —
 * deletable once Lane A's geometry/elevation endpoints are authoritative; no
 * screen imports it directly.
 *
 * The coordinates are believable hand-traced routes in Shenandoah (WGS84,
 * `[lon, lat]`); the elevation curves reuse each trail's tuned climb shape and
 * are scaled so the reported gain tracks the card's `ascentFeet`. Two trails
 * deliberately exercise the honest states (S3): `dark-hollow` is `approximate`
 * (dashed), `hawksbill` has no mapped route and no profile.
 */
import { clamp01, summarizeProfile } from '../geo'
import type {
  ElevationProfile,
  ElevationSample,
  GeometryQuality,
  GeoPosition,
  RouteGeometry,
  TrailGeo,
} from '../vm'

interface GeoSpec {
  trailhead: GeoPosition
  summit?: GeoPosition
  quality: GeometryQuality
  /** Control points tracing the route; `null` → no mapped geometry (S3 AC-3.1). */
  waypoints: [number, number][] | null
  /** Trailhead elevation (m) — sets the profile's absolute floor. */
  baseElevM: number
  /** Normalized-ish climb shape; `null` → no profile yet (degrade to "coming soon"). */
  shape: number[] | null
}

const SPECS: Record<string, GeoSpec> = {
  'stony-man': {
    trailhead: { lat: 38.5928, lon: -78.3736 },
    summit: { lat: 38.5945, lon: -78.376 },
    quality: 'confident',
    baseElevM: 1010,
    waypoints: [
      [-78.3736, 38.5928],
      [-78.3748, 38.5934],
      [-78.3759, 38.5941],
      [-78.3766, 38.5948],
      [-78.376, 38.5945],
      [-78.3752, 38.595],
      [-78.3742, 38.5944],
      [-78.3736, 38.5935],
      [-78.3736, 38.5928],
    ],
    shape: [12, 18, 32, 46, 58, 66, 71, 72, 70],
  },
  'whiteoak-canyon': {
    trailhead: { lat: 38.5557, lon: -78.349 },
    summit: { lat: 38.5695, lon: -78.3592 },
    quality: 'confident',
    baseElevM: 430,
    waypoints: [
      [-78.349, 38.5557],
      [-78.3512, 38.5585],
      [-78.3534, 38.5612],
      [-78.3556, 38.564],
      [-78.3578, 38.5668],
      [-78.3592, 38.5695],
    ],
    shape: [8, 16, 21, 29, 35, 45, 56, 59, 60],
  },
  'old-rag': {
    trailhead: { lat: 38.5709, lon: -78.289 },
    summit: { lat: 38.5519, lon: -78.3107 },
    quality: 'confident',
    baseElevM: 320,
    waypoints: [
      [-78.289, 38.5709],
      [-78.2925, 38.568],
      [-78.2975, 38.564],
      [-78.303, 38.559],
      [-78.308, 38.5545],
      [-78.3107, 38.5519],
      [-78.312, 38.556],
      [-78.309, 38.561],
      [-78.303, 38.566],
      [-78.296, 38.57],
      [-78.289, 38.5709],
    ],
    shape: [6, 18, 30, 43, 57, 69, 77, 74, 62],
  },
  'dark-hollow': {
    trailhead: { lat: 38.5226, lon: -78.4253 },
    // Low source agreement on the exact line → dashed "approximate route" (S3).
    quality: 'approximate',
    baseElevM: 1015,
    waypoints: [
      [-78.4253, 38.5226],
      [-78.4268, 38.5214],
      [-78.4282, 38.5202],
      [-78.43, 38.5189],
    ],
    shape: [10, 16, 20, 27, 33, 35, 36, 31, 26],
  },
  hawksbill: {
    trailhead: { lat: 38.556, lon: -78.387 },
    quality: 'confident',
    // No conflated route line yet → trailhead-only state (S3 AC-3.1), and no
    // 3DEP profile → the chart/glyph degrade honestly (S5 AC-5.2 / S4 AC-4.2).
    waypoints: null,
    baseElevM: 1050,
    shape: null,
  },
}

const FEET_PER_METER = 3.28084
const METERS_PER_MILE = 1609.344
const PROFILE_SAMPLES = 48

/** Densify control points into a smoother polyline for marker interpolation. */
function densify(waypoints: [number, number][], perLeg = 4): [number, number][] {
  const out: [number, number][] = []
  for (let i = 0; i < waypoints.length - 1; i++) {
    const [ax, ay] = waypoints[i]
    const [bx, by] = waypoints[i + 1]
    for (let s = 0; s < perLeg; s++) {
      const t = s / perLeg
      out.push([ax + (bx - ax) * t, ay + (by - ay) * t])
    }
  }
  out.push(waypoints[waypoints.length - 1])
  return out
}

function normalize(values: number[]): number[] {
  const min = Math.min(...values)
  const span = Math.max(...values) - min
  return span === 0 ? values.map(() => 0) : values.map((v) => (v - min) / span)
}

function positiveDeltaSum(values: number[]): number {
  let sum = 0
  for (let i = 1; i < values.length; i++) {
    const d = values[i] - values[i - 1]
    if (d > 0) sum += d
  }
  return sum
}

function sampleShape(values: number[], fraction: number): number {
  if (values.length <= 1) return values[0] ?? 0
  const x = clamp01(fraction) * (values.length - 1)
  const i = Math.floor(x)
  if (i >= values.length - 1) return values[values.length - 1]
  return values[i] + (values[i + 1] - values[i]) * (x - i)
}

/**
 * Build an elevation profile scaled so the reported gain tracks `ascentFeet`,
 * sampled along the trail's stated mileage (so the chart's distance axis matches
 * the card). Mirrors what the 3DEP precompute will return — same shape, summary.
 */
function buildProfile(distanceMiles: number, baseElevM: number, shape: number[], ascentFeet: number): ElevationProfile {
  const totalMeters = distanceMiles * METERS_PER_MILE
  const norm = normalize(shape)
  const scale = (ascentFeet / FEET_PER_METER) / (positiveDeltaSum(norm) || 1)
  const samples: ElevationSample[] = []
  for (let i = 0; i <= PROFILE_SAMPLES; i++) {
    const f = i / PROFILE_SAMPLES
    samples.push({
      distanceMeters: Math.round(f * totalMeters),
      elevationMeters: Math.round(baseElevM + scale * sampleShape(norm, f)),
    })
  }
  return summarizeProfile(samples, 'USGS 3DEP (sample)', Math.max(1, Math.round(totalMeters / PROFILE_SAMPLES)))
}

/**
 * Assemble the full geometry + elevation payload for a trail. `distanceMiles`
 * and `ascentFeet` come from the trail record so the profile stays consistent
 * with the card's figures without duplicating them here.
 */
export function buildTrailGeo(id: string, distanceMiles: number, ascentFeet: number): TrailGeo {
  const spec = SPECS[id]
  if (!spec) throw new Error(`geoFixtures: no fixture for "${id}"`)
  const geometry: RouteGeometry | null = spec.waypoints
    ? { type: 'LineString', coordinates: densify(spec.waypoints) }
    : null
  const elevationProfile = spec.shape ? buildProfile(distanceMiles, spec.baseElevM, spec.shape, ascentFeet) : null
  return {
    geometry,
    trailhead: spec.trailhead,
    quality: spec.quality,
    summit: spec.summit,
    elevationProfile,
  }
}
