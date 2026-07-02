/**
 * The region tag shown on Home must track what was actually served, never a
 * static assumption from the picker (report finding #3: "shows Shenandoah
 * while serving Charlottesville"). Every card that carries geometry already
 * carries a real trailhead coordinate (`geo.trailhead`) — the ground truth for
 * where a trail sits — so the label is derived from THAT, by nearest-origin
 * match, rather than from the origin the viewer happened to pick. The origin
 * mapping is only a fallback for the (thin, geometry-less) cards that carry no
 * coordinate at all.
 */
import { originCoords } from './origins'
import { regionLabels } from './labels'
import type { OriginKey, TuningState } from '../types'
import type { CardVM } from './vm'

function nearestOriginRegion(lat: number, lon: number): string {
  let bestKey: OriginKey | null = null
  let bestDist = Infinity
  for (const key of Object.keys(originCoords) as OriginKey[]) {
    const o = originCoords[key]
    // A cheap planar proxy, not haversine: named regions sit hundreds of miles
    // apart, so no precision is lost picking the nearest one.
    const dist = (o.lat - lat) ** 2 + (o.lon - lon) ** 2
    if (dist < bestDist) {
      bestDist = dist
      bestKey = key
    }
  }
  return regionLabels[bestKey as OriginKey]
}

/** The region actually represented by the served cards' trailheads (majority
 *  vote), falling back to the query's own origin only when no card discloses
 *  a coordinate to check that assumption against. */
export function resolveRegionLabel(cards: CardVM[], tuning: TuningState): string {
  const counts = new Map<string, number>()
  for (const card of cards) {
    const trailhead = card.geo?.trailhead
    if (!trailhead) continue
    const region = nearestOriginRegion(trailhead.lat, trailhead.lon)
    counts.set(region, (counts.get(region) ?? 0) + 1)
  }
  if (counts.size > 0) {
    return [...counts.entries()].sort((a, b) => b[1] - a[1])[0][0]
  }
  if (tuning.originCoords) return 'Near you'
  return regionLabels[tuning.origin]
}
