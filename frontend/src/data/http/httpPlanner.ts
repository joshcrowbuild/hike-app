/**
 * HttpPlannerClient — the real adapter. Wired but inert until a backend is
 * reachable (the container has no Neo4j tonight). It is real code, not a
 * placeholder: it POSTs the actual `/plan` contract and maps `FeedResponse` →
 * VM with `provenance: 'live'`, dropping the enrichment the API does not supply
 * so the card degrades to its honest-thin rendering. Flipping `VITE_USE_MOCK`
 * off selects this; no screen changes.
 */
import { relativeAge } from '../age'
import { buildQuery } from '../buildQuery'
import { isDrawableRoute } from '../geo'
import type {
  CardWarningResponse,
  ConditionStatusResponse,
  ConfidenceLevel,
  FeedCardResponse,
  FeedLineResponse,
  FeedResponse,
  OutcomeBody,
  OutcomeResponse,
  PlanConditionsRequest,
  PlanConditionsResponse,
  PlanRequest,
  ScopeContext,
  SearchRequest,
  SearchResponse,
  TrailDetailWaterSlice,
  WireElevationProfile,
  WireTrailWater,
} from '../api'
import type { PlanInput, PlannerClient } from '../source'
import type {
  CardVM,
  ConditionsPatchVM,
  ConditionStateVM,
  ConditionStatusVM,
  ElevationProfile,
  EpisodeVM,
  FeedError,
  FeedVM,
  LineVM,
  OutcomeVM,
  TrailGeo,
  TrailWaterVM,
  WarningVM,
} from '../vm'
import type { Coords, TuningState } from '../../types'

// Last-resort default when a named origin key isn't in the loaded catalog at all
// (e.g. a stale key from a region since removed from config) — never crashes the
// coordinate lookup (Rule #1). `PlannerProvider` always constructs this client with
// the real fetched catalog, so this only ever fires for a genuinely unknown key.
const FALLBACK_COORDS: Coords = { lat: 38.918, lon: -78.194 }

// The Render free-tier API cold-starts in 30–60s after idling out. A 10s budget
// lost that race — the browser aborted /plan while a long-timeout curl succeeded
// (the "first tap fails on mobile" bug). 60s clears the worst-case cold start; a
// warm-ping cron (.github/workflows/warm-ping.yml) keeps this path rare. Only
// /plan (and getCard, which reruns plan) carries this budget — recordOutcome has
// no timeout — so a single constant suffices.
const PLAN_TIMEOUT_MS = 60_000

// The water read (Epic 041) is a small per-trail GET on an already-warm host
// (Detail is only reachable after a feed landed), so it never needs the /plan
// cold-start budget; past this it degrades to silence rather than keeping a
// stale spinner region alive on the commitment view.
const WATER_TIMEOUT_MS = 15_000

/**
 * Two-phase client switch (Epic 040 D6), build-time baked like `VITE_USE_MOCK`
 * and the S3 stale cap: `VITE_TWO_PHASE=0` restores today's single-call flow
 * byte-identically (AC-3.5). Blank counts as unset (enabled) — an
 * empty-but-present env line must not silently engage the kill switch.
 */
const TWO_PHASE = ((): boolean => {
  const raw = import.meta.env.VITE_TWO_PHASE
  if (raw === undefined || raw.trim() === '') return true
  return raw !== '0'
})()

/**
 * Managed auth (Epic 043 S3): a non-anonymous scope carries a Supabase access
 * token, sent as `Authorization: Bearer <token>`. The backend verifies it against
 * the public JWKS and derives the viewer from its `sub` — the client no longer
 * injects any shared secret (the H1/dev-secret path is retired). Anonymous
 * browsing sends no credentials at all.
 */
function authHeaders(scope: ScopeContext): HeadersInit {
  const base: HeadersInit = { 'content-type': 'application/json' }
  if (scope.viewerId === 'anonymous' || !scope.accessToken) return base
  return { ...base, Authorization: `Bearer ${scope.accessToken}` }
}

function classify(err: unknown, status?: number): FeedError {
  if (status === 401 || status === 403) return { kind: 'auth', message: 'This view needs you to be signed in.' }
  if (status && status >= 500) return { kind: 'server', message: 'The planner had trouble. Try again in a moment.' }
  if (err instanceof DOMException && err.name === 'AbortError')
    return { kind: 'timeout', message: 'That took too long. Check your connection and retry.' }
  return { kind: 'offline', message: 'Couldn’t reach the planner. Showing nothing live right now.' }
}

