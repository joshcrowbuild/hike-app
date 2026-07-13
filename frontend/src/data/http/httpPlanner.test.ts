import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { HttpPlannerClient } from './httpPlanner'
import { ANON_SCOPE, type ScopeContext, type FeedResponse, type OutcomeResponse } from '../api'
import type { PlanInput } from '../source'
import type { Coords, TuningState } from '../../types'

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

// The config-driven origin catalog (Phase 2) as `PlannerProvider` would inject it
// after `GET /regions` resolves — a small fixture standing in for that fetch, not
// a static map the client imports itself.
const ORIGIN_COORDS: Record<string, Coords> = {
  frontRoyal: { lat: 38.918, lon: -78.194 },
  nagsHead: { lat: 35.957, lon: -75.624 },
}

function client(): HttpPlannerClient {
  return new HttpPlannerClient('http://api', ORIGIN_COORDS)
}

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
    await client().plan(PLAN_INPUT, JOSH)
    expect(headersOf(fetchMock.mock.calls[0])['X-Dev-Viewer-Secret']).toBe(SECRET)
  })

  it('omits the secret on /plan for an anonymous viewer', async () => {
    fetchMock.mockReturnValue(ok(FEED))
    await client().plan(PLAN_INPUT, ANON_SCOPE)
    expect(headersOf(fetchMock.mock.calls[0])).not.toHaveProperty('X-Dev-Viewer-Secret')
  })

  it('sends the dev-viewer secret on /outcome for a non-anonymous viewer', async () => {
    fetchMock.mockReturnValue(ok(OUTCOME))
    await client().recordOutcome(
      'e1',
      { overall: 2, skipped: false },
      [],
      JOSH,
    )
    expect(headersOf(fetchMock.mock.calls[0])['X-Dev-Viewer-Secret']).toBe(SECRET)
  })

  it('omits the secret on /outcome for an anonymous viewer', async () => {
    fetchMock.mockReturnValue(ok(OUTCOME))
    await client().recordOutcome(
      'e1',
      { overall: 2, skipped: false },
      [],
      ANON_SCOPE,
    )
    expect(headersOf(fetchMock.mock.calls[0])).not.toHaveProperty('X-Dev-Viewer-Secret')
  })
})

