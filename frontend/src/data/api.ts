/**
 * Wire DTOs — a faithful TypeScript mirror of the FastAPI contract in
 * `api/schemas.py`. These types describe what the backend ACTUALLY returns;
 * the view-model (`vm.ts`) is what screens consume. The `HttpPlannerClient`
 * maps these → VM; the `MockPlannerClient` produces the VM directly.
 *
 * Keeping this a literal transcription (snake_case and all) means the seam can
 * be regenerated from the backend's OpenAPI later without touching the VM or
 * any screen.
 */

/** Presentation tier the backend derives from freshness · authority · corroboration. */
export type ConfidenceLevel = 'stated' | 'hedged' | 'flagged'

/**
 * Viewer scope, mirroring the backend's `owner_scope = (owner_id = $viewer OR
 * owner_id IN $granted)` (graph access control, Rule #4). Threaded through every
 * client method so the Phase-2 grant dimension is a value change, not a
 * signature change. Anonymous = empty scope is a real product, not a fallback.
 */
export interface ScopeContext {
  viewerId: string
  grantedIds: string[]
}

export const ANON_SCOPE: ScopeContext = { viewerId: 'anonymous', grantedIds: [] }

// ---- POST /plan ----------------------------------------------------------

export interface PlanRequest {
  query: string
  lat: number
  lon: number
  k?: number
  viewer_id?: string
}

export interface FeedLineResponse {
  text: string
  source: string
  confidence_level: ConfidenceLevel
}

/**
 * One prominent, source-stamped hazard warning a card wears (decision of
 * 2026-07-01): a VERIFIED hazard shows on the trail, never hides it. Mirrors
 * how `FeedLineResponse` carries source; `observed_at` is the ISO-8601 fetch
 * timestamp of the hazard fact.
 */
export interface CardWarningResponse {
  text: string
  source: string
  observed_at: string
  kind: string
}

export interface FeedCardResponse {
  canonical_id: string
  name: string
  distance_mi: number | null
  lines: FeedLineResponse[]
  warnings: CardWarningResponse[]
  /**
   * Maps & terrain (Epic 016 S1). Optional: the current `/plan` omits them, so
   * the adapter degrades; once the geometry/detail endpoint lands these arrive
   * and the map renders with no client change (a snake_case mirror of the VM).
   */
  geometry?: WireGeometry | null
  trailhead?: WirePoint | null
  /** Geometry's confidence tier; non-`stated` draws the dashed "approximate" route (D5). */
  geometry_confidence?: ConfidenceLevel
  summit?: WirePoint | null
  elevation_profile?: WireElevationProfile | null
}

/** WGS84 point, `{lat, lon}`. */
export interface WirePoint {
  lat: number
  lon: number
}

/** GeoJSON route geometry (`[lon, lat]` coordinate order per the spec). */
export type WireGeometry =
  | { type: 'LineString'; coordinates: [number, number][] }
  | { type: 'MultiLineString'; coordinates: [number, number][][] }

export interface WireElevationSample {
  distance_m: number
  elevation_m: number
}

export interface WireElevationProfile {
  samples: WireElevationSample[]
  total_gain_m: number
  total_loss_m: number
  max_grade_pct: number
  source: string
  resolution_m: number
}

/** One source-stamped cause a trail was set aside by a hard live guardrail (Epic 018 S5). */
export interface SetAsideReasonResponse {
  text: string
  source: string
  kind: string
}

/**
 * A trail a hard live guardrail ruled out — an unverifiable required condition or
 * a hard threshold — disclosed with its cause + source (Epic 018 S5), never dropped
 * without a trace. A VERIFIED hazard is NOT set aside: it stays a card carrying a
 * `warnings` entry (decision of 2026-07-01). A safety gate, not a ranking signal.
 */
export interface SetAsideResponse {
  canonical_id: string
  name: string
  reasons: SetAsideReasonResponse[]
}

export interface FeedResponse {
  query: string
  cards: FeedCardResponse[]
  card_count: number
  notices: string[]
  /** Trails a hard live guardrail set aside, disclosed with cause + source (Epic 018 S5). */
  set_aside?: SetAsideResponse[]
}

// ---- POST /episode/{id}/outcome ------------------------------------------

export interface OutcomeBody {
  overall: 1 | 2 | 3 | null
  delta_question?: string | null
  delta_answer?: string | null
  skipped: boolean
}

export interface OutcomeResponse {
  outcome_id: string
  episode_id: string
  skipped: boolean
  overall: number | null
}

// ---- GET /health ---------------------------------------------------------

export interface GraphStats {
  canonical_trails: number
  source_records: number
  trailheads: number
  same_as_edges: number
  schema_version: string | null
}

export interface HealthResponse {
  status: string
  version: string
  region: string
  probes_available: string[]
  graph: GraphStats | null
}
