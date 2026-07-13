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
  WireElevationProfile,
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
 * Scoped requests carry the dev-viewer secret so the backend's fail-closed
 * `_authorize_viewer` admits a non-anonymous viewer. Anonymous browsing needs
 * no secret. The secret lives only in `.env` (Rule #10) — never in the repo.
 */
function authHeaders(scope: ScopeContext): HeadersInit {
  const base: HeadersInit = { 'content-type': 'application/json' }
  if (scope.viewerId === 'anonymous') return base
  return { ...base, 'X-Dev-Viewer-Secret': import.meta.env.VITE_DEV_VIEWER_SECRET ?? '' }
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
    source: l.source,
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
    // No GET /trail/{id} exists yet (backend ask #1/#5), so `useCard` only calls
    // this when the id isn't already in the in-memory feed. Re-run the plan with
    // the CALLER'S current tuning (never a rebuilt default — a reset frame
    // returns a different, often thinner, set that may not contain the card,
    // which is what made every non-default-origin trail read as "not found").
    // A true deep-link to a card outside the set still returns null. Always
    // the FULL single-pass response (twoPhase=false): a card handed to Detail
    // must carry verified conditions, never a phase-1 frame's pending silence.
    const feed = await this.planWith({ tuning: tuning ?? fallbackTuning() }, scope, false)
    // A transient failure (notably the cold-start timeout this branch now waits
    // out for up to 60s) must not masquerade as "not found": throw so `useCard`
    // maps it to a retryable error state, not an authoritative absence (R1).
    if (feed.error) throw new Error(feed.error.message)
    return feed.cards.find((c) => c.id === id) ?? null
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

function emptyFeed(input: PlanInput, error: FeedError): FeedVM {
  return {
    query: input.tuning.prompt,
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
