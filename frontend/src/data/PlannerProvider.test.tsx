import { act, render, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'

import { PlannerProvider, useCard, useFeed, useSearch, useTrailWater } from './PlannerProvider'
import type { FeedState } from './PlannerProvider'
import { ANON_SCOPE } from './api'
import type { ScopeContext } from './api'
import { feedKey, readFeedCache, resetFeedCacheForTests, writeFeedCache } from './feedCache'
import { COLDSTART_MS, REASSURE_MS } from './loadingStages'
import type { PlanInput, PlannerClient } from './source'
import type { CardVM, FeedVM, TrailWaterVM } from './vm'
import type { TuningState } from '../types'

// A successful anonymous resolve now write-throughs to the feed cache
// (Epic 039 S3) — clear it after every test so one test's write can never
// leak into another's (e.g. a later test's hydrateStale seeing a stale hit
// under the same PLAN_INPUT/ANON_SCOPE key).
afterEach(() => resetFeedCacheForTests())

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

const READY_FEED: FeedVM = {
  query: '',
  cards: [{ id: 'a', name: 'A', distanceMi: 1, conditionLines: [], warnings: [] }],
  notices: [],
  setAside: [],
  heldBack: [],
  readiness: { on: false, state: 'off' },
  dataSource: 'live',
}

/** A client whose plan() resolves only when the test fires `resolve`. */
function deferredClient(): {
  client: PlannerClient
  resolve: (feed: FeedVM) => void
  pending: Promise<FeedVM>
} {
  let resolve!: (feed: FeedVM) => void
  const pending = new Promise<FeedVM>((r) => {
    resolve = r
  })
  const client = {
    plan: () => pending,
  } as unknown as PlannerClient
  return { client, resolve, pending }
}

function wrapperWith(client: PlannerClient) {
  return ({ children }: { children: ReactNode }) => (
    <PlannerProvider scope={ANON_SCOPE} client={client}>
      {children}
    </PlannerProvider>
  )
}

describe('useFeed loading-stage progress (D4 — never a frozen line)', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('steps loadingStage from initial → reassure → coldstart at the REASSURE_MS/COLDSTART_MS marks', () => {
    const { client } = deferredClient()
    const { result } = renderHook(() => useFeed(PLAN_INPUT), { wrapper: wrapperWith(client) })

    expect(result.current.status).toBe('loading')
    expect(result.current.loadingStage).toBe('initial')

    act(() => {
      vi.advanceTimersByTime(REASSURE_MS - 1)
    })
    expect(result.current.loadingStage).toBe('initial')

    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(result.current.loadingStage).toBe('reassure')

    act(() => {
      vi.advanceTimersByTime(COLDSTART_MS - REASSURE_MS - 1)
    })
    expect(result.current.loadingStage).toBe('reassure')

    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(result.current.loadingStage).toBe('coldstart')
  })

  it('resets loadingStage to initial once the feed resolves', async () => {
    const { client, resolve, pending } = deferredClient()
    const { result } = renderHook(() => useFeed(PLAN_INPUT), { wrapper: wrapperWith(client) })

    act(() => {
      vi.advanceTimersByTime(25_000)
    })
    expect(result.current.loadingStage).toBe('coldstart')

    // Resolve and drain the plan() promise chain (.then sets status, .finally
    // resets loadingStage) inside act — no waitFor, which would poll on
    // stalled fake timers.
    await act(async () => {
      resolve(READY_FEED)
      await pending
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(result.current.status).toBe('ready')
    expect(result.current.loadingStage).toBe('initial')
  })

  it('resets loadingStage when the input re-keys mid cold-start (retune while waking)', () => {
    const { client } = deferredClient()
    const { result, rerender } = renderHook((props: { input: PlanInput }) => useFeed(props.input), {
      wrapper: wrapperWith(client),
      initialProps: { input: PLAN_INPUT },
    })

    act(() => {
      vi.advanceTimersByTime(25_000)
    })
    expect(result.current.loadingStage).toBe('coldstart')

    // Retuning changes the effect key — loadingStage resets and re-arms its
    // timers rather than leaving "Waking the server…" stuck under the new frame.
    const retuned: PlanInput = { tuning: { ...TUNING, party: 'friends' } }
    act(() => {
      rerender({ input: retuned })
    })
    expect(result.current.loadingStage).toBe('initial')

    act(() => {
      vi.advanceTimersByTime(25_000)
    })
    expect(result.current.loadingStage).toBe('coldstart')
  })
})

function feedWithCard(id: string): FeedVM {
  return {
    query: '',
    cards: [{ id, name: id, distanceMi: 1, conditionLines: [], warnings: [] }],
    notices: [],
    setAside: [],
    heldBack: [],
    readiness: { on: false, state: 'off' },
    dataSource: 'live',
  }
}

/** Mounts useFeed + useCard side by side, sharing the one PlannerProvider
 *  instance, so a resolved feed is visible to useCard the way Home's feed is
 *  visible to Detail in the real app (both live under the same provider). */
function useHarness(input: PlanInput, cardId: string | null) {
  const feed = useFeed(input)
  const card = useCard(cardId)
  return { feed, card }
}

/**
 * Epic 056 S1: a probe that renders nothing, just reports each `useFeed`
 * resolution via a callback — used with `render`/`rerender` (NOT
 * `renderHook`) so the probe itself can be truly unmounted and remounted
 * while the surrounding `<PlannerProvider>` stays mounted, exactly like Home
 * unmounting when Detail opens and remounting when the user goes back.
 * `renderHook`'s own wrapper persists for the ENTIRE hook lifetime (it never
 * unmounts on a plain `rerender`), so it can't simulate this — only a real
 * conditional child under a stable provider can.
 */
function FeedProbe({ input, onState }: { input: PlanInput; onState: (s: FeedState) => void }) {
  const state = useFeed(input)
  onState(state)
  return null
}

async function flushMicrotasks() {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
    await Promise.resolve()
  })
}

