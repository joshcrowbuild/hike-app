import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { HttpPlannerClient } from './httpPlanner'
import { ANON_SCOPE, type ScopeContext, type FeedResponse, type OutcomeResponse } from '../api'
import type { PlanInput } from '../source'
import type { TuningState } from '../../types'

const JOSH: ScopeContext = { viewerId: 'josh', grantedIds: [] }

const TUNING: TuningState = {
  origin: 'frontRoyal',
  when: 'weekendMorning',
  effort: 'moderate',
  party: 'solo',
  today: 'standard',
  readinessOn: false,
  prompt: '',
}
const PLAN_INPUT: PlanInput = { tuning: TUNING }

const FEED: FeedResponse = { query: '', cards: [], card_count: 0, notices: [] }
const OUTCOME: OutcomeResponse = { outcome_id: 'o1', episode_id: 'e1', skipped: false, overall: 2 }

function headersOf(call: unknown): Record<string, string> {
  const init = (call as [string, RequestInit])[1]
  return init.headers as Record<string, string>
}

describe('HttpPlannerClient auth headers', () => {
  const SECRET = 'dev-secret-value'
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.stubEnv('VITE_DEV_VIEWER_SECRET', SECRET)
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
  })

  function ok(json: unknown) {
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(json) } as Response)
  }

  it('sends the dev-viewer secret on /plan for a non-anonymous viewer', async () => {
    fetchMock.mockReturnValue(ok(FEED))
    await new HttpPlannerClient('http://api').plan(PLAN_INPUT, JOSH)
    expect(headersOf(fetchMock.mock.calls[0])['X-Dev-Viewer-Secret']).toBe(SECRET)
  })

  it('omits the secret on /plan for an anonymous viewer', async () => {
    fetchMock.mockReturnValue(ok(FEED))
    await new HttpPlannerClient('http://api').plan(PLAN_INPUT, ANON_SCOPE)
    expect(headersOf(fetchMock.mock.calls[0])).not.toHaveProperty('X-Dev-Viewer-Secret')
  })

  it('sends the dev-viewer secret on /outcome for a non-anonymous viewer', async () => {
    fetchMock.mockReturnValue(ok(OUTCOME))
    await new HttpPlannerClient('http://api').recordOutcome(
      'e1',
      { overall: 2, skipped: false },
      [],
      JOSH,
    )
    expect(headersOf(fetchMock.mock.calls[0])['X-Dev-Viewer-Secret']).toBe(SECRET)
  })

  it('omits the secret on /outcome for an anonymous viewer', async () => {
    fetchMock.mockReturnValue(ok(OUTCOME))
    await new HttpPlannerClient('http://api').recordOutcome(
      'e1',
      { overall: 2, skipped: false },
      [],
      ANON_SCOPE,
    )
    expect(headersOf(fetchMock.mock.calls[0])).not.toHaveProperty('X-Dev-Viewer-Secret')
  })
})

describe('HttpPlannerClient geometry/elevation mapping (Epic 016 S1)', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => vi.unstubAllGlobals())

  const ok = (json: unknown) =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(json) } as Response)

  it('maps wire geometry + trailhead + elevation profile onto the VM geo', async () => {
    const feed: FeedResponse = {
      query: '',
      card_count: 1,
      notices: [],
      cards: [
        {
          canonical_id: 'stony-man',
          name: 'Stony Man Loop',
          distance_mi: 3,
          lines: [],
          warnings: [],
          geometry: { type: 'LineString', coordinates: [[-78.4, 38.5], [-78.39, 38.51]] },
          trailhead: { lat: 38.5, lon: -78.4 },
          geometry_confidence: 'hedged',
          summit: { lat: 38.51, lon: -78.39 },
          elevation_profile: {
            samples: [{ distance_m: 0, elevation_m: 1000 }, { distance_m: 500, elevation_m: 1200 }],
            total_gain_m: 200,
            total_loss_m: 0,
            max_grade_pct: 40,
            source: 'USGS 3DEP',
            resolution_m: 10,
          },
        },
      ],
    }
    fetchMock.mockReturnValue(ok(feed))
    const result = await new HttpPlannerClient('http://api').plan(PLAN_INPUT, ANON_SCOPE)
    const geo = result.cards[0].geo
    expect(geo?.geometry?.type).toBe('LineString')
    expect(geo?.trailhead).toEqual({ lat: 38.5, lon: -78.4 })
    // hedged confidence → drawn as the dashed "approximate" route (D5).
    expect(geo?.quality).toBe('approximate')
    expect(geo?.elevationProfile?.totalGainMeters).toBe(200)
    expect(geo?.elevationProfile?.samples[1]).toEqual({ distanceMeters: 500, elevationMeters: 1200 })
  })

  it('yields no geo when the card carries no trailhead (degrade, not fabricate)', async () => {
    const feed: FeedResponse = {
      query: '',
      card_count: 1,
      notices: [],
      cards: [{ canonical_id: 'x', name: 'X', distance_mi: null, lines: [], warnings: [] }],
    }
    fetchMock.mockReturnValue(ok(feed))
    const result = await new HttpPlannerClient('http://api').plan(PLAN_INPUT, ANON_SCOPE)
    expect(result.cards[0].geo).toBeUndefined()
  })
})
