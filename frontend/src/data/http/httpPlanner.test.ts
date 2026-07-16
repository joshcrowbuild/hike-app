import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { HttpPlannerClient, resetPlanShellCacheForTests } from './httpPlanner'
import { ANON_SCOPE, type ScopeContext, type FeedResponse, type OutcomeResponse } from '../api'
import type { PlanInput } from '../source'
import type { Coords, TuningState } from '../../types'

// The /plan SHELL ETag cache (Epic 052 WP-5) is module-level, in-memory state
// shared across every test in this file (and every `HttpPlannerClient`
// instance) — reset it before each test so one test's cached shell can never
// serve a stale mock response to a later test with the same request shape.
beforeEach(() => resetPlanShellCacheForTests())

const JOSH: ScopeContext = { viewerId: 'josh-sub', grantedIds: [], accessToken: 'jwt-token-abc' }

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

describe('HttpPlannerClient auth headers (Epic 043 managed auth)', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
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

  it('sends the Supabase Bearer token on /plan for a signed-in viewer', async () => {
    fetchMock.mockReturnValue(ok(FEED))
    await client().plan(PLAN_INPUT, JOSH)
    expect(headersOf(fetchMock.mock.calls[0]).Authorization).toBe('Bearer jwt-token-abc')
  })

  it('never sends the retired dev-viewer secret', async () => {
    // The whole VITE_DEV_VIEWER_SECRET path is gone — a signed-in call must carry
    // only the Bearer token, never the old shared secret (S3.2 regression).
    vi.stubEnv('VITE_DEV_VIEWER_SECRET', 'stale-secret')
    fetchMock.mockReturnValue(ok(FEED))
    await client().plan(PLAN_INPUT, JOSH)
    expect(headersOf(fetchMock.mock.calls[0])).not.toHaveProperty('X-Dev-Viewer-Secret')
  })

  it('sends no credentials on /plan for an anonymous viewer', async () => {
    fetchMock.mockReturnValue(ok(FEED))
    await client().plan(PLAN_INPUT, ANON_SCOPE)
    const headers = headersOf(fetchMock.mock.calls[0])
    expect(headers).not.toHaveProperty('Authorization')
    expect(headers).not.toHaveProperty('X-Dev-Viewer-Secret')
  })

  it('sends the Bearer token on /outcome for a signed-in viewer', async () => {
    fetchMock.mockReturnValue(ok(OUTCOME))
    await client().recordOutcome('e1', { overall: 2, skipped: false }, [], JOSH)
    expect(headersOf(fetchMock.mock.calls[0]).Authorization).toBe('Bearer jwt-token-abc')
  })

  it('sends no Authorization on /outcome for an anonymous viewer', async () => {
    fetchMock.mockReturnValue(ok(OUTCOME))
    await client().recordOutcome('e1', { overall: 2, skipped: false }, [], ANON_SCOPE)
    expect(headersOf(fetchMock.mock.calls[0])).not.toHaveProperty('Authorization')
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

  it('carries a live line’s real sources onto the VM, unmodified, and maps the structured body/age fields (Epic 046 S1 AC-1.1)', async () => {
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
            {
              text: 'Sunny 70°F · NWS, 10m ago',
              body: 'Sunny 70°F',
              source: 'NWS api.weather.gov',
              age: '10m ago',
              confidence_level: 'stated',
              sources: ['NWS'],
            },
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
    expect(line.body).toBe('Sunny 70°F')
    expect(line.age).toBe('10m ago')
    expect(line.text).toBe('Sunny 70°F · NWS, 10m ago')
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

  it('maps an unparseable checked_at to no stamp, never the literal "time unknown" (Epic 046 S4 AC-4.2 / D6)', async () => {
    fetchMock.mockReturnValue(
      ok(
        cardWith([
          { kind: 'weather', state: 'present', source: 'NWS', checked_at: 'not-a-date', detail: '' },
        ]),
      ),
    )
    const result = await client().plan(PLAN_INPUT, ANON_SCOPE)
    expect(result.cards[0].conditions).toEqual([
      { kind: 'weather', state: 'present', source: 'NWS', checkedAgo: undefined, detail: undefined },
    ])
  })
})

describe('HttpPlannerClient hazard warning age (Epic 046 S4 AC-4.2 / D6)', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => vi.unstubAllGlobals())

  const ok = (json: unknown) =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(json) } as Response)

  it('maps an unparseable observed_at to no stamp, never the literal "time unknown"', async () => {
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
              observed_at: 'not-a-date',
              kind: 'weather',
            },
          ],
          unavailable: [],
        },
      ],
    }
    fetchMock.mockReturnValue(ok(feed))
    const result = await client().plan(PLAN_INPUT, ANON_SCOPE)
    expect(result.cards[0].warnings[0].observedAgo).toBeUndefined()
    expect(result.cards[0].warnings[0].text).toBe('weather alert: Extreme Heat Warning')
  })
})

