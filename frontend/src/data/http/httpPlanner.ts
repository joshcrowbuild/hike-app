/**
 * HttpPlannerClient — the real adapter. Wired but inert until a backend is
 * reachable (the container has no Neo4j tonight). It is real code, not a
 * placeholder: it POSTs the actual `/plan` contract and maps `FeedResponse` →
 * VM with `provenance: 'live'`, dropping the enrichment the API does not supply
 * so the card degrades to its honest-thin rendering. Flipping `VITE_USE_MOCK`
 * off selects this; no screen changes.
 */
import { buildQuery } from '../buildQuery'
import { originCoords } from '../origins'
import type { FeedResponse, OutcomeBody, OutcomeResponse, PlanRequest, ScopeContext } from '../api'
import type { PlanInput, PlannerClient } from '../source'
import type { CardVM, EpisodeVM, FeedError, FeedVM, OutcomeVM } from '../vm'
import type { OriginKey } from '../../types'

const TIMEOUT_MS = 10_000

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

function mapFeed(res: FeedResponse): FeedVM {
  return {
    query: res.query,
    cards: res.cards.map(
      (c): CardVM => ({
        id: c.canonical_id,
        name: c.name,
        distanceMi: c.distance_mi,
        conditionLines: c.lines.map((l) => ({
          text: l.text,
          source: l.source,
          confidence: l.confidence_level,
          provenance: 'live',
        })),
        warnings: c.warnings,
        // The API supplies no rich enrichment yet; the card degrades to thin.
        enrichment: undefined,
      }),
    ),
    notices: res.notices,
    setAside: [],
    // Readiness has no HTTP surface yet (Epic 007 backlog); it stays off.
    readiness: { on: false, state: 'off' },
    dataSource: 'live',
  }
}

export class HttpPlannerClient implements PlannerClient {
  constructor(private readonly baseUrl: string) {}

  async plan(input: PlanInput, scope: ScopeContext): Promise<FeedVM> {
    const { lat, lon } = originCoords[input.tuning.origin]
    const body: PlanRequest = {
      query: buildQuery(input.tuning),
      lat,
      lon,
      k: input.k ?? 10,
      viewer_id: scope.viewerId,
    }
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)
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

  async getCard(id: string, scope: ScopeContext, origin?: OriginKey): Promise<CardVM | null> {
    // No GET /trail/{id} exists yet (backend ask #1/#5). Re-run the plan and
    // resolve the id from the current set; a true deep-link to a card outside
    // the set returns null until the detail endpoint lands.
    void origin
    const feed = await this.plan({ tuning: fallbackTuning(origin) }, scope)
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
    readiness: { on: false, state: 'off' },
    dataSource: 'live',
    error,
  }
}

function fallbackTuning(origin?: OriginKey) {
  return {
    origin: origin ?? 'frontRoyal',
    when: 'weekendMorning',
    effort: 'moderate',
    party: 'solo',
    today: 'standard',
    readinessOn: false,
    prompt: '',
  } as const
}
