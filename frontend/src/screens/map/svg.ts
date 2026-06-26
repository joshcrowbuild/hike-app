/**
 * Pure SVG-coordinate helpers for the map module's non-GL surfaces: the feed
 * elevation glyph, the Detail elevation profile, and the static route fallback
 * drawn when WebGL/tiles are unavailable. No React, no map library — projection
 * math only, so it is unit-tested directly.
 */
import { clamp01, flattenGeometry } from '../../data/geo'
import type { ElevationSample, GeoPosition, RouteGeometry } from '../../data/vm'

export interface Box {
  width: number
  height: number
  padX?: number
  padY?: number
}

const round = (n: number): number => Math.round(n * 100) / 100

export interface ProfileScale {
  /** SVG x for an along-route distance (m). */
  x: (distanceMeters: number) => number
  /** SVG y for an elevation (m), inverted so up is up. */
  y: (elevationMeters: number) => number
  minE: number
  maxE: number
  maxD: number
  bottom: number
}

/** Shared distance/elevation → SVG mapping, so the plotted curve and the scrub
 *  cursor use one coordinate system. */
export function profileScale(samples: ElevationSample[], box: Box): ProfileScale {
  const padX = box.padX ?? 0
  const padY = box.padY ?? 0
  const innerW = box.width - 2 * padX
  const innerH = box.height - 2 * padY
  const maxD = samples.length > 0 ? samples[samples.length - 1].distanceMeters || 1 : 1
  const elevs = samples.map((s) => s.elevationMeters)
  const minE = elevs.length > 0 ? Math.min(...elevs) : 0
  const maxE = elevs.length > 0 ? Math.max(...elevs) : 0
  const spanE = maxE - minE || 1
  return {
    x: (d) => round(padX + (d / maxD) * innerW),
    y: (e) => round(padY + (1 - (e - minE) / spanE) * innerH),
    minE,
    maxE,
    maxD,
    bottom: box.height - padY,
  }
}

/** Elevation samples → SVG points, distance on x (0..max), elevation on y
 *  (min..max, inverted so up is up). Returns `[]` for an empty profile. */
export function profilePoints(samples: ElevationSample[], box: Box): [number, number][] {
  if (samples.length === 0) return []
  const scale = profileScale(samples, box)
  return samples.map((s) => [scale.x(s.distanceMeters), scale.y(s.elevationMeters)])
}

export function profilePolyline(samples: ElevationSample[], box: Box): string {
  return profilePoints(samples, box)
    .map(([x, y]) => `${x},${y}`)
    .join(' ')
}

/** SVG x for a fraction (0..1) of the profile's distance axis. */
export function fractionToX(fraction: number, box: Box): number {
  const padX = box.padX ?? 0
  return padX + clamp01(fraction) * (box.width - 2 * padX)
}

/** Inverse of {@link fractionToX}: a pointer x → fraction (0..1). */
export function xToFraction(x: number, box: Box): number {
  const padX = box.padX ?? 0
  const inner = box.width - 2 * padX || 1
  return clamp01((x - padX) / inner)
}

export interface ProjectedRoute {
  route: [number, number][]
  trailhead: [number, number]
  summit?: [number, number]
  /** Project any `[lon, lat]` into the same SVG frame (e.g. the scrub cursor). */
  project: (point: [number, number]) => [number, number]
}

/**
 * Project a route + trailhead (+ summit) into SVG space, fit to the box with an
 * equirectangular projection that preserves aspect (no north/south stretch).
 * Powers the static fallback route render — honest even with no tiles (AC-3.3).
 */
export function projectRoute(
  geometry: RouteGeometry | null,
  trailhead: GeoPosition,
  box: Box,
  summit?: GeoPosition,
): ProjectedRoute {
  const padX = box.padX ?? 8
  const padY = box.padY ?? 8
  const pts: [number, number][] = [[trailhead.lon, trailhead.lat]]
  if (summit) pts.push([summit.lon, summit.lat])
  if (geometry) pts.push(...flattenGeometry(geometry))

  const lats = pts.map((p) => p[1])
  const midLat = (Math.min(...lats) + Math.max(...lats)) / 2
  const k = Math.cos((midLat * Math.PI) / 180) || 1 // longitude foreshortening

  const xs = pts.map((p) => p[0] * k)
  const ys = pts.map((p) => p[1])
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)
  const spanX = maxX - minX || 1e-6
  const spanY = maxY - minY || 1e-6

  const innerW = box.width - 2 * padX
  const innerH = box.height - 2 * padY
  const scale = Math.min(innerW / spanX, innerH / spanY)
  const offX = padX + (innerW - spanX * scale) / 2
  const offY = padY + (innerH - spanY * scale) / 2

  const project = ([lon, lat]: [number, number]): [number, number] => [
    round(offX + (lon * k - minX) * scale),
    round(offY + (maxY - lat) * scale), // invert y so north is up
  ]

  return {
    route: geometry ? flattenGeometry(geometry).map(project) : [],
    trailhead: project([trailhead.lon, trailhead.lat]),
    summit: summit ? project([summit.lon, summit.lat]) : undefined,
    project,
  }
}