/** Wire lines → VM, shared by the full feed card and the phase-2 patch (Epic 040
 *  AC-2.1's client half: one mapping truth, never two). */
function mapLines(lines: FeedLineResponse[]): LineVM[] {
  return lines.map((l) => ({
    text: l.text,
    // Epic 045 S1 AC-1.1: the fact's value and its freshness, structurally
    // separate from `source` — a structured surface folds these in instead of
    // the welded `text` (never re-baking source/age into displayed copy).
    body: l.body,
    source: l.source,
    age: l.age,
    confidence: l.confidence_level,
    provenance: 'live',
    // Real per-fact corroboration (Epic 026a) — every wire line is live, so this
    // carries straight through; never backfilled from card-level enrichment.
    sources: l.sources,
  }))
}

/** Wire warnings → VM (source + humanised age), shared like `mapLines`. */
function mapWarnings(warnings: CardWarningResponse[]): WarningVM[] {
  return warnings.map((w) => ({
    text: w.text,
    source: w.source,
    observedAgo: relativeAge(w.observed_at),
    kind: w.kind,
    provenance: 'live',
  }))
}

function mapFeed(res: FeedResponse): FeedVM {
  return {
    query: res.query,
    cards: res.cards.map(
      (c): CardVM => ({
        id: c.canonical_id,
        name: c.name,
        distanceMi: c.distance_mi,
        conditionLines: mapLines(c.lines),
        // The per-kind `conditions` payload (Epic 018 S4f / CDP-02) is the
        // authoritative coverage signal — the old `lines.length === 0 →
        // not-fetched` heuristic mislabeled an answered-clear card as
        // couldn't-verify (#160's documented interim quirk), so it applies ONLY
        // when the payload is absent (an older backend). With the payload, the
        // card renders each kind's real disposition and needs no blanket guess.
        conditions: mapConditions(c.conditions),
        conditionSilence:
          c.conditions == null && c.lines.length === 0 ? { state: 'not-fetched' } : undefined,
        // A VERIFIED hazard rides the card as a prominent warning — shown, never
        // hidden (decision of 2026-07-01). Source + humanised age, like a line.
        warnings: mapWarnings(c.warnings),
        // The API supplies no rich enrichment yet; the card degrades to thin.
        enrichment: undefined,
        // Geometry/elevation arrive once Lane A's contract lands; map them when
        // present so the swap is a no-op, else `undefined` → no map (honest).
        geo: mapGeo(c),
      }),
    ),
    notices: res.notices,
    setAside: [],
    // Guardrail-held trails (an unverifiable required condition — Epic 018 S5):
    // disclosed at feed level so nothing the engine held back silently vanishes.
    heldBack: (res.set_aside ?? []).map((s) => ({
      id: s.canonical_id,
      name: s.name,
      reasons: s.reasons.map((r) => ({ text: r.text, source: r.source, kind: r.kind })),
    })),
    // Readiness has no HTTP surface yet (Epic 007 backlog); it stays off.
    readiness: { on: false, state: 'off' },
    dataSource: 'live',
    // Two-phase (Epic 040): only an EXPLICIT false means pending — an older
    // backend omits the field and its feed is the verified single-pass truth.
    conditionsPending: res.conditions_complete === false || undefined,
  }
}

/** Wire → VM state names (snake_case → the VM's kebab-case vocabulary). */
const WIRE_CONDITION_STATES: Record<string, ConditionStateVM> = {
  present: 'present',
  stale_degraded: 'stale-degraded',
  no_hazard: 'no-hazard',
  no_data: 'no-data',
  unavailable: 'unavailable',
  not_fetched: 'not-fetched',
}

/**
 * Wire → VM for the per-kind condition dispositions (Epic 018 S4f). Timestamps
 * are humanised here (`relativeAge`) so no raw datetime crosses into the VM
 * (§7.2). A state this client doesn't know is dropped — the additive-contract
 * posture: an older client ignores what it can't render rather than guessing a
 * disposition it can't stand behind (Rule #1).
 */
/** States where a source actually ANSWERED — the only ones that may carry a
 *  source + age. The engine already guarantees this; the client re-enforces it
 *  so a divergent payload can never render a fabricated attribution on a
 *  couldn't-verify or not-checked claim (Rule #1). */
const ANSWERED_STATES: ReadonlySet<ConditionStateVM> = new Set([
  'present',
  'stale-degraded',
  'no-hazard',
  'no-data',
])