describe('HttpPlannerClient getCard by id (Epic 045 — verified card for any trail)', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => vi.unstubAllGlobals())

  const ok = (json: unknown) =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(json) } as Response)

  function urlOf(call: unknown): string {
    return (call as [string, RequestInit])[0]
  }

  it('GETs /trail/{id}/card and maps the returned card (Epic 045 S4)', async () => {
    const feed: FeedResponse = {
      query: '',
      card_count: 1,
      notices: [],
      cards: [
        {
          canonical_id: 'ct:osm:way_138445924',
          name: 'Old Rag Loop',
          distance_mi: 3.7,
          lines: [
            { text: 'Clear skies', body: 'Clear skies', source: 'NWS', age: 'just now', confidence_level: 'stated', sources: ['NWS'] },
          ],
          warnings: [],
          unavailable: [],
        },
      ],
    }
    fetchMock.mockReturnValue(ok(feed))
    const card = await client().getCard('ct:osm:way_138445924', ANON_SCOPE, TUNING)

    // Calls /trail/{id}/card, not /plan
    expect(urlOf(fetchMock.mock.calls[0])).toContain('/trail/ct%3Aosm%3Away_138445924/card')
    // Maps the card correctly through the shared mapFeed logic
    expect(card?.id).toBe('ct:osm:way_138445924')
    expect(card?.name).toBe('Old Rag Loop')
    expect(card?.conditionLines[0]).toMatchObject({
      text: 'Clear skies',
      provenance: 'live',
      sources: ['NWS'],
    })
  })

  it('returns null for a genuine absence (unknown id)', async () => {
    fetchMock.mockReturnValue(ok({ query: '', card_count: 0, notices: [], cards: [] }))
    const card = await client().getCard('ct:osm:way_unknown', ANON_SCOPE, TUNING)
    expect(card).toBeNull()
  })

  it('throws — never a false "not found" — when the request itself fails (R1: stays retryable)', async () => {
    fetchMock.mockReturnValue(Promise.resolve({ ok: false, status: 503 } as Response))
    await expect(
      client().getCard('ct:osm:way_138445924', ANON_SCOPE, TUNING),
    ).rejects.toThrow()
  })

  it('respects tuning for frame context (e.g. origin for drive time)', async () => {
    const feed: FeedResponse = {
      query: '',
      card_count: 1,
      notices: [],
      cards: [
        {
          canonical_id: 'ct:osm:way_123',
          name: 'Test Trail',
          distance_mi: null,
          lines: [],
          warnings: [],
          unavailable: [],
        },
      ],
    }
    fetchMock.mockReturnValue(ok(feed))
    const tuning: TuningState = { ...TUNING, origin: 'nagsHead' }
    await client().getCard('ct:osm:way_123', ANON_SCOPE, tuning)

    // The call is to /trail/{id}/card, which is frame-agnostic (no lat/lon sent).
    // But the response mapping preserves enrichment (drive minutes come from elsewhere).
    const url = urlOf(fetchMock.mock.calls[0])
    expect(url).toContain('/trail/ct%3Aosm%3Away_123/card')
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
  // models a genuinely slow request the 60s safety-net budget has to wait out
  // (a just-deployed instance restarting, or a real upstream outage), not a
  // routine free-tier wake — Render is a paid Starter with no idle spin-down.
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
            lines: [
              { text: 'Clear skies', body: 'Clear skies', source: 'nws', age: 'just now', confidence_level: 'stated', sources: ['NWS'] },
            ],
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

describe('HttpPlannerClient /plan shell ETag cache (Epic 052 WP-5 — cheap background revalidate)', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  function okWithEtag(json: unknown, etag: string) {
    return Promise.resolve({
      ok: true,
      status: 200,
      headers: new Headers({ etag }),
      json: () => Promise.resolve(json),
    } as Response)
  }
  function notModified(etag: string) {
    return Promise.resolve({
      ok: false,
      status: 304,
      headers: new Headers({ etag }),
      // Proves the client never calls .json() on a 304 — there's no body.
      json: () => Promise.reject(new Error('must not parse a 304 body')),
    } as unknown as Response)
  }
  function headersOf(call: unknown): Record<string, string> {
    return (call as [string, RequestInit])[1].headers as Record<string, string>
  }

  it('sends no If-None-Match on the first request for a given frame', async () => {
    fetchMock.mockReturnValue(okWithEtag(FEED, '"v1"'))
    await client().plan(PLAN_INPUT, ANON_SCOPE)
    expect(headersOf(fetchMock.mock.calls[0])).not.toHaveProperty('If-None-Match')
  })

  it('sends If-None-Match with the previous ETag on a repeat request for the SAME frame', async () => {
    fetchMock.mockReturnValue(okWithEtag(FEED, '"v1"'))
    const c = client()
    await c.plan(PLAN_INPUT, ANON_SCOPE)
    await c.plan(PLAN_INPUT, ANON_SCOPE)
    expect(headersOf(fetchMock.mock.calls[1])['If-None-Match']).toBe('"v1"')
  })

  it('a DIFFERENT frame (retuned party) never sends the other frame\'s ETag', async () => {
    fetchMock.mockReturnValue(okWithEtag(FEED, '"v1"'))
    const c = client()
    await c.plan(PLAN_INPUT, ANON_SCOPE)
    const retuned: PlanInput = { tuning: { ...TUNING, party: 'friends' } }
    await c.plan(retuned, ANON_SCOPE)
    expect(headersOf(fetchMock.mock.calls[1])).not.toHaveProperty('If-None-Match')
  })

  it('a 304 reuses the previously cached shell body — never parses an empty one', async () => {
    const cardFeed: FeedResponse = {
      ...FEED,
      cards: [{ canonical_id: 'ct:a', name: 'A', distance_mi: 1, lines: [], warnings: [], unavailable: [] }],
    }
    fetchMock.mockReturnValueOnce(okWithEtag(cardFeed, '"v1"'))
    fetchMock.mockReturnValueOnce(notModified('"v1"'))
    const c = client()
    const first = await c.plan(PLAN_INPUT, ANON_SCOPE)
    const second = await c.plan(PLAN_INPUT, ANON_SCOPE)
    expect(second.cards[0]?.id).toBe('ct:a')
    expect(second).toEqual(first)
  })

  it('a fresh 200 with a NEW ETag replaces the cached one (the shell genuinely changed)', async () => {
    const feedV2: FeedResponse = {
      ...FEED,
      cards: [{ canonical_id: 'ct:b', name: 'B', distance_mi: 2, lines: [], warnings: [], unavailable: [] }],
    }
    fetchMock.mockReturnValueOnce(okWithEtag(FEED, '"v1"'))
    fetchMock.mockReturnValueOnce(okWithEtag(feedV2, '"v2"'))
    const third = notModified('"v2"')
    fetchMock.mockReturnValueOnce(third)
    const c = client()
    await c.plan(PLAN_INPUT, ANON_SCOPE)
    const second = await c.plan(PLAN_INPUT, ANON_SCOPE)
    expect(second.cards[0]?.id).toBe('ct:b')
    // The THIRD call must send the NEW etag (v2), not the stale v1.
    await c.plan(PLAN_INPUT, ANON_SCOPE)
    expect(headersOf(fetchMock.mock.calls[2])['If-None-Match']).toBe('"v2"')
  })

  it('a response with no ETag header (kill switch / older backend) is simply never cached', async () => {
    fetchMock.mockReturnValue(
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(FEED) } as Response),
    )
    const c = client()
    await c.plan(PLAN_INPUT, ANON_SCOPE)
    await c.plan(PLAN_INPUT, ANON_SCOPE)
    expect(headersOf(fetchMock.mock.calls[1])).not.toHaveProperty('If-None-Match')
  })

  it('a minimal test double with no headers object at all degrades safely (no throw, no cache)', async () => {
    fetchMock.mockReturnValue(
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(FEED) } as Response),
    )
    await expect(client().plan(PLAN_INPUT, ANON_SCOPE)).resolves.toBeDefined()
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

  it('resolves via GET /trail/{id}/card (verified conditions), never a phased /plan frame', async () => {
    fetchMock.mockReturnValue(
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(FEED) } as Response),
    )
    await client().getCard('ct:a', ANON_SCOPE, TUNING)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    // getCard now hits the by-id card endpoint (which always returns conditions_
    // complete), not a phased /plan — so Detail can never resolve a phase-1 frame.
    // A bodyless GET means there is no `phase` to send at all (the old invariant,
    // now held by construction).
    expect(url).toContain('/trail/ct%3Aa/card')
    expect(url).not.toContain('/plan')
    expect(init?.body).toBeUndefined()
  })
})

