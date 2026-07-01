/**
 * View-model — the stable shape every screen consumes. Both the mock and the
 * HTTP adapter satisfy this; screens never see a wire DTO or the legacy `Trail`.
 *
 * The load-bearing idea (UX assembly plan §3, R1): **provenance is first-class.**
 * Every fact-bearing value declares whether it came from a `live` call, is
 * `mock` (fabricated for a backend that isn't wired yet), or is `sample`
 * (illustrative seed about a sample subject). The honesty primitives refuse to
 * render a confident tier over non-live provenance, so mock can never wear the
 * costume of a verified fact — degradation stays visible, never silent.
 */
import type { EffortKey } from '../types'
import type { ConfidenceLevel } from './api'

export type Provenance = 'live' | 'mock' | 'sample'

/** A single verified (or, in mock, fabricated) condition line, 1:1 with the API. */
export interface LineVM {
  text: string
  source: string
  confidence: ConfidenceLevel
  provenance: Provenance
}

/**
 * The four legible silence states (CDP-02). An honest app in a data-sparse spot
 * must never read as broken or *falsely clear*: absence of a condition is a
 * distinct, disclosed state, never a blank. Each renders a visibly different
 * treatment — same-looking gray for all four is a fail (Epic 018 AC-4.2).
 *
 * - `not-fetched`  — no live probe has run yet (open to verify). The honest
 *                    default for today's thin `/plan`, which never claims coverage.
 * - `checked-clear`— a source ran and found nothing to flag (a real positive
 *                    result — only shown on an explicit backend signal, never assumed).
 * - `no-data`      — no source covers this kind at this spot (e.g. no gauge near).
 * - `stale-degraded`— a last-known value exists but is past its rate-of-change
 *                    horizon and may have changed (carries a relative age).
 */
export type SilenceState = 'not-fetched' | 'checked-clear' | 'no-data' | 'stale-degraded'

export interface ConditionSilence {
  state: SilenceState
  /**
   * Optional specifics for the state, already humanised — e.g. a relative age
   * ("4h ago") for `stale-degraded`, or which kinds are uncovered for `no-data`.
   * Never a raw datetime (§7.2).
   */
  detail?: string
}

/**
 * The rich card vocabulary the v0.3 design wants but the API does not yet
 * provide. Optional by construction: the HTTP adapter drops what it can't
 * supply, and the card degrades to the honest-thin rendering. Everything here
 * carries `provenance` so the surface can demote/label it.
 */
export interface CardEnrichment {
  placeCue?: string
  area?: string
  routeShape?: string
  /** Trail length in miles (distinct from the API's crow-flies `distance_mi`). */
  distanceMiles?: number
  ascentFeet?: number
  durationHours?: string
  /** Drive minutes from the current frame's origin; absent on a frame-less deep-link. */
  driveMinutes?: number
  effort?: EffortKey
  tags?: string[]
  fitLine?: string
  conditionValue?: string
  freshness?: string
  /** A soft verify-before-you-go caution (distinct from the safety `warnings`). */
  caution?: string
  /** Richer prose, used only on Detail. */
  character?: string
  practicalNote?: string
  /** Inspectable source basis (Detail). Reuses real per-line sources when live. */
  sources?: string[]
  provenance: Provenance
}

export interface CardVM {
  id: string
  name: string
  /** Crow-flies origin→trail miles (the API's `distance_mi`), null when unknown. */
  distanceMi: number | null
  conditionLines: LineVM[]
  /**
   * The honest silence for absent/degraded conditions (CDP-02). Used to render a
   * legible silence state when no usable line exists, or — alongside present
   * lines — to disclose that the shown set isn't exhaustive (AC-4.3). Absent →
   * the card falls back to the honest `not-fetched` default when it has no lines.
   */
  conditionSilence?: ConditionSilence
  /** Safety guardrail strings from the engine (the API's `warnings`). */
  warnings: string[]
  enrichment?: CardEnrichment
  /**
   * Maps & terrain payload (Epic 016). Absent until the geometry/elevation
   * contract is wired (the thin `/plan` adapter drops it); present on the mock
   * and, later, the detail endpoint. The map and the elevation glyph read this.
   */
  geo?: TrailGeo
}

// ---- Maps & terrain (Epic 016 / 017) -------------------------------------

/** A WGS84 point. Mirrors the contract's `trailhead {lat, lon}`. */
export interface GeoPosition {
  lat: number
  lon: number
}

/**
 * GeoJSON route geometry (WGS84, `[lon, lat]` order per the spec). A
 * `MultiLineString` is used when a trail's segments don't join cleanly. A trail
 * with no mapped route is `null` — never an empty or fabricated line (D5/AC-1.2).
 */
