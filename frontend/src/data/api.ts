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

export interface FeedCardResponse {
  canonical_id: string
  name: string
  distance_mi: number | null
  lines: FeedLineResponse[]
  warnings: string[]
}

export interface FeedResponse {
  query: string
  cards: FeedCardResponse[]
  card_count: number
  notices: string[]
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