describe('HttpPlannerClient per-fact sources (Epic 026a — honest corroboration contract)', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => vi.unstubAllGlobals())

  const ok = (json: unknown) =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(json) } as Response)

  it('carries a live line’s real sources onto the VM, unmodified', async () => {
    const feed: FeedResponse = {
      query: '',
      card_count: 1,
      notices: [],
      cards: [
        {
          canonical_id: 'stony-man',
          name: 'Stony Man Loop',
          distance_mi: 3.7,
          lines: [
            { text: 'Sunny 70°F · NWS, 10m ago', source: 'NWS api.weather.gov', confidence_level: 'stated', sources: ['NWS'] },
          ],
          warnings: [],
          unavailable: [],
        },
      ],
    }
    fetchMock.mockReturnValue(ok(feed))
    const result = await client().plan(PLAN_INPUT, ANON_SCOPE)
    const line = result.cards[0].conditionLines[0]
    expect(line.provenance).toBe('live')
    expect(line.sources).toEqual(['NWS'])
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
          unavailable: [],
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
            estimated_duration_min: 26,
          },
        },
      ],
    }
    fetchMock.mockReturnValue(ok(feed))
    const result = await client().plan(PLAN_INPUT, ANON_SCOPE)
    const geo = result.cards[0].geo
    expect(geo?.geometry?.type).toBe('LineString')
    // A surveyed trailhead (no `derived` on the wire) → derived:false, never approximate.
    expect(geo?.trailhead).toEqual({ lat: 38.5, lon: -78.4, derived: false })
    // hedged confidence → drawn as the dashed "approximate" route (D5).
    expect(geo?.quality).toBe('approximate')
    expect(geo?.elevationProfile?.totalGainMeters).toBe(200)
    expect(geo?.elevationProfile?.samples[1]).toEqual({ distanceMeters: 500, elevationMeters: 1200 })
    expect(geo?.elevationProfile?.estimatedDurationMin).toBe(26)
  })

  it('threads a derived (approximate) access point onto the VM start marker (D7)', async () => {
    const feed: FeedResponse = {
      query: '',
      card_count: 1,
      notices: [],
      cards: [
        {
          canonical_id: 'duck-boardwalk',
          name: 'Duck Boardwalk',
          distance_mi: 0.3,
          lines: [],
          warnings: [],
          unavailable: [],
          geometry: { type: 'LineString', coordinates: [[-75.75, 36.17], [-75.74, 36.18]] },
          // No surveyed trailhead: the backend disclosed the start as derived.
          trailhead: { lat: 36.17, lon: -75.75, derived: true },
          geometry_confidence: 'stated',
          summit: null,
          elevation_profile: null,
        },
      ],
    }
    fetchMock.mockReturnValue(ok(feed))
    const result = await client().plan(PLAN_INPUT, ANON_SCOPE)
    expect(result.cards[0].geo?.trailhead).toEqual({ lat: 36.17, lon: -75.75, derived: true })
  })

  it('yields no geo when the card carries no trailhead (degrade, not fabricate)', async () => {
    const feed: FeedResponse = {
      query: '',
      card_count: 1,
      notices: [],
      cards: [{ canonical_id: 'x', name: 'X', distance_mi: null, lines: [], warnings: [], unavailable: [] }],
    }
    fetchMock.mockReturnValue(ok(feed))
    const result = await client().plan(PLAN_INPUT, ANON_SCOPE)
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
          unavailable: [],
        },
      ],
    }
    fetchMock.mockReturnValue(ok(feed))
    const result = await client().plan(PLAN_INPUT, ANON_SCOPE)
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
    const result = await client().plan(PLAN_INPUT, ANON_SCOPE)
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
    const result = await client().plan(PLAN_INPUT, ANON_SCOPE)
    expect(result.heldBack).toEqual([])
  })
})

