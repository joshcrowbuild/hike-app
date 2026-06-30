import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'

import { PlannerProvider, useFeed } from './PlannerProvider'
import { ANON_SCOPE } from './api'
import type { PlanInput, PlannerClient } from './source'
import type { FeedVM } from './vm'
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
