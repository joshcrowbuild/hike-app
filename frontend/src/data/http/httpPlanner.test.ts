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

describe('HttpPlannerClient hazard warnings + held-back mapping (2026-07-01)', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-07-01T22:00:00Z'))
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  const ok = (json: unknown) =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(json) } as Response)

  it('maps a verified hazard onto the card as a source-stamped, aged warning — the trail shows', async () => {
    const feed: FeedResponse = {
      query: '',
      card_count: 1,
      notices: [],
      cards: [
        {
          canonical_id: 'compton-peak',
          name: 'Compton Peak',
          distance_mi: 2.1,
          lines: [],
          warnings: [
            {
              text: 'weather alert: Extreme Heat Warning',
              source: 'NWS api.weather.gov',
              observed_at: '2026-07-01T20:00:00Z',
              kind: 'weather',
            },
          ],
        },
      ],
    }
    fetchMock.mockReturnValue(ok(feed))
    const result = await new HttpPlannerClient('http://api').plan(PLAN_INPUT, ANON_SCOPE)
    expect(result.cards).toHaveLength(1) // shown, never hidden
    expect(result.cards[0].warnings).toEqual([
      {
        text: 'weather alert: Extreme Heat Warning',
        source: 'NWS api.weather.gov',
        observedAgo: '2h ago', // humanised — never a raw datetime (§7.2)
        kind: 'weather',
        provenance: 'live',
      },
    ])
  })

  it('maps set_aside (the unverifiable class) onto heldBack so nothing silently vanishes', async () => {
    const feed: FeedResponse = {
      query: '',
      card_count: 0,
      notices: [],
      cards: [],
      set_aside: [
        {
          canonical_id: 'foggy-hollow',
          name: 'Foggy Hollow',
          reasons: [
            {
              text: "weather alerts couldn't be verified (NWS api.weather.gov)",
              source: 'NWS api.weather.gov',
              kind: 'weather',
            },
          ],
        },
      ],
    }
    fetchMock.mockReturnValue(ok(feed))
    const result = await new HttpPlannerClient('http://api').plan(PLAN_INPUT, ANON_SCOPE)
    expect(result.heldBack).toEqual([
      {
        id: 'foggy-hollow',
        name: 'Foggy Hollow',
        reasons: [
          {
            text: "weather alerts couldn't be verified (NWS api.weather.gov)",
            source: 'NWS api.weather.gov',
            kind: 'weather',
          },
        ],
      },
    ])
  })

  it('degrades an absent set_aside to an honest empty heldBack', async () => {
    fetchMock.mockReturnValue(ok(FEED))
    const result = await new HttpPlannerClient('http://api').plan(PLAN_INPUT, ANON_SCOPE)
    expect(result.heldBack).toEqual([])
  })
})

describe('HttpPlannerClient /plan cold-start timeout', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  beforeEach(() => {
    vi.useFakeTimers()
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  // A fetch that never resolves on its own, only when its abort signal fires —
  // models the Render free-tier cold start the client has to wait out.
  function hangingFetch(): AbortSignal {
    let signal!: AbortSignal
    fetchMock.mockImplementation((_url: string, init: RequestInit) => {
      signal = init.signal as AbortSignal
      return new Promise((_resolve, reject) => {
        signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
      })
    })
    // Capture the signal on first call; the returned ref is read after plan() runs.
    return new Proxy({} as AbortSignal, { get: (_t, p) => Reflect.get(signal, p, signal) })
  }

  it('does not abort /plan at the old 10s budget, but does at exactly 60s (cold-start fix)', async () => {
    const signal = hangingFetch()
    const promise = new HttpPlannerClient('http://api').plan(PLAN_INPUT, ANON_SCOPE)

    // The old 10s timeout would have aborted here — it must not anymore.
    await vi.advanceTimersByTimeAsync(10_000)
    expect(signal.aborted).toBe(false)

    // Pin the exact 60s boundary so a mid-range regression (e.g. 30s, which may
    // not clear a real cold start) is caught: still in flight at 59.999s...
    await vi.advanceTimersByTimeAsync(49_999)
    expect(signal.aborted).toBe(false)

    // ...aborts on the next tick, classified as a calm "timeout" FeedError.
    await vi.advanceTimersByTimeAsync(1)
    const feed = await promise
    expect(signal.aborted).toBe(true)
    expect(feed.error?.kind).toBe('timeout')
    expect(feed.cards).toEqual([])
  })
})