describe('HttpPlannerClient per-kind condition states (Epic 018 S4f / CDP-02)', () => {
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

  const cardWith = (conditions?: FeedResponse['cards'][number]['conditions']): FeedResponse => ({
    query: '',
    card_count: 1,
    notices: [],
    cards: [
      {
        canonical_id: 'compton-peak',
        name: 'Compton Peak',
        distance_mi: 2.1,
        lines: [],
        warnings: [],
        unavailable: [],
        ...(conditions ? { conditions } : {}),
      },
    ],
  })

  it('maps all six wire states onto the VM, humanising checked_at (§7.2)', async () => {
    fetchMock.mockReturnValue(
      ok(
        cardWith([
          { kind: 'weather', state: 'present', source: 'NWS', checked_at: '2026-07-01T21:48:00Z', detail: '' },
          { kind: 'air', state: 'stale_degraded', source: 'EPA AirNow', checked_at: '2026-07-01T19:00:00Z', detail: '' },
          { kind: 'fire', state: 'no_hazard', source: 'NASA FIRMS', checked_at: '2026-07-01T21:40:00Z', detail: '' },
          {
            kind: 'water',
            state: 'no_data',
            source: 'USGS',
            checked_at: '2026-07-01T21:45:00Z',
            detail: 'no gauge within 30 mi',
          },
          { kind: 'closures', state: 'unavailable', source: '', checked_at: null, detail: '' },
          { kind: 'permits', state: 'not_fetched', source: '', checked_at: null, detail: '' },
        ]),
      ),
    )
    const result = await client().plan(PLAN_INPUT, ANON_SCOPE)
    expect(result.cards[0].conditions).toEqual([
      { kind: 'weather', state: 'present', source: 'NWS', checkedAgo: '12m ago', detail: undefined },
      { kind: 'air', state: 'stale-degraded', source: 'EPA AirNow', checkedAgo: '3h ago', detail: undefined },
      { kind: 'fire', state: 'no-hazard', source: 'NASA FIRMS', checkedAgo: '20m ago', detail: undefined },
      { kind: 'water', state: 'no-data', source: 'USGS', checkedAgo: '15m ago', detail: 'no gauge within 30 mi' },
      { kind: 'closures', state: 'unavailable', source: undefined, checkedAgo: undefined, detail: undefined },
      { kind: 'permits', state: 'not-fetched', source: undefined, checkedAgo: undefined, detail: undefined },
    ])
  })

  it('retires the lines.length===0 heuristic: an answered card gets NO blanket silence (#160 mislabel)', async () => {
    // A lineless card whose kinds all answered clear/no-data must never read
    // "not checked" — the per-kind payload is the authoritative rendering.
    fetchMock.mockReturnValue(
      ok(
        cardWith([
          { kind: 'fire', state: 'no_hazard', source: 'NASA FIRMS', checked_at: '2026-07-01T21:40:00Z', detail: '' },
        ]),
      ),
    )
    const result = await client().plan(PLAN_INPUT, ANON_SCOPE)
    expect(result.cards[0].conditionSilence).toBeUndefined()
    expect(result.cards[0].conditions).toHaveLength(1)
  })

  it('keeps the honest not-fetched fallback ONLY for an older payload with no conditions field', async () => {
    fetchMock.mockReturnValue(ok(cardWith(undefined)))
    const result = await client().plan(PLAN_INPUT, ANON_SCOPE)
    expect(result.cards[0].conditions).toBeUndefined()
    expect(result.cards[0].conditionSilence).toEqual({ state: 'not-fetched' })
  })

  it('strips source/age from an UNANSWERED state — a divergent payload can never fabricate an attribution', async () => {
    // The engine never sets source/checked_at on unavailable/not_fetched; the
    // client re-enforces that (Rule #1) so "couldn't verify (USGS · 2h ago)"
    // is unrenderable even from a divergent or stored payload.
    fetchMock.mockReturnValue(
      ok(
        cardWith([
          { kind: 'water', state: 'unavailable', source: 'USGS', checked_at: '2026-07-01T20:00:00Z', detail: '' },
          { kind: 'air', state: 'not_fetched', source: 'EPA AirNow', checked_at: '2026-07-01T20:00:00Z', detail: '' },
        ]),
      ),
    )
    const result = await client().plan(PLAN_INPUT, ANON_SCOPE)
    expect(result.cards[0].conditions).toEqual([
      { kind: 'water', state: 'unavailable', source: undefined, checkedAgo: undefined, detail: undefined },
      { kind: 'air', state: 'not-fetched', source: undefined, checkedAgo: undefined, detail: undefined },
    ])
  })

  it('drops a wire state this client does not know rather than guessing a disposition', async () => {
    fetchMock.mockReturnValue(
      ok(
        cardWith([
          { kind: 'weather', state: 'some_future_state', source: 'NWS', checked_at: null, detail: '' },
          { kind: 'permits', state: 'not_fetched', source: '', checked_at: null, detail: '' },
        ]),
      ),
    )
    const result = await client().plan(PLAN_INPUT, ANON_SCOPE)
    expect(result.cards[0].conditions).toEqual([
      { kind: 'permits', state: 'not-fetched', source: undefined, checkedAgo: undefined, detail: undefined },
    ])
  })
})