describe('HttpPlannerClient search (Epic 038/B001 build lane — the Home Omnibox search line)', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => vi.unstubAllGlobals())

  const ok = (json: unknown) =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(json) } as Response)

  function bodyOf(call: unknown): Record<string, unknown> {
    return JSON.parse(((call as [string, RequestInit])[1] as { body: string }).body)
  }
  function urlOf(call: unknown): string {
    return (call as [string, RequestInit])[0]
  }

  it('POSTs /search with the query and default k, and maps the response through the shared mapFeed', async () => {
    const feed: FeedResponse = {
      query: 'old rag',
      card_count: 1,
      notices: [],
      cards: [
        {
          canonical_id: 'old-rag',
          name: 'Old Rag Loop',
          distance_mi: 3.7,
          lines: [
            {
              text: 'Sunny 70°F · NWS, 10m ago',
              body: 'Sunny 70°F',
              source: 'NWS',
              age: '10m ago',
              confidence_level: 'stated',
              sources: ['NWS'],
            },
          ],
          warnings: [],
          unavailable: [],
        },
      ],
    }
    fetchMock.mockReturnValue(ok(feed))
    const result = await client().search('old rag', ANON_SCOPE)

    expect(urlOf(fetchMock.mock.calls[0])).toBe('http://api/search')
    const body = bodyOf(fetchMock.mock.calls[0])
    expect(body).toEqual({ query: 'old rag', k: 10 })
    expect(result.cards).toHaveLength(1)
    expect(result.cards[0].id).toBe('old-rag')
    // Same mapping truth as /plan: provenance + sources carry through unchanged.
    expect(result.cards[0].conditionLines[0].provenance).toBe('live')
    expect(result.cards[0].conditionLines[0].sources).toEqual(['NWS'])
  })

  it('passes a caller-supplied k straight through', async () => {
    fetchMock.mockReturnValue(ok(FEED))
    await client().search('rivanna', ANON_SCOPE, 5)
    expect(bodyOf(fetchMock.mock.calls[0])).toEqual({ query: 'rivanna', k: 5 })
  })

  it('sends the Bearer token for a signed-in viewer, same as /plan', async () => {
    fetchMock.mockReturnValue(ok(FEED))
    await client().search('old rag', { viewerId: 'josh-sub', grantedIds: [], accessToken: 'jwt-xyz' })
    const init = (fetchMock.mock.calls[0] as [string, RequestInit])[1]
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer jwt-xyz')
  })

  it('returns an honest empty FeedVM (no cards) rather than an error when the backend returns zero matches', async () => {
    fetchMock.mockReturnValue(ok({ query: 'zzznotrail', card_count: 0, notices: [], cards: [] }))
    const result = await client().search('zzznotrail', ANON_SCOPE)
    expect(result.cards).toEqual([])
    expect(result.error).toBeUndefined()
  })

  it('classifies a non-OK response the same way /plan does (server/auth), never throwing', async () => {
    fetchMock.mockReturnValue(Promise.resolve({ ok: false, status: 500 } as Response))
    const result = await client().search('old rag', ANON_SCOPE)
    expect(result.cards).toEqual([])
    expect(result.error?.kind).toBe('server')
  })

  it('classifies a network throw as offline, never propagating the raw exception', async () => {
    fetchMock.mockImplementation(() => Promise.reject(new TypeError('Failed to fetch')))
    const result = await client().search('old rag', ANON_SCOPE)
    expect(result.error?.kind).toBe('offline')
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
