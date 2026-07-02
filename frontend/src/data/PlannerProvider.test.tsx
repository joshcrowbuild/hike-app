import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'

import { PlannerProvider, useCard, useFeed } from './PlannerProvider'
import { ANON_SCOPE } from './api'
import type { PlanInput, PlannerClient } from './source'
import type { CardVM, FeedVM } from './vm'
import type { TuningState } from '../types'

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

describe('useFeed slow / cold-start state', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('flips slow=true only after the 8s mark while still loading', () => {
    const { client } = deferredClient()
    const { result } = renderHook(() => useFeed(PLAN_INPUT), { wrapper: wrapperWith(client) })

    expect(result.current.status).toBe('loading')
    expect(result.current.slow).toBe(false)

    act(() => {
      vi.advanceTimersByTime(7_999)
    })
    expect(result.current.slow).toBe(false)

    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(result.current.slow).toBe(true)
  })

  it('clears slow once the feed resolves', async () => {
    const { client, resolve, pending } = deferredClient()
    const { result } = renderHook(() => useFeed(PLAN_INPUT), { wrapper: wrapperWith(client) })

    act(() => {
      vi.advanceTimersByTime(8_000)
    })
    expect(result.current.slow).toBe(true)

    // Resolve and drain the plan() promise chain (.then sets status, .finally
    // clears slow) inside act — no waitFor, which would poll on stalled fake timers.
    await act(async () => {
      resolve(READY_FEED)
      await pending
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(result.current.status).toBe('ready')
    expect(result.current.slow).toBe(false)
  })

  it('resets slow when the input re-keys mid cold-start (retune while waking)', () => {
    const { client } = deferredClient()
    const { result, rerender } = renderHook((props: { input: PlanInput }) => useFeed(props.input), {
      wrapper: wrapperWith(client),
      initialProps: { input: PLAN_INPUT },
    })

    act(() => {
      vi.advanceTimersByTime(8_000)
    })
    expect(result.current.slow).toBe(true)

    // Retuning changes the effect key — the slow flag resets and re-arms its timer
    // rather than leaving "Waking the server…" stuck under the new frame.
    const retuned: PlanInput = { tuning: { ...TUNING, party: 'friends' } }
    act(() => {
      rerender({ input: retuned })
    })
    expect(result.current.slow).toBe(false)

    act(() => {
      vi.advanceTimersByTime(8_000)
    })
    expect(result.current.slow).toBe(true)
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