export type RouteGeometry =
  | { type: 'LineString'; coordinates: [number, number][] }
  | { type: 'MultiLineString'; coordinates: [number, number][][] }

/**
 * Confidence in the route's conflation, derived from the existing confidence
 * tier on the backend (Rule #2). `approximate` draws a dashed line with a
 * disclosed note (D5/S3 AC-3.2); `confident` draws a solid line.
 */
export type GeometryQuality = 'confident' | 'approximate'

/** One sampled point along the route's elevation profile. */
export interface ElevationSample {
  /** Cumulative distance from the trailhead, in metres. */
  distanceMeters: number
  elevationMeters: number
}

/**
 * Elevation profile precomputed from USGS 3DEP along the route (the Epic 017 S0
 * contract the two lanes freeze on). `null` on a trail with no profile → the
 * chart and glyph degrade honestly to the ascent figure, never a faked curve.
 */
export interface ElevationProfile {
  samples: ElevationSample[]
  totalGainMeters: number
  totalLossMeters: number
  maxGradePercent: number
  /** Provenance string, e.g. "USGS 3DEP". Shown with the profile. */
  source: string
  resolutionMeters: number
}

/**
 * The map/terrain payload for one trip — exactly the shapes Lane A's API
 * returns, consumed identically whether mock or live. Bundling them keeps the
 * map a single prop and the trailhead (needed even with `geometry: null`, for
 * the trailhead-only state and the directions deep-link) always present.
 */
export interface TrailGeo {
  geometry: RouteGeometry | null
  trailhead: GeoPosition
  /** Solid vs dashed route (honesty, D5). Defaults to confident when geometry exists. */
  quality: GeometryQuality
  /** Optional summit / high-point marker, where known. */
  summit?: GeoPosition
  elevationProfile: ElevationProfile | null
}

/**
 * A candidate excluded by an explicit, reversible constraint (Ruby's party
 * gate, or the readiness filter) — disclosed, never silently dropped (R6, R2).
 * Mirrors the readiness "N hidden · show anyway" affordance.
 */
export interface SetAside {
  id: string
  name: string
  reason: string
  /** Which constraint set it aside, so the surface can group/label it. */
  kind: 'party' | 'readiness'
  restorable: boolean
}

/** Readiness disclosure (R2): a gate over the ranked set, never a rank penalty. */
export interface ReadinessVM {
  on: boolean
  /** off = not applied; applied = a fresh reading filtered the set; open = on but
   *  no/stale reading, so it failed open to the full feed and says so. */
  state: 'off' | 'applied' | 'open'
  /** Effect-first, trail-facing rationale — never a body diagnosis, never a number. */
  rationale?: string
  /** Why it failed open (stale/absent reading), shown plainly when state==='open'. */
  staleReason?: string
}

export type FeedErrorKind = 'offline' | 'timeout' | 'server' | 'auth' | 'partial' | 'empty'

export interface FeedError {
  kind: FeedErrorKind
  message: string
}

export interface FeedVM {
  query: string
  cards: CardVM[]
  /** Feed-level disclosures (e.g. "Drive times unavailable this run"). */
  notices: string[]
  /** Constraint-excluded candidates, disclosed and restorable. */
  setAside: SetAside[]
  readiness: ReadinessVM
  /** Whether this whole feed is live or sample data — drives the calm sample strip. */
  dataSource: 'live' | 'mock'
  error?: FeedError
}

// ---- Post-hike loop (Outcome) --------------------------------------------

/**
 * A companion on a hike. Modeled as a list of refs, not a bool (R5): Ruby is a
 * `dependent`; a real second member would be a `member` — distinct kinds, never
 * conflated. The current backend has no party field on the outcome, so this is
 * captured client-side and noted as a backend gap.
 */
export interface CompanionRef {
  kind: 'dependent' | 'member'
  name: string
}

/**
 * An Episode = one recorded hike. Measured facts come from the watch; tonight
 * they are `sample` provenance and must be disclosed as such — never posed as
 * the user's real watch data (R11, source-or-silence on our own record).
 */
export interface EpisodeVM {
  id: string
  trailName: string
  /** Relative day, e.g. "Saturday" — never a raw datetime. */
  when: string
  distanceMiles: number
  ascentFeet: number
  movingTime: string
  /** Optional LLM-extracted note, shown as already-known, never asked. */
  paceNote?: string
  companions: CompanionRef[]
  /** Present once an outcome has been logged (drives the pending-nod surfacing). */
  outcome?: { overall: 1 | 2 | 3 | null; skipped: boolean }
  provenance: Provenance
}

export interface OutcomeVM {
  outcomeId: string
  episodeId: string
  overall: number | null
  skipped: boolean
  companions: CompanionRef[]
}