describe('HttpPlannerClient getCard fallback refetch (OBX "not in your current set" fix)', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => vi.unstubAllGlobals())

  const ok = (json: unknown) =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(json) } as Response)

  function coordsOf(call: unknown): { lat: number; lon: number } {
    const init = (call as [string, RequestInit])[1]
    const body = JSON.parse(init.body as string) as { lat: number; lon: number }
    return { lat: body.lat, lon: body.lon }
  }

  it('refetches with the CALLER-SUPPLIED tuning, not a rebuilt default — a non-default origin still resolves', async () => {
    const nagsHead: TuningState = { ...TUNING, origin: 'nagsHead' }
    const feed: FeedResponse = {
      query: '',
      card_count: 1,
      notices: [],
      cards: [
        {
          canonical_id: 'jockeys-ridge',
          name: "Jockey's Ridge",
          distance_mi: 1,
          lines: [],
          warnings: [],
          unavailable: [],
        },
      ],
    }
    fetchMock.mockReturnValue(ok(feed))
    const card = await client().getCard('jockeys-ridge', ANON_SCOPE, nagsHead)

    expect(card?.id).toBe('jockeys-ridge')
    // Nags Head's coordinates, not Front Royal's default — proves the fallback
    // never rebuilds a fresh default tuning when a caller tuning is supplied.
    expect(coordsOf(fetchMock.mock.calls[0])).toEqual({ lat: 35.957, lon: -75.624 })
  })

  it('falls back to the Front Royal default only when no tuning at all is supplied (true cold link)', async () => {
    fetchMock.mockReturnValue(ok(FEED))
    await client().getCard('some-id', ANON_SCOPE)
    expect(coordsOf(fetchMock.mock.calls[0])).toEqual({ lat: 38.918, lon: -78.194 })
  })

  it('returns null for a genuine absence (id not in the refetched set)', async () => {
    fetchMock.mockReturnValue(ok(FEED))
    const card = await client().getCard('no-such-trail', ANON_SCOPE, TUNING)
    expect(card).toBeNull()
  })

  it('throws — never a false "not found" — when the refetch itself fails (R1: stays retryable)', async () => {
    fetchMock.mockReturnValue(Promise.resolve({ ok: false, status: 503 } as Response))
    await expect(
      client().getCard('some-id', ANON_SCOPE, TUNING),
    ).rejects.toThrow()
  })
})