function mapConditions(wire: ConditionStatusResponse[] | undefined): ConditionStatusVM[] | undefined {
  if (!wire) return undefined
  const mapped: ConditionStatusVM[] = []
  for (const s of wire) {
    const state = WIRE_CONDITION_STATES[s.state]
    if (!state) continue
    const answered = ANSWERED_STATES.has(state)
    mapped.push({
      kind: s.kind,
      state,
      source: answered ? s.source || undefined : undefined,
      checkedAgo: answered && s.checked_at ? relativeAge(s.checked_at) : undefined,
      detail: s.detail || undefined,
    })
  }
  return mapped
}

/**
 * Wire → VM for the maps/terrain payload. A trailhead is required for any map
 * surface (even the trailhead-only state), so a card without one yields no
 * `geo`. The dashed "approximate route" derives from the geometry's confidence
 * tier (D5): anything below `stated` is drawn dashed.
 */
function mapGeo(c: FeedCardResponse): TrailGeo | undefined {
  if (!c.trailhead) return undefined
  const quality = isApproximate(c.geometry_confidence) ? 'approximate' : 'confident'
  // Fail loudly at the boundary: a present-but-undrawable geometry (empty or
  // single-point coordinates from a malformed payload) becomes the honest
  // trailhead-only state, never an empty line that crashes the map math.
  return {
    geometry: isDrawableRoute(c.geometry ?? null) ? (c.geometry ?? null) : null,
    trailhead: { lat: c.trailhead.lat, lon: c.trailhead.lon, derived: c.trailhead.derived ?? false },
    quality,
    summit: c.summit ? { lat: c.summit.lat, lon: c.summit.lon } : undefined,
    elevationProfile: mapElevationProfile(c.elevation_profile),
  }
}

const isApproximate = (level: ConfidenceLevel | undefined): boolean =>
  level === 'hedged' || level === 'flagged'

/**
 * Wire → VM for the water answer (Epic 041). A null/absent wire field is the
 * CDP-02 not-fetched silence and maps to null (no row); the two answered
 * states pass through with the snake_case → kebab-case rename. Optional
 * per-source fields collapse `null` → `undefined` at this boundary so the VM
 * stays idiomatic. Everything here is `provenance: 'live'` — it came off the
 * real API — even though the FACT is corpus data the surface must still hedge
 * as "not verified live" (the hedge is copy-level, not provenance-level).
 */
function mapTrailWater(wire: WireTrailWater | null | undefined): TrailWaterVM | null {
  if (!wire) return null
  // Only the two known answered states pass; anything else (a future wire
  // state this client can't render) degrades to silence rather than guessing
  // a disposition it can't stand behind (the mapConditions posture, Rule #1).
  if (wire.state !== 'sources' && wire.state !== 'none_nearby') return null
  return {
    state: wire.state === 'none_nearby' ? 'none-nearby' : 'sources',
    basis: wire.basis,
    radiusM: wire.radius_m,
    source: wire.source,
    sources: wire.sources.map((w) => ({
      id: w.water_id,
      type: w.water_type,
      name: w.name ?? undefined,
      lat: w.lat,
      lon: w.lon,
      distanceM: w.distance_m,
      seasonal: w.seasonal ?? undefined,
    })),
    provenance: 'live',
  }
}

function mapElevationProfile(p: WireElevationProfile | null | undefined): ElevationProfile | null {
  if (!p) return null
  return {
    samples: p.samples.map((s) => ({ distanceMeters: s.distance_m, elevationMeters: s.elevation_m })),
    totalGainMeters: p.total_gain_m,
    totalLossMeters: p.total_loss_m,
    maxGradePercent: p.max_grade_pct,
    source: p.source,
    resolutionMeters: p.resolution_m,
    estimatedDurationMin: p.estimated_duration_min,
  }
}

export class HttpPlannerClient implements PlannerClient {
  /** `originCoords` is the config-driven origin→coordinates map (Phase 2), fetched
   *  once from `GET /regions` and injected by `PlannerProvider` — never a static
   *  import here, so this adapter carries no hardcoded per-region data. */
  constructor(
    private readonly baseUrl: string,
    private readonly originCoords: Record<string, Coords> = {},
  ) {}

  async plan(input: PlanInput, scope: ScopeContext): Promise<FeedVM> {
    return this.planWith(input, scope, TWO_PHASE)
  }

