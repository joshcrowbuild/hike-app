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
import type { FeedResponse, PlanRequest, ScopeContext } from '../api'
import type { PlanInput, PlannerClient } from '../source'
import type { CardVM, FeedError, FeedVM } from '../vm'
import type { OriginKey } from '../../types'

const TIMEOUT_MS = 10_000

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
        headers: { 'content-type': 'application/json' },
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