describe('HttpPlannerClient "Near me" live-coords override', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => vi.unstubAllGlobals())

  const ok = (json: unknown) =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(json) } as Response)

  function coordsOf(call: unknown): { lat: number; lon: number } {
    const init = (call as [string, RequestInit])[1]
    const body = JSON.parse(init.body as string) as { lat: number; lon: number }
    return { lat: body.lat, lon: body.lon }
  }

  it('sends the live originCoords fix instead of the named origin lookup when present', async () => {
    fetchMock.mockReturnValue(ok(FEED))
    const nearMe: TuningState = { ...TUNING, originCoords: { lat: 39.123, lon: -77.456 } }
    await client().plan({ tuning: nearMe }, ANON_SCOPE)
    expect(coordsOf(fetchMock.mock.calls[0])).toEqual({ lat: 39.123, lon: -77.456 })
  })

  it('falls back to the named origin lookup when originCoords is absent (named origins unchanged)', async () => {
    fetchMock.mockReturnValue(ok(FEED))
    await client().plan(PLAN_INPUT, ANON_SCOPE)
    expect(coordsOf(fetchMock.mock.calls[0])).toEqual({ lat: 38.918, lon: -78.194 })
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
    const promise = client().plan(PLAN_INPUT, ANON_SCOPE)

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

describe('HttpPlannerClient two-phase flow (Epic 040)', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  function ok(json: unknown) {
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(json) } as Response)
  }
  function bodyOf(call: unknown): Record<string, unknown> {
    return JSON.parse(((call as [string, RequestInit])[1] as { body: string }).body)
  }
  function urlOf(call: unknown): string {
    return (call as [string, RequestInit])[0]
  }

  it('asks /plan for phase:"cards" (two-phase enabled by default)', async () => {
    fetchMock.mockReturnValue(ok(FEED))
    await client().plan(PLAN_INPUT, ANON_SCOPE)
    expect(bodyOf(fetchMock.mock.calls[0]).phase).toBe('cards')
  })

  it('marks the VM pending ONLY on an explicit conditions_complete:false', async () => {
    fetchMock.mockReturnValueOnce(ok({ ...FEED, conditions_complete: false }))
    const pending = await client().plan(PLAN_INPUT, ANON_SCOPE)
    expect(pending.conditionsPending).toBe(true)

    // Absent (older backend) and explicit true both mean complete — absence is
    // never read as pending (the additive-contract posture).
    fetchMock.mockReturnValueOnce(ok(FEED))
    const legacy = await client().plan(PLAN_INPUT, ANON_SCOPE)
    expect(legacy.conditionsPending).toBeUndefined()

    fetchMock.mockReturnValueOnce(ok({ ...FEED, conditions_complete: true }))
    const complete = await client().plan(PLAN_INPUT, ANON_SCOPE)
    expect(complete.conditionsPending).toBeUndefined()
  })

  it('planConditions POSTs the same key inputs plus the ids, and maps the patch through the shared mappers', async () => {
    fetchMock.mockReturnValue(
      ok({
        patches: [
          {
            canonical_id: 'ct:a',
            lines: [{ text: 'Clear skies', source: 'nws', confidence_level: 'stated', sources: ['NWS'] }],
            warnings: [
              { text: 'weather alert: Heat', source: 'NWS', observed_at: new Date().toISOString(), kind: 'weather' },
            ],
            conditions: [
              { kind: 'weather', state: 'present', source: 'NWS', checked_at: new Date().toISOString(), detail: '' },
            ],
          },
        ],
        set_aside: [
          {
            canonical_id: 'ct:smoky',
            name: 'Smoky',
            reasons: [{ text: 'air quality hazardous (AirNow)', source: 'AirNow', kind: 'air' }],
          },
        ],
        unknown: ['ct:ghost'],
      }),
    )

    const patch = await client().planConditions(PLAN_INPUT, ANON_SCOPE, ['ct:a', 'ct:smoky', 'ct:ghost'])

    expect(urlOf(fetchMock.mock.calls[0])).toBe('http://api/plan/conditions')
    const body = bodyOf(fetchMock.mock.calls[0])
    expect(body.canonical_ids).toEqual(['ct:a', 'ct:smoky', 'ct:ghost'])
    expect(body.lat).toBeCloseTo(38.918) // same origin resolution as plan()
    expect(patch.patches[0].id).toBe('ct:a')
    expect(patch.patches[0].conditionLines[0]).toMatchObject({
      text: 'Clear skies',
      provenance: 'live',
      sources: ['NWS'],
    })
    expect(patch.patches[0].conditions?.[0]).toMatchObject({ kind: 'weather', state: 'present', source: 'NWS' })
    expect(patch.patches[0].warnings[0].source).toBe('NWS')
    expect(patch.heldBack[0]).toMatchObject({ id: 'ct:smoky', name: 'Smoky' })
  })

  it('planConditions rejects on a non-OK response — the caller owns the calm retry, never a fake-clear', async () => {
    fetchMock.mockReturnValue(Promise.resolve({ ok: false, status: 500 } as Response))
    await expect(client().planConditions(PLAN_INPUT, ANON_SCOPE, ['ct:a'])).rejects.toThrow('500')
  })
})

describe('HttpPlannerClient getCard stays single-pass (Epic 040 self-review)', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('the deep-link refetch never asks for phase:"cards" — Detail must get verified conditions', async () => {
    fetchMock.mockReturnValue(
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(FEED) } as Response),
    )
    await client().getCard('ct:a', ANON_SCOPE, TUNING)
    const body = JSON.parse((fetchMock.mock.calls[0][1] as { body: string }).body)
    expect(body.phase).toBeUndefined()
  })
})