  /**
   * Trail-name search (Epic 038/B001): POSTs `/search` and maps the response
   * through the SAME `mapFeed` `/plan` uses — the contract is byte-identical
   * to `FeedResponse`, so there is exactly one card-mapping truth for both
   * surfaces (never a second one that could drift). Shares `/plan`'s 60s
   * cold-start budget since search runs through the same engine/host.
   */
  async search(query: string, scope: ScopeContext, k?: number): Promise<FeedVM> {
    const body: SearchRequest = { query, k: k ?? 10 }
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), PLAN_TIMEOUT_MS)
    try {
      const resp = await fetch(`${this.baseUrl}/search`, {
        method: 'POST',
        headers: authHeaders(scope),
        body: JSON.stringify(body),
        signal: controller.signal,
      })
      if (!resp.ok) {
        return emptyFeed({ tuning: fallbackTuning() }, classify(null, resp.status), query)
      }
      return mapFeed((await resp.json()) as SearchResponse)
    } catch (err) {
      return emptyFeed({ tuning: fallbackTuning() }, classify(err), query)
    } finally {
      clearTimeout(timer)
    }
  }

  /**
   * The shared /plan POST. `twoPhase=false` forces the classic single-pass
   * response — `getCard`'s deep-link refetch uses it so Detail NEVER resolves a
   * card from an unverified phase-1 frame (the D4 snapshot rule, applied to the
   * refetch path too).
   */
  private async planWith(input: PlanInput, scope: ScopeContext, twoPhase: boolean): Promise<FeedVM> {
    // A live "Near me" fix overrides the named origin's fixed coordinates so
    // /plan searches from the viewer's actual position; absent that, the named
    // origin lookup is unchanged.
    const { lat, lon } =
      input.tuning.originCoords ?? this.originCoords[input.tuning.origin] ?? FALLBACK_COORDS
    const body: PlanRequest = {
      query: buildQuery(input.tuning),
      lat,
      lon,
      k: input.k ?? 10,
      viewer_id: scope.viewerId,
      // Two-phase (Epic 040): ask for cards-first; the response self-describes
      // completeness, so a kill-switched server or a warm key degrades to the
      // classic flow with no client branching beyond `conditionsPending`.
      ...(twoPhase ? { phase: 'cards' as const } : {}),
    }
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), PLAN_TIMEOUT_MS)
    try {
      const resp = await fetch(`${this.baseUrl}/plan`, {
        method: 'POST',
        headers: authHeaders(scope),
        body: JSON.stringify(body),
        signal: controller.signal,
      })
      if (!resp.ok) {
        return emptyFeed(input, classify(null, resp.status))
      }
      return mapFeed((await resp.json()) as FeedResponse)
    } catch (err) {
      return emptyFeed(input, classify(err))
    } finally {
      clearTimeout(timer)
    }
  }

  /**
   * The phase-2 patch (Epic 040 S2): POSTs the same key inputs as `plan` plus
   * the phase-1 card ids, and maps the verified overlay through the SAME
   * line/warning/condition mappers the full feed uses. Rejects on any failure —
   * `useFeed` owns the calm "couldn't verify" surface (never a fake-clear).
   */
  async planConditions(input: PlanInput, scope: ScopeContext, canonicalIds: string[]): Promise<ConditionsPatchVM> {
    const { lat, lon } =
      input.tuning.originCoords ?? this.originCoords[input.tuning.origin] ?? FALLBACK_COORDS
    const body: PlanConditionsRequest = {
      query: buildQuery(input.tuning),
      lat,
      lon,
      k: input.k ?? 10,
      viewer_id: scope.viewerId,
      canonical_ids: canonicalIds,
    }
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), PLAN_TIMEOUT_MS)
    try {
      const resp = await fetch(`${this.baseUrl}/plan/conditions`, {
        method: 'POST',
        headers: authHeaders(scope),
        body: JSON.stringify(body),
        signal: controller.signal,
      })
      if (!resp.ok) throw new Error(`conditions failed: ${resp.status}`)
      const res = (await resp.json()) as PlanConditionsResponse
      return {
        patches: res.patches.map((p) => ({
          id: p.canonical_id,
          conditionLines: mapLines(p.lines),
          conditions: mapConditions(p.conditions),
          warnings: mapWarnings(p.warnings),
        })),
        heldBack: (res.set_aside ?? []).map((s) => ({
          id: s.canonical_id,
          name: s.name,
          reasons: s.reasons.map((r) => ({ text: r.text, source: r.source, kind: r.kind })),
        })),
      }
    } finally {
      clearTimeout(timer)
    }
  }

  async getCard(id: string, scope: ScopeContext, tuning?: TuningState): Promise<CardVM | null> {
    // GET /trail/{id}/card returns a FeedResponse with one verified card (Epic 045 S3),
    // so we call it directly instead of re-running /plan. A direct id match is
    // unambiguous and carries sourced+timestamped conditions for any trail, not just
    // those in the current origin-based top-K. Unknown id → honest-empty FeedResponse
    // (never 404, never error). Anonymous-capable (a trail's conditions are the same
    // for everyone). A transient failure (cold start timeout) must throw (not masquerade
    // as notfound) so useCard maps it to error state (R1).
    try {
      const params = new URLSearchParams({ viewer_id: scope.viewerId })
      const resp = await fetch(`${this.baseUrl}/trail/${encodeURIComponent(id)}/card?${params}`, {
        headers: authHeaders(scope),
      })
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const feedResp = (await resp.json()) as FeedResponse
      // Map through the SAME shared mapFeed the feed uses (id ← canonical_id, lines →
      // conditionLines, geo/elevation) so a deep-linked card is byte-identical to a
      // feed-tapped one — never the raw wire shape (whose `id` is undefined).
      const feed = mapFeed(feedResp)
      return feed.cards.length === 0 ? null : feed.cards[0]
    } catch (error) {
      // A transient failure (network, timeout, 5xx) must throw so useCard treats it
      // as retryable error, not a genuine "not found" (R1).
      throw error
    }
  }

  async trailWater(id: string, scope: ScopeContext): Promise<TrailWaterVM | null> {
    // GET /trail/{id} → the `water_sources` slice (Epic 041). Every failure
    // path — network, 404, 5xx, timeout — degrades to null (honest silence:
    // Detail renders no water row), never an error surface: water is
    // enrichment on the commitment view, not a dependency.
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), WATER_TIMEOUT_MS)
    try {
      const params = new URLSearchParams({ viewer_id: scope.viewerId })
      const resp = await fetch(`${this.baseUrl}/trail/${encodeURIComponent(id)}?${params}`, {
        headers: authHeaders(scope),
        signal: controller.signal,
      })
      if (!resp.ok) return null
      const detail = (await resp.json()) as TrailDetailWaterSlice
      return mapTrailWater(detail.water_sources)
    } catch {
      return null
    } finally {
      clearTimeout(timer)
    }
  }

  async recentEpisodes(): Promise<EpisodeVM[]> {
    // No episode list endpoint exists (backend ask #1). Until it lands, the
    // live adapter has no hikes to show rather than inventing any.
    return []
  }

  async getEpisode(): Promise<EpisodeVM | null> {
    return null
  }

  async recordOutcome(
    episodeId: string,
    body: OutcomeBody,
    companions: EpisodeVM['companions'],
    scope: ScopeContext,
  ): Promise<OutcomeVM> {
    // The POST contract is real; companions have no wire field yet (backend
    // gap), so they are not sent — captured client-side only.
    const params = new URLSearchParams({ viewer_id: scope.viewerId })
    const resp = await fetch(`${this.baseUrl}/episode/${encodeURIComponent(episodeId)}/outcome?${params}`, {
      method: 'POST',
      headers: authHeaders(scope),
      body: JSON.stringify(body),
    })
    if (!resp.ok) throw new Error(`outcome failed: ${resp.status}`)
    const out = (await resp.json()) as OutcomeResponse
    return {
      outcomeId: out.outcome_id,
      episodeId: out.episode_id,
      overall: out.overall,
      skipped: out.skipped,
      companions,
    }
  }
}

/** `queryOverride` lets `search()` report the actual query text (there's no
 *  `input.tuning.prompt` for a name search) without a second empty-feed shape. */
function emptyFeed(input: PlanInput, error: FeedError, queryOverride?: string): FeedVM {
  return {
    query: queryOverride ?? input.tuning.prompt,
    cards: [],
    notices: [],
    setAside: [],
    heldBack: [],
    readiness: { on: false, state: 'off' },
    dataSource: 'live',
    error,
  }
}

// The last resort when there's no current tuning at all — a genuinely cold
// deep-link with nothing in context yet. Mirrors App's own default frame.
function fallbackTuning(): TuningState {
  return {
    origin: 'frontRoyal',
    when: 'weekendMorning',
    effort: 'moderate',
    party: 'solo',
    today: 'standard',
    readinessOn: false,
    prompt: '',
  }
}