describe('useFeed error state (NNG: calm, actionable, never the raw exception)', () => {
  it('surfaces a fixed calm message when plan() rejects, not the raw error string', async () => {
    const client = {
      plan: vi.fn().mockRejectedValue(new TypeError('Failed to fetch')),
    } as unknown as PlannerClient
    const { result } = renderHook(() => useFeed(PLAN_INPUT), { wrapper: wrapperWith(client) })

    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(result.current.status).toBe('error')
    expect(result.current.error?.message).toBe('Couldn’t reach the planner. Try again.')
    expect(result.current.error?.message).not.toContain('TypeError')
  })
})

describe('useCard resolves the tapped card from the in-memory feed (OBX "not in your current set" fix)', () => {
  it('finds a card already in the just-resolved feed with no network call', async () => {
    const feed = feedWithCard('stony-man')
    const getCard = vi.fn().mockRejectedValue(new Error('getCard should not be called'))
    const client = { plan: vi.fn().mockResolvedValue(feed), getCard } as unknown as PlannerClient

    const { result, rerender } = renderHook(
      (props: { cardId: string | null }) => useHarness(PLAN_INPUT, props.cardId),
      { wrapper: wrapperWith(client), initialProps: { cardId: null as string | null } },
    )

    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(result.current.feed.status).toBe('ready')

    rerender({ cardId: 'stony-man' })

    expect(result.current.card.status).toBe('ready')
    expect(result.current.card.card?.id).toBe('stony-man')
    expect(getCard).not.toHaveBeenCalled()
  })

  it('resolves a card under a non-default origin (Nags Head) instantly, matching the default-origin path', async () => {
    const nagsHeadTuning: TuningState = { ...TUNING, origin: 'nagsHead' }
    const feed = feedWithCard('jockeys-ridge')
    const getCard = vi.fn().mockRejectedValue(new Error('getCard should not be called'))
    const client = { plan: vi.fn().mockResolvedValue(feed), getCard } as unknown as PlannerClient

    const { result, rerender } = renderHook(
      (props: { cardId: string | null }) => useHarness({ tuning: nagsHeadTuning }, props.cardId),
      { wrapper: wrapperWith(client), initialProps: { cardId: null as string | null } },
    )

    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    rerender({ cardId: 'jockeys-ridge' })

    expect(result.current.card.status).toBe('ready')
    expect(result.current.card.card?.id).toBe('jockeys-ridge')
    expect(getCard).not.toHaveBeenCalled()
  })

  it('falls back to a refetch with the CURRENT tuning — never a rebuilt default — for a true deep link', async () => {
    const friendsBigDay: TuningState = { ...TUNING, origin: 'nagsHead', effort: 'bigDay', party: 'friends' }
    // The resolved feed does not contain 'hidden-trail' (e.g. a set-aside "show
    // anyway" tap, or a cold link to an id outside the visible set).
    const feed = feedWithCard('jockeys-ridge')
    const hiddenCard: CardVM = {
      id: 'hidden-trail',
      name: 'Hidden Trail',
      distanceMi: 2,
      conditionLines: [],
      warnings: [],
    }
    const getCard = vi.fn().mockResolvedValue(hiddenCard)
    const client = { plan: vi.fn().mockResolvedValue(feed), getCard } as unknown as PlannerClient

    const { result, rerender } = renderHook(
      (props: { cardId: string | null }) => useHarness({ tuning: friendsBigDay }, props.cardId),
      { wrapper: wrapperWith(client), initialProps: { cardId: null as string | null } },
    )

    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    rerender({ cardId: 'hidden-trail' })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(getCard).toHaveBeenCalledWith('hidden-trail', ANON_SCOPE, friendsBigDay)
    expect(result.current.card.status).toBe('ready')
    expect(result.current.card.card?.id).toBe('hidden-trail')
  })
})