describe('HttpPlannerClient trailWater (Epic 041) — the water slice of GET /trail/{id}', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  function ok(json: unknown) {
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(json) } as Response)
  }

  const WIRE_WATER = {
    state: 'sources',
    basis: 'route',
    radius_m: 200.0,
    source: 'OSM',
    sources: [
      {
        water_id: 'water:osm:node/1',
        water_type: 'spring',
        name: 'Furnace Spring',
        lat: 38.5,
        lon: -78.4,
        distance_m: 63.7,
        seasonal: 'yes',
        source: 'OSM',
      },
      {
        water_id: 'water:osm:node/2',
        water_type: 'water_tap',
        name: null,
        lat: 38.51,
        lon: -78.39,
        distance_m: 21.9,
        seasonal: null,
        source: 'OSM',
      },
    ],
  }

  it('GETs /trail/{id} and maps the answered state to the VM (live provenance)', async () => {
    fetchMock.mockReturnValue(ok({ canonical_id: 'ct:osm:x', name: 'X', water_sources: WIRE_WATER }))
    const vm = await client().trailWater('ct:osm:x', ANON_SCOPE)

    const url = (fetchMock.mock.calls[0] as [string, RequestInit])[0]
    expect(url).toContain('/trail/ct%3Aosm%3Ax?')
    expect(url).toContain('viewer_id=anonymous')

    expect(vm).not.toBeNull()
    expect(vm?.state).toBe('sources')
    expect(vm?.basis).toBe('route')
    expect(vm?.radiusM).toBe(200)
    expect(vm?.provenance).toBe('live')
    // null wire optionals collapse to undefined at the boundary (idiomatic VM).
    expect(vm?.sources[1]).toEqual({
      id: 'water:osm:node/2',
      type: 'water_tap',
      name: undefined,
      lat: 38.51,
      lon: -78.39,
      distanceM: 21.9,
      seasonal: undefined,
    })
  })

  it('maps the wire none_nearby to the VM none-nearby (an answered-empty, not silence)', async () => {
    fetchMock.mockReturnValue(
      ok({ canonical_id: 'ct:osm:x', name: 'X', water_sources: { ...WIRE_WATER, state: 'none_nearby', sources: [] } }),
    )
    const vm = await client().trailWater('ct:osm:x', ANON_SCOPE)
    expect(vm?.state).toBe('none-nearby')
    expect(vm?.sources).toEqual([])
  })

  it('maps a null/absent water_sources field to null (CDP-02 not-fetched silence)', async () => {
    fetchMock.mockReturnValue(ok({ canonical_id: 'ct:osm:x', name: 'X', water_sources: null }))
    expect(await client().trailWater('ct:osm:x', ANON_SCOPE)).toBeNull()
    fetchMock.mockReturnValue(ok({ canonical_id: 'ct:osm:x', name: 'X' }))
    expect(await client().trailWater('ct:osm:x', ANON_SCOPE)).toBeNull()
  })

  it('degrades EVERY failure to null silence — 404, 5xx, and a network throw', async () => {
    fetchMock.mockReturnValue(Promise.resolve({ ok: false, status: 404 } as Response))
    expect(await client().trailWater('ct:osm:gone', ANON_SCOPE)).toBeNull()
    fetchMock.mockReturnValue(Promise.resolve({ ok: false, status: 500 } as Response))
    expect(await client().trailWater('ct:osm:x', ANON_SCOPE)).toBeNull()
    fetchMock.mockImplementation(() => Promise.reject(new TypeError('Failed to fetch')))
    expect(await client().trailWater('ct:osm:x', ANON_SCOPE)).toBeNull()
  })

  it('degrades an UNKNOWN wire state to null silence rather than guessing an answer', async () => {
    fetchMock.mockReturnValue(
      ok({ canonical_id: 'ct:osm:x', name: 'X', water_sources: { ...WIRE_WATER, state: 'seasonal_estimate' } }),
    )
    expect(await client().trailWater('ct:osm:x', ANON_SCOPE)).toBeNull()
  })
})
