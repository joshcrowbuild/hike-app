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
  /**
   * Distinct live-source names backing this fact (Epic 026a). Present on every
   * wire line (the feed carries no non-live lines) — always a single-entry list
   * today, since a live condition fact is single-source by construction (CDP-01).
   * Never conflate with a card-level enrichment/mock source list.
   */
  sources: string[]
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

/**
 * One condition that couldn't be verified — the trail stays a normal card carrying
 * this disclosure rather than being set aside (decision of 2026-07-02): live
 * conditions are enrichment, never a dependency, so an outage must never blank the
 * feed.
 */
export interface ConditionUnavailableResponse {
  text: string
  source: string
  kind: string
}

/**
 * One kind's disposition on one card (Epic 018 S4 / CDP-02): the per-kind condition
 * summary that makes absence legible, distinct silence — never a blank the client
 * must guess about. `state` is one of present | stale_degraded | no_hazard |
 * no_data | unavailable | not_fetched; `source`/`checked_at` are set exactly when a
 * source actually answered. Presentation only — never a ranking input (Rule #2).
 */
export interface ConditionStatusResponse {
  kind: string
  state: string
  source: string
  checked_at: string | null
  detail: string
}

export interface FeedCardResponse {
  canonical_id: string
  name: string
  distance_mi: number | null
  lines: FeedLineResponse[]
  warnings: CardWarningResponse[]
  unavailable: ConditionUnavailableResponse[]
  /** Per-kind condition disposition (Epic 018 S4 / CDP-02) — additive; older payloads omit it. */
  conditions?: ConditionStatusResponse[]
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
  /**
   * Source-or-silence disclosure for a start marker (Rule #1): `true` when the point
   * is a derived, approximate access point (synthesised from the trail's geometry
   * because the trail has no surveyed trailhead — D7), `false`/absent for a real
   * surveyed trailhead. Presentation-only; never affects ranking (Rule #2).
   */
  derived?: boolean
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
  /** Naismith's-rule duration ESTIMATE, not a stated fact (Rule #1/#7) — disclose as such. */
  estimated_duration_min: number
}

// ---- GET /trail/{canonical_id} — the water answer (Epic 041) --------------

/**
 * One mapped water POI near a trail (Epic 041, reading the Epic 035
 * `:WaterSource` overlay). Location + type + seasonality only — NEVER a
 * potability claim in any field (`water_type: "drinking_water"` is the OSM
 * POI category, not a "safe to drink" assertion). `distance_m` is measured
 * against `WireTrailWater.basis` (route vertices or the trail's start point).
 */
export interface WireWaterSource {
  water_id: string
  water_type: string // "spring" | "drinking_water" | "water_tap" | "water_well"
  name: string | null
  lat: number
  lon: number
  distance_m: number
  /** Raw OSM `seasonal` tag (e.g. "yes"), or null. */
  seasonal: string | null
  /** Provenance, e.g. "OSM" (ODbL — the surface owes © OpenStreetMap). */
  source: string
}

/**
 * The water answer for one trail — a TRAIL FACT from the slow/structural
 * corpus, deliberately NOT a condition kind (the condition kind named "water"
 * is USGS streamflow). CDP-02 three ways: `state: "sources"` = an answer;
 * `state: "none_nearby"` = an answered-empty (the corpus has water mapped
 * around this trail, none within `radius_m`); the whole field null/absent on
 * `GET /trail/{id}` = silence (region never water-ingested / read failed) —
 * rendered as NO row, never an empty claim.
 */
export interface WireTrailWater {
  state: 'sources' | 'none_nearby'
  basis: 'route' | 'start'
  /** The near threshold the server actually applied (m). */
  radius_m: number
  /** Distinct corpus source names backing the answer, e.g. "OSM". */
  source: string
  sources: WireWaterSource[]
}

/** The slice of `GET /trail/{canonical_id}` this client reads today (the maps
 *  fields also ride that payload but Detail already has them via the card). */
export interface TrailDetailWaterSlice {
  water_sources?: WireTrailWater | null
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

// ---- GET /regions (Phase 2: config-driven origins) -----------------------

export interface OriginResponse {
  key: string
  label: string
  lat: number
  lon: number
}

export interface RegionResponse {
  region_id: string
  label: string
  origins: OriginResponse[]
}

export interface RegionsResponse {
  regions: RegionResponse[]
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