describe('Epic 039 S3 / Epic 052 WP-5 — stale-while-revalidate (any viewer)', () => {
  function seedCache(input: PlanInput, feed: FeedVM, scope: ScopeContext = ANON_SCOPE) {
    writeFeedCache(feedKey(input, scope), feed, scope.viewerId)
  }

  it('AC-3.1: a matching stale cache paints on the FIRST committed render — ready/stale/revalidating, never loading', () => {
    seedCache(PLAN_INPUT, feedWithCard('compton-peak'))
    const { client } = deferredClient()
    const statuses: string[] = []
    const { result } = renderHook(
      () => {
        const state = useFeed(PLAN_INPUT)
        statuses.push(state.status)
        return state
      },
      { wrapper: wrapperWith(client) },
    )

    expect(result.current.status).toBe('ready')
    expect(result.current.stale).toBe(true)
    expect(result.current.revalidating).toBe(true)
    expect(result.current.feed?.cards[0].id).toBe('compton-peak')
    expect(statuses).not.toContain('loading')
  })

  it('AC-3.3: the stale paint is honest — no warnings/lines, every card stale-degraded, feed-level disclosures emptied', () => {
    const richFeed: FeedVM = {
      query: '',
      cards: [
        {
          id: 'compton-peak',
          name: 'Compton Peak',
          distanceMi: 2.1,
          conditionLines: [{ text: 'Clear', source: 'NWS', confidence: 'stated', provenance: 'live' }],
          warnings: [
            {
              text: 'flash flood warning',
              source: 'NWS',
              observedAgo: '2h ago',
              kind: 'weather',
              provenance: 'live',
            },
          ],
        },
      ],
      notices: ['Drive times unavailable this run'],
      setAside: [],
      heldBack: [],
      readiness: { on: true, state: 'applied', rationale: 'because' },
      dataSource: 'live',
    }
    seedCache(PLAN_INPUT, richFeed)
    const { client } = deferredClient()
    const { result } = renderHook(() => useFeed(PLAN_INPUT), { wrapper: wrapperWith(client) })

    const card = result.current.feed?.cards[0]
    expect(card?.warnings).toEqual([])
    expect(card?.conditionLines).toEqual([])
    expect(card?.conditionSilence?.state).toBe('stale-degraded')
    expect(result.current.feed?.notices).toEqual([])
    expect(result.current.feed?.readiness).toEqual({ on: false, state: 'off' })
  })

  it('AC-3.2: revalidates behind the stale paint and writes the fresh feed through on a successful resolve', async () => {
    seedCache(PLAN_INPUT, feedWithCard('compton-peak'))
    const { client, resolve, pending } = deferredClient()
    const { result } = renderHook(() => useFeed(PLAN_INPUT), { wrapper: wrapperWith(client) })
    expect(result.current.stale).toBe(true)

    const freshFeed = feedWithCard('old-rag')
    await act(async () => {
      resolve(freshFeed)
      await pending
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(result.current.status).toBe('ready')
    expect(result.current.stale).toBe(false)
    expect(result.current.revalidating).toBe(false)
    expect(result.current.feed?.cards[0].id).toBe('old-rag')
    expect(readFeedCache(feedKey(PLAN_INPUT, ANON_SCOPE), Date.now(), ANON_SCOPE.viewerId)?.feed.cards[0].id).toBe(
      'old-rag',
    )
  })

  it('AC-3.5b (Epic 052 WP-5): a signed-in viewer DOES get a stale paint + write-through, in its OWN namespaced slot', async () => {
    // Seed under the anonymous key — a leak into josh's read would show up as a hit.
    seedCache(PLAN_INPUT, feedWithCard('compton-peak'))
    const josh: ScopeContext = { viewerId: 'josh', grantedIds: [] }
    const { client, resolve, pending } = deferredClient()
    function wrapperFor(scope: ScopeContext, c: PlannerClient) {
      return ({ children }: { children: ReactNode }) => (
        <PlannerProvider scope={scope} client={c}>
          {children}
        </PlannerProvider>
      )
    }
    const { result } = renderHook(() => useFeed(PLAN_INPUT), { wrapper: wrapperFor(josh, client) })

    // No cross-viewer leak: josh's slot is empty, so josh still starts loading
    // (never repaints from anonymous's cached feed).
    expect(result.current.status).toBe('loading')
    expect(result.current.stale).toBe(false)

    await act(async () => {
      resolve(feedWithCard('old-rag'))
      await pending
      await Promise.resolve()
      await Promise.resolve()
    })

    // The resolve write-throughs to josh's OWN slot now (WP-5 lifts the old
    // anonymous-only gate) — the anonymous slot is untouched.
    expect(readFeedCache(feedKey(PLAN_INPUT, josh), Date.now(), 'josh')?.feed.cards[0].id).toBe('old-rag')
    expect(readFeedCache(feedKey(PLAN_INPUT, ANON_SCOPE), Date.now(), 'anonymous')?.feed.cards[0].id).toBe(
      'compton-peak',
    )
  })

  it('AC-3.6: an empty or errored resolve is never persisted', async () => {
    const emptyFeed: FeedVM = { ...feedWithCard('x'), cards: [] }
    const client1 = { plan: vi.fn().mockResolvedValue(emptyFeed) } as unknown as PlannerClient
    const { result: r1 } = renderHook(() => useFeed(PLAN_INPUT), { wrapper: wrapperWith(client1) })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(r1.current.status).toBe('empty')
    expect(readFeedCache(feedKey(PLAN_INPUT, ANON_SCOPE), Date.now(), ANON_SCOPE.viewerId)).toBeNull()

    const erroredFeed: FeedVM = { ...feedWithCard('y'), error: { kind: 'partial', message: 'partial' } }
    const client2 = { plan: vi.fn().mockResolvedValue(erroredFeed) } as unknown as PlannerClient
    const { result: r2 } = renderHook(() => useFeed(PLAN_INPUT), { wrapper: wrapperWith(client2) })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(r2.current.status).toBe('error')
    expect(readFeedCache(feedKey(PLAN_INPUT, ANON_SCOPE), Date.now(), ANON_SCOPE.viewerId)).toBeNull()
  })

  it('AC-3.7: a revalidation rejection keeps the stale feed usable; a cold rejection (no seed) still errors', async () => {
    seedCache(PLAN_INPUT, feedWithCard('compton-peak'))
    const client = { plan: vi.fn().mockRejectedValue(new Error('offline')) } as unknown as PlannerClient
    const { result } = renderHook(() => useFeed(PLAN_INPUT), { wrapper: wrapperWith(client) })
    expect(result.current.stale).toBe(true)

    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(result.current.status).toBe('ready')
    expect(result.current.stale).toBe(true)
    expect(result.current.revalidating).toBe(false)
    expect(result.current.revalidateError).toBeDefined()
    expect(result.current.feed?.cards[0].id).toBe('compton-peak')

    // A cold rejection with no stale seed still yields the full error state.
    resetFeedCacheForTests()
    const coldClient = { plan: vi.fn().mockRejectedValue(new Error('offline')) } as unknown as PlannerClient
    const { result: coldResult } = renderHook(() => useFeed(PLAN_INPUT), { wrapper: wrapperWith(coldClient) })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(coldResult.current.status).toBe('error')
    expect(coldResult.current.stale).toBe(false)
  })
})

describe('Epic 040 S3 — two-phase flow (cards first, conditions patched behind)', () => {
  const NOT_FETCHED = [
    { kind: 'weather', state: 'not-fetched' as const },
    { kind: 'air', state: 'not-fetched' as const },
  ]

  function phase1Feed(ids: string[]): FeedVM {
    return {
      query: '',
      cards: ids.map((id) => ({
        id,
        name: id,
        distanceMi: 1,
        conditionLines: [],
        conditions: [...NOT_FETCHED],
        warnings: [],
      })),
      notices: [],
      setAside: [],
      heldBack: [],
      readiness: { on: false, state: 'off' },
      dataSource: 'live',
      conditionsPending: true,
    }
  }

  const PATCH = {
    patches: [
      {
        id: 'old-rag',
        conditionLines: [
          { text: 'Clear skies', source: 'nws', confidence: 'stated' as const, provenance: 'live' as const },
        ],
        conditions: [{ kind: 'weather', state: 'present' as const, source: 'NWS', checkedAgo: 'just now' }],
        warnings: [],
      },
    ],
    heldBack: [],
  }

  async function flush() {
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
    })
  }

  it('AC-3.1/3.3: phase 1 commits ready cards with revalidating up, then the patch fills in place', async () => {
    const planConditions = vi.fn().mockResolvedValue(PATCH)
    const client = {
      plan: vi.fn().mockResolvedValue(phase1Feed(['old-rag'])),
      planConditions,
    } as unknown as PlannerClient
    const { result } = renderHook(() => useFeed(PLAN_INPUT), { wrapper: wrapperWith(client) })

    await flush()

    // Composed end-state: patch applied in place, pending cleared.
    expect(result.current.status).toBe('ready')
    expect(result.current.revalidating).toBe(false)
    expect(result.current.feed?.cards[0].conditionLines[0].text).toBe('Clear skies')
    expect(result.current.feed?.cards[0].conditions?.[0].state).toBe('present')
    expect(result.current.feed?.conditionsPending).toBeUndefined()
    // Phase 2 was asked for exactly the phase-1 ids.
    expect(planConditions).toHaveBeenCalledTimes(1)
    expect(planConditions.mock.calls[0][2]).toEqual(['old-rag'])
  })

  it('AC-3.2: a complete feed (warm key / kill switch / old backend) never fires the conditions call', async () => {
    const planConditions = vi.fn()
    const client = {
      plan: vi.fn().mockResolvedValue(feedWithCard('old-rag')), // no conditionsPending
      planConditions,
    } as unknown as PlannerClient
    const { result } = renderHook(() => useFeed(PLAN_INPUT), { wrapper: wrapperWith(client) })

    await flush()

    expect(result.current.status).toBe('ready')
    expect(result.current.revalidating).toBe(false)
    expect(planConditions).not.toHaveBeenCalled()
  })

  it('a client without planConditions (the mock) treats a pending feed as complete rather than hanging', async () => {
    const client = { plan: vi.fn().mockResolvedValue(phase1Feed(['old-rag'])) } as unknown as PlannerClient
    const { result } = renderHook(() => useFeed(PLAN_INPUT), { wrapper: wrapperWith(client) })

    await flush()

    expect(result.current.status).toBe('ready')
    expect(result.current.revalidating).toBe(false)
  })

  it('AC-3.4: a hard-guardrail removal patches out the card and discloses it — order untouched', async () => {
    const patch = {
      patches: [],
      heldBack: [
        { id: 'smoky', name: 'smoky', reasons: [{ text: 'air quality hazardous (AirNow)', source: 'AirNow', kind: 'air' }] },
      ],
    }
    const client = {
      plan: vi.fn().mockResolvedValue(phase1Feed(['old-rag', 'smoky', 'stony-man'])),
      planConditions: vi.fn().mockResolvedValue(patch),
    } as unknown as PlannerClient
    const { result } = renderHook(() => useFeed(PLAN_INPUT), { wrapper: wrapperWith(client) })

    await flush()

    expect(result.current.feed?.cards.map((c) => c.id)).toEqual(['old-rag', 'stony-man'])
    expect(result.current.feed?.heldBack.map((h) => h.id)).toEqual(['smoky'])
  })

  it('AC-3.4: a patch failure keeps the phase-1 cards usable and reload() re-posts the conditions call ONLY', async () => {
    const plan = vi.fn().mockResolvedValue(phase1Feed(['old-rag']))
    const planConditions = vi
      .fn()
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValueOnce(PATCH)
    const client = { plan, planConditions } as unknown as PlannerClient
    const { result } = renderHook(() => useFeed(PLAN_INPUT), { wrapper: wrapperWith(client) })

    await flush()

    // Failure: cards stay (never a blank), the gap is disclosed, silence stays honest.
    expect(result.current.status).toBe('ready')
    expect(result.current.feed?.cards[0].conditions?.[0].state).toBe('not-fetched')
    expect(result.current.revalidateError?.message).toContain('verify current conditions')
    expect(plan).toHaveBeenCalledTimes(1)

    await act(async () => {
      result.current.reload()
    })
    await flush()

    // Retry re-posted phase 2 only — the plan call count did NOT grow.
    expect(plan).toHaveBeenCalledTimes(1)
    expect(planConditions).toHaveBeenCalledTimes(2)
    expect(result.current.revalidateError).toBeUndefined()
    expect(result.current.feed?.cards[0].conditions?.[0].state).toBe('present')
  })

  it('AC-3.5: the anonymous stale-paint cache holds ONLY the composed feed, never the phase-1 frame', async () => {
    let resolvePatch!: (p: unknown) => void
    const patchPending = new Promise((r) => {
      resolvePatch = r
    })
    const client = {
      plan: vi.fn().mockResolvedValue(phase1Feed(['old-rag'])),
      planConditions: vi.fn().mockReturnValue(patchPending),
    } as unknown as PlannerClient
    const { result } = renderHook(() => useFeed(PLAN_INPUT), { wrapper: wrapperWith(client) })

    await flush()

    // Phase 1 is on screen but the write-gate held: nothing cached yet.
    expect(result.current.revalidating).toBe(true)
    expect(readFeedCache(feedKey(PLAN_INPUT, ANON_SCOPE), Date.now(), ANON_SCOPE.viewerId)).toBeNull()

    await act(async () => {
      resolvePatch(PATCH)
      await patchPending
    })

    const hit = readFeedCache(feedKey(PLAN_INPUT, ANON_SCOPE), Date.now(), ANON_SCOPE.viewerId)
    expect(hit).not.toBeNull()
    expect(hit?.feed.conditionsPending).toBeUndefined()
    expect(hit?.feed.cards[0].conditions?.[0].state).toBe('present')
  })
})

