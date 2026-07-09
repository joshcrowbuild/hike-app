import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'

import { PlannerProvider, useCard, useFeed } from './PlannerProvider'
import { ANON_SCOPE } from './api'
import type { ScopeContext } from './api'
import { feedKey, readFeedCache, resetFeedCacheForTests, writeFeedCache } from './feedCache'
import type { PlanInput, PlannerClient } from './source'
import type { CardVM, FeedVM } from './vm'
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

  it('steps loadingStage from initial → reassure → coldstart at the 10s and 25s marks', () => {
    const { client } = deferredClient()
    const { result } = renderHook(() => useFeed(PLAN_INPUT), { wrapper: wrapperWith(client) })

    expect(result.current.status).toBe('loading')
    expect(result.current.loadingStage).toBe('initial')

    act(() => {
      vi.advanceTimersByTime(9_999)
    })
    expect(result.current.loadingStage).toBe('initial')

    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(result.current.loadingStage).toBe('reassure')

    act(() => {
      vi.advanceTimersByTime(14_999)
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

describe('Epic 039 S3 — anonymous stale-while-revalidate', () => {
  function seedCache(input: PlanInput, feed: FeedVM, scope: ScopeContext = ANON_SCOPE) {
    writeFeedCache(feedKey(input, scope), feed)
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
    expect(readFeedCache(feedKey(PLAN_INPUT, ANON_SCOPE), Date.now())?.feed.cards[0].id).toBe('old-rag')
  })

  it('AC-3.5b: a non-anonymous viewer neither reads nor writes the cache', async () => {
    // Seed under the anonymous key so a leak into josh's read would show up as a hit.
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

    // No stale paint for a non-anonymous viewer — starts loading, same as today.
    expect(result.current.status).toBe('loading')
    expect(result.current.stale).toBe(false)

    await act(async () => {
      resolve(feedWithCard('old-rag'))
      await pending
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(readFeedCache(feedKey(PLAN_INPUT, josh), Date.now())).toBeNull()
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
    expect(readFeedCache(feedKey(PLAN_INPUT, ANON_SCOPE), Date.now())).toBeNull()

    const erroredFeed: FeedVM = { ...feedWithCard('y'), error: { kind: 'partial', message: 'partial' } }
    const client2 = { plan: vi.fn().mockResolvedValue(erroredFeed) } as unknown as PlannerClient
    const { result: r2 } = renderHook(() => useFeed(PLAN_INPUT), { wrapper: wrapperWith(client2) })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(r2.current.status).toBe('error')
    expect(readFeedCache(feedKey(PLAN_INPUT, ANON_SCOPE), Date.now())).toBeNull()
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
