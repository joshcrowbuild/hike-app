/**
 * Facet → wire translation lives at the seam, never in components (R-plan §3).
 *
 * The backend takes only `lat`/`lon` + a free-text `query`; it has no named-origin
 * concept and no structured facet fields. So a named origin becomes coordinates
 * here, and the rest of the tuning frame is folded into the query string by
 * `buildQuery`. Components keep using `TuningState` unchanged; the mock honors
 * the structured intent directly, the HTTP adapter serializes it into `query`.
 */
import type { OriginKey } from '../types'

export interface Coords {
  lat: number
  lon: number
}

/** Approximate town centers for the three seed origins (WGS84). */
export const originCoords: Record<OriginKey, Coords> = {
  frontRoyal: { lat: 38.918, lon: -78.194 },
  luray: { lat: 38.665, lon: -78.459 },
  charlottesville: { lat: 38.029, lon: -78.477 },
}