describe('useSearch — the Home Omnibox trail-name search hook (Epic 038/B001)', () => {
  it('starts idle and never calls the client until search() is invoked', () => {
    const search = vi.fn()
    const client = { plan: vi.fn(), search } as unknown as PlannerClient
    const { result } = renderHook(() => useSearch(), { wrapper: wrapperWith(client) })

    expect(result.current.status).toBe('idle')
    expect(search).not.toHaveBeenCalled()
  })

  it('goes loading then ready with cards on a successful resolve, keyed to the searched query', async () => {
    const feed = feedWithCard('old-rag')
    const search = vi.fn().mockResolvedValue(feed)
    const client = { plan: vi.fn(), search } as unknown as PlannerClient
    const { result } = renderHook(() => useSearch(), { wrapper: wrapperWith(client) })

    act(() => {
      result.current.search('old rag')
    })
    expect(result.current.status).toBe('loading')
    expect(result.current.query).toBe('old rag')

    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(search).toHaveBeenCalledWith('old rag', ANON_SCOPE)
    expect(result.current.status).toBe('ready')
    expect(result.current.feed?.cards[0].id).toBe('old-rag')
  })

  it('resolves to the honest empty status on a zero-card match — never fabricated', async () => {
    const empty: FeedVM = { ...feedWithCard('x'), cards: [] }
    const search = vi.fn().mockResolvedValue(empty)
    const client = { plan: vi.fn(), search } as unknown as PlannerClient
    const { result } = renderHook(() => useSearch(), { wrapper: wrapperWith(client) })

    act(() => {
      result.current.search('no such trail')
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(result.current.status).toBe('empty')
    expect(result.current.query).toBe('no such trail')
  })

  it('surfaces a calm error state on a resolved FeedVM.error or a rejection, mirroring useFeed', async () => {
    const errored: FeedVM = { ...feedWithCard('x'), cards: [], error: { kind: 'offline', message: 'offline msg' } }
    const search = vi.fn().mockResolvedValue(errored)
    const client = { plan: vi.fn(), search } as unknown as PlannerClient
    const { result } = renderHook(() => useSearch(), { wrapper: wrapperWith(client) })

    act(() => {
      result.current.search('old rag')
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(result.current.status).toBe('error')
    expect(result.current.error?.message).toBe('offline msg')

    const rejecting = { plan: vi.fn(), search: vi.fn().mockRejectedValue(new Error('boom')) } as unknown as PlannerClient
    const { result: r2 } = renderHook(() => useSearch(), { wrapper: wrapperWith(rejecting) })
    act(() => {
      r2.current.search('old rag')
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(r2.current.status).toBe('error')
    expect(r2.current.error?.message).not.toContain('boom') // never the raw exception (NNG)
  })

  it('degrades to a calm error when the injected client has no search seam at all', async () => {
    const client = { plan: vi.fn() } as unknown as PlannerClient // predates search — no `search` key
    const { result } = renderHook(() => useSearch(), { wrapper: wrapperWith(client) })

    act(() => {
      result.current.search('old rag')
    })
    expect(result.current.status).toBe('error')
    expect(result.current.error?.message).toBeTruthy()
  })

  it('a blank/whitespace-only query resolves straight to idle without calling the client', () => {
    const search = vi.fn()
    const client = { plan: vi.fn(), search } as unknown as PlannerClient
    const { result } = renderHook(() => useSearch(), { wrapper: wrapperWith(client) })

    act(() => {
      result.current.search('   ')
    })
    expect(result.current.status).toBe('idle')
    expect(search).not.toHaveBeenCalled()
  })

  it('clear() returns to idle and drops any in-flight result', async () => {
    let resolveSearch!: (feed: FeedVM) => void
    const pending = new Promise<FeedVM>((r) => {
      resolveSearch = r
    })
    const search = vi.fn().mockReturnValue(pending)
    const client = { plan: vi.fn(), search } as unknown as PlannerClient
    const { result } = renderHook(() => useSearch(), { wrapper: wrapperWith(client) })

    act(() => {
      result.current.search('old rag')
    })
    expect(result.current.status).toBe('loading')

    act(() => {
      result.current.clear()
    })
    expect(result.current.status).toBe('idle')

    // The stale in-flight response landing after clear() must not resurrect the search.
    await act(async () => {
      resolveSearch(feedWithCard('old-rag'))
      await pending
      await Promise.resolve()
    })
    expect(result.current.status).toBe('idle')
  })

  it('a stale in-flight search response never overwrites a newer submitted query', async () => {
    let resolveFirst!: (feed: FeedVM) => void
    const firstPending = new Promise<FeedVM>((r) => {
      resolveFirst = r
    })
    const search = vi
      .fn()
      .mockReturnValueOnce(firstPending)
      .mockResolvedValueOnce(feedWithCard('new-query-trail'))
    const client = { plan: vi.fn(), search } as unknown as PlannerClient
    const { result } = renderHook(() => useSearch(), { wrapper: wrapperWith(client) })

    act(() => {
      result.current.search('first')
    })
    act(() => {
      result.current.search('second')
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(result.current.query).toBe('second')
    expect(result.current.feed?.cards[0].id).toBe('new-query-trail')

    // The first (now-stale) request resolving afterwards must not clobber "second"'s result.
    await act(async () => {
      resolveFirst(feedWithCard('first-query-trail'))
      await firstPending
      await Promise.resolve()
    })
    expect(result.current.query).toBe('second')
    expect(result.current.feed?.cards[0].id).toBe('new-query-trail')
  })
})

describe('Epic 056 S1 — session-lifetime conditions reuse', () => {
  function providerWith(client: PlannerClient, child: ReactNode) {
    return (
      <PlannerProvider scope={ANON_SCOPE} client={client}>
        {child}
      </PlannerProvider>
    )
  }

  it('AC-1.1: remounting the feed consumer under the same scope+frame key reuses the composed feed — no refetch', async () => {
    const plan = vi.fn().mockResolvedValue(feedWithCard('old-rag'))
    const client = { plan } as unknown as PlannerClient
    let latest: FeedState | undefined
    const onState = (s: FeedState) => {
      latest = s
    }

    const { rerender, unmount } = render(providerWith(client, <FeedProbe input={PLAN_INPUT} onState={onState} />))
    await flushMicrotasks()
    expect(latest?.status).toBe('ready')
    expect(plan).toHaveBeenCalledTimes(1)

    // "Navigate to Detail": the feed consumer unmounts; the provider stays up.
    rerender(providerWith(client, null))
    // "Navigate back": remount it under the identical key.
    rerender(providerWith(client, <FeedProbe input={PLAN_INPUT} onState={onState} />))
    await flushMicrotasks()

    expect(plan).toHaveBeenCalledTimes(1) // still 1 — fetch-free remount
    expect(latest?.status).toBe('ready')
    expect(latest?.stale).toBe(false)
    expect(latest?.revalidating).toBe(false)
    expect(latest?.feed?.cards[0].id).toBe('old-rag')
    unmount()
  })

  it('AC-1.2: a retuned key never reuses another key\'s entry — revisiting the ORIGINAL key afterwards is still fetch-free', async () => {
    const plan = vi
      .fn()
      .mockResolvedValueOnce(feedWithCard('old-rag'))
      .mockResolvedValueOnce(feedWithCard('big-schloss'))
    const client = { plan } as unknown as PlannerClient
    let latest: FeedState | undefined
    const onState = (s: FeedState) => {
      latest = s
    }
    const retuned: PlanInput = { tuning: { ...TUNING, party: 'friends' } }

    const { rerender } = render(providerWith(client, <FeedProbe input={PLAN_INPUT} onState={onState} />))
    await flushMicrotasks()
    expect(latest?.feed?.cards[0].id).toBe('old-rag')

    // A genuinely different frame — a real second fetch.
    rerender(providerWith(client, <FeedProbe input={retuned} onState={onState} />))
    await flushMicrotasks()
    expect(plan).toHaveBeenCalledTimes(2)
    expect(latest?.feed?.cards[0].id).toBe('big-schloss')

    // Unmount, then remount under the ORIGINAL key — a warm session entry,
    // never a third fetch, even though the most recent key was `retuned`.
    rerender(providerWith(client, null))
    rerender(providerWith(client, <FeedProbe input={PLAN_INPUT} onState={onState} />))
    await flushMicrotasks()

    expect(plan).toHaveBeenCalledTimes(2) // no third call
    expect(latest?.feed?.cards[0].id).toBe('old-rag')
  })

  it('AC-1.3: reload() bypasses the session store and forces a fresh /plan', async () => {
    const plan = vi
      .fn()
      .mockResolvedValueOnce(feedWithCard('old-rag'))
      .mockResolvedValueOnce(feedWithCard('old-rag-v2'))
    const client = { plan } as unknown as PlannerClient
    const { result } = renderHook(() => useFeed(PLAN_INPUT), { wrapper: wrapperWith(client) })

    await flushMicrotasks()
    expect(plan).toHaveBeenCalledTimes(1)
    expect(result.current.feed?.cards[0].id).toBe('old-rag')

    await act(async () => {
      result.current.reload()
    })
    await flushMicrotasks()

    expect(plan).toHaveBeenCalledTimes(2) // forced, not a session-store repaint
    expect(result.current.feed?.cards[0].id).toBe('old-rag-v2')
  })

  it('AC-1.4: a warm session-store hit takes priority over a stale localStorage seed on the same key — never the neutralised repaint', async () => {
    // Seed the cross-session localStorage cache with a DIFFERENT card than
    // what the (mocked) live fetch will return — a hit on this seed would be
    // visibly distinguishable from the session-store's real composed feed.
    writeFeedCache(feedKey(PLAN_INPUT, ANON_SCOPE), feedWithCard('stale-cached'), ANON_SCOPE.viewerId)
    const plan = vi.fn().mockResolvedValue(feedWithCard('fresh-session'))
    const client = { plan } as unknown as PlannerClient
    let latest: FeedState | undefined
    const onState = (s: FeedState) => {
      latest = s
    }

    const { rerender } = render(providerWith(client, <FeedProbe input={PLAN_INPUT} onState={onState} />))
    await flushMicrotasks()
    expect(latest?.feed?.cards[0].id).toBe('fresh-session')
    expect(plan).toHaveBeenCalledTimes(1)

    rerender(providerWith(client, null))
    rerender(providerWith(client, <FeedProbe input={PLAN_INPUT} onState={onState} />))
    await flushMicrotasks()

    // The session-store hit paints instantly with the FRESH feed — never the
    // stale/neutralised localStorage seed, and never a second fetch.
    expect(latest?.status).toBe('ready')
    expect(latest?.stale).toBe(false)
    expect(latest?.feed?.cards[0].id).toBe('fresh-session')
    expect(plan).toHaveBeenCalledTimes(1)
  })
})

describe('Epic 056 S2 — phase-2 presentation budget (~12s degrade, late success recovers)', () => {
  const NOT_FETCHED = [{ kind: 'weather', state: 'not-fetched' as const }]

  function phase1Feed(ids: string[]): FeedVM {
    return {
      query: '',
      cards: ids.map((id) => ({
        id,
        name: id,
        distanceMi: 1,
        conditionLines: [],
        conditions: [...NOT_FETCHED],
        warnings: [],
      })),
      notices: [],
      setAside: [],
      heldBack: [],
      readiness: { on: false, state: 'off' },
      dataSource: 'live',
      conditionsPending: true,
    }
  }

  const PATCH = {
    patches: [
      {
        id: 'old-rag',
        conditionLines: [
          { text: 'Clear skies', source: 'nws', confidence: 'stated' as const, provenance: 'live' as const },
        ],
        conditions: [{ kind: 'weather', state: 'present' as const, source: 'NWS', checkedAgo: 'just now' }],
        warnings: [],
      },
    ],
    heldBack: [],
  }

  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('AC-2.1/2.2: degrades to revalidateError only at the ~12s budget, not before — a late success still composes and clears it', async () => {
    let resolvePatch!: (p: unknown) => void
    const patchPending = new Promise((r) => {
      resolvePatch = r
    })
    const planConditions = vi.fn().mockReturnValue(patchPending)
    const client = {
      plan: vi.fn().mockResolvedValue(phase1Feed(['old-rag'])),
      planConditions,
    } as unknown as PlannerClient
    const { result } = renderHook(() => useFeed(PLAN_INPUT), { wrapper: wrapperWith(client) })

    await flushMicrotasks()
    expect(result.current.revalidating).toBe(true) // AC-2.1: exposed immediately, never blocking
    expect(result.current.revalidateError).toBeUndefined()

    await act(async () => {
      vi.advanceTimersByTime(11_999)
    })
    expect(result.current.revalidateError).toBeUndefined() // not yet — under budget

    await act(async () => {
      vi.advanceTimersByTime(1)
    })
    expect(result.current.revalidating).toBe(false)
    expect(result.current.revalidateError).toBeDefined()
    // The phase-1 cards stay up — never blanked (AC-2.2).
    expect(result.current.feed?.cards[0].id).toBe('old-rag')
    expect(result.current.feed?.cards[0].conditions?.[0].state).toBe('not-fetched')

    // The underlying fetch is still running; a late success still composes
    // and clears the degrade.
    await act(async () => {
      resolvePatch(PATCH)
      await patchPending
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(result.current.revalidateError).toBeUndefined()
    expect(result.current.feed?.cards[0].conditionLines[0].text).toBe('Clear skies')
    expect(result.current.feed?.cards[0].conditions?.[0].state).toBe('present')
  })

  it('AC-2.3: reload() after the budget degrade re-posts the conditions call only — never a full re-plan', async () => {
    const plan = vi.fn().mockResolvedValue(phase1Feed(['old-rag']))
    let firstPatchNeverResolves!: (p: unknown) => void
    const firstPending = new Promise((r) => {
      firstPatchNeverResolves = r
    })
    const planConditions = vi.fn().mockReturnValueOnce(firstPending).mockResolvedValueOnce(PATCH)
    const client = { plan, planConditions } as unknown as PlannerClient
    const { result } = renderHook(() => useFeed(PLAN_INPUT), { wrapper: wrapperWith(client) })

    await flushMicrotasks()
    await act(async () => {
      vi.advanceTimersByTime(12_000)
    })
    expect(result.current.revalidateError).toBeDefined()
    expect(plan).toHaveBeenCalledTimes(1)
    expect(planConditions).toHaveBeenCalledTimes(1)

    await act(async () => {
      result.current.reload()
    })
    await flushMicrotasks()

    expect(plan).toHaveBeenCalledTimes(1) // phase 1 never re-ran
    expect(planConditions).toHaveBeenCalledTimes(2) // phase 2 retried
    expect(result.current.revalidateError).toBeUndefined()
    expect(result.current.feed?.cards[0].conditionLines[0].text).toBe('Clear skies')
    void firstPatchNeverResolves // the original call is simply abandoned by this test, never asserted on again
  })

  it('clears the budget timer on unmount — no leaked timer, no stray late setState', async () => {
    const patchPending = new Promise(() => {
      /* deliberately never resolves within this test */
    })
    const planConditions = vi.fn().mockReturnValue(patchPending)
    const client = {
      plan: vi.fn().mockResolvedValue(phase1Feed(['old-rag'])),
      planConditions,
    } as unknown as PlannerClient
    const { result, unmount } = renderHook(() => useFeed(PLAN_INPUT), { wrapper: wrapperWith(client) })

    await flushMicrotasks()
    expect(result.current.revalidating).toBe(true)
    expect(vi.getTimerCount()).toBeGreaterThan(0) // the budget timer is armed

    unmount()
    expect(vi.getTimerCount()).toBe(0) // cleaned up, not leaked

    // Advancing past the budget after unmount must not throw (no setState on
    // an unmounted component).
    expect(() => vi.advanceTimersByTime(12_000)).not.toThrow()
  })
})

describe('Epic 056 S4 — Detail fetch calm (getCard deep-link cache)', () => {
  it('AC-4.1: a deep-linked getCard resolve is reused on a later reopen with no second network call', async () => {
    const card: CardVM = { id: 'hidden-trail', name: 'Hidden Trail', distanceMi: 2, conditionLines: [], warnings: [] }
    const getCard = vi.fn().mockResolvedValue(card)
    const client = { plan: vi.fn().mockResolvedValue(feedWithCard('other')), getCard } as unknown as PlannerClient

    const { result, rerender } = renderHook(
      (props: { cardId: string | null }) => useHarness(PLAN_INPUT, props.cardId),
      { wrapper: wrapperWith(client), initialProps: { cardId: null as string | null } },
    )
    await flushMicrotasks()

    rerender({ cardId: 'hidden-trail' })
    await flushMicrotasks()
    expect(result.current.card.status).toBe('ready')
    expect(getCard).toHaveBeenCalledTimes(1)

    // "Leave Detail" (id → null), then "reopen" the SAME id.
    rerender({ cardId: null })
    rerender({ cardId: 'hidden-trail' })
    await flushMicrotasks()

    expect(result.current.card.status).toBe('ready')
    expect(result.current.card.card?.id).toBe('hidden-trail')
    expect(getCard).toHaveBeenCalledTimes(1) // still 1 — fetch-free reopen
  })

  it('AC-4.2: a getCard failure is never cached — the next open retries, degrading exactly as today', async () => {
    const resolvedCard: CardVM = {
      id: 'hidden-trail',
      name: 'Hidden Trail',
      distanceMi: 2,
      conditionLines: [],
      warnings: [],
    }
    const getCard = vi.fn().mockRejectedValueOnce(new Error('boom')).mockResolvedValueOnce(resolvedCard)
    const client = { plan: vi.fn().mockResolvedValue(feedWithCard('other')), getCard } as unknown as PlannerClient

    const { result, rerender } = renderHook(
      (props: { cardId: string | null }) => useHarness(PLAN_INPUT, props.cardId),
      { wrapper: wrapperWith(client), initialProps: { cardId: null as string | null } },
    )
    await flushMicrotasks()

    rerender({ cardId: 'hidden-trail' })
    await flushMicrotasks()
    expect(result.current.card.status).toBe('error')

    rerender({ cardId: null })
    rerender({ cardId: 'hidden-trail' })
    await flushMicrotasks()

    expect(getCard).toHaveBeenCalledTimes(2) // retried, never stuck on a cached failure
    expect(result.current.card.status).toBe('ready')
  })

  it('reload() evicts the cached entry and forces a fresh getCard call', async () => {
    const card: CardVM = { id: 'hidden-trail', name: 'Hidden Trail', distanceMi: 2, conditionLines: [], warnings: [] }
    const getCard = vi.fn().mockResolvedValue(card)
    const client = { plan: vi.fn().mockResolvedValue(feedWithCard('other')), getCard } as unknown as PlannerClient
    const { result } = renderHook(() => useCard('hidden-trail'), { wrapper: wrapperWith(client) })

    await flushMicrotasks()
    expect(getCard).toHaveBeenCalledTimes(1)

    await act(async () => {
      result.current.reload()
    })
    await flushMicrotasks()

    expect(getCard).toHaveBeenCalledTimes(2)
  })
})

describe('Epic 056 S4 — useTrailWater session cache', () => {
  it('AC-4.1: a resolved (non-null) water answer is reused on the next reopen — fetch-free', async () => {
    const water: TrailWaterVM = {
      state: 'sources',
      basis: 'route',
      radiusM: 500,
      source: 'OSM',
      sources: [],
      provenance: 'live',
    }
    const trailWater = vi.fn().mockResolvedValue(water)
    const client = { plan: vi.fn(), trailWater } as unknown as PlannerClient

    const { result, rerender } = renderHook((props: { id: string | null }) => useTrailWater(props.id), {
      wrapper: wrapperWith(client),
      initialProps: { id: 'old-rag' as string | null },
    })
    await flushMicrotasks()
    expect(result.current.water).toEqual(water)
    expect(trailWater).toHaveBeenCalledTimes(1)

    rerender({ id: null }) // "leave Detail"
    rerender({ id: 'old-rag' }) // "reopen Detail"
    await flushMicrotasks()

    expect(result.current.water).toEqual(water)
    expect(trailWater).toHaveBeenCalledTimes(1) // no second fetch
  })

  it('AC-4.2: a null answer is never cached — every open retries, degrading exactly as today', async () => {
    const trailWater = vi.fn().mockResolvedValue(null)
    const client = { plan: vi.fn(), trailWater } as unknown as PlannerClient

    const { result, rerender } = renderHook((props: { id: string | null }) => useTrailWater(props.id), {
      wrapper: wrapperWith(client),
      initialProps: { id: 'old-rag' as string | null },
    })
    await flushMicrotasks()
    expect(result.current.water).toBeNull()
    expect(trailWater).toHaveBeenCalledTimes(1)

    rerender({ id: null })
    rerender({ id: 'old-rag' })
    await flushMicrotasks()

    expect(trailWater).toHaveBeenCalledTimes(2) // retried, never frozen on a cached miss
  })

  it('a genuine none-nearby answer (a real positive result, not a failure) is also reused', async () => {
    const water: TrailWaterVM = {
      state: 'none-nearby',
      basis: 'route',
      radiusM: 500,
      source: 'OSM',
      sources: [],
      provenance: 'live',
    }
    const trailWater = vi.fn().mockResolvedValue(water)
    const client = { plan: vi.fn(), trailWater } as unknown as PlannerClient

    const { result, rerender } = renderHook((props: { id: string | null }) => useTrailWater(props.id), {
      wrapper: wrapperWith(client),
      initialProps: { id: 'old-rag' as string | null },
    })
    await flushMicrotasks()

    rerender({ id: null })
    rerender({ id: 'old-rag' })
    await flushMicrotasks()

    expect(result.current.water).toEqual(water)
    expect(trailWater).toHaveBeenCalledTimes(1)
  })
})
