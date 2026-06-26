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
  profilePath?: number[]
  terrainPath?: number[]
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
  /** Safety guardrail strings from the engine (the API's `warnings`). */
  warnings: string[]
  enrichment?: CardEnrichment
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
