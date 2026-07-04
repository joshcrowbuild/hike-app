/**
 * The data seam wired into React. One provider chooses the adapter (mock by
 * default; HTTP when `VITE_USE_MOCK=false`) and carries the viewer scope. Screens
 * read data only through `useFeed` / `useCard`, which expose an async status
 * envelope from day one — so loading / empty / error / not-found states exist
 * before the network ever lands (no second rewrite when HTTP goes live).
 */
import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import type { MutableRefObject } from 'react'

import type { TuningState } from '../types'
import type { ScopeContext } from './api'
import { HttpPlannerClient } from './http/httpPlanner'
import { MockPlannerClient } from './mock/mockPlanner'
import type { PlanInput, PlannerClient } from './source'
import type { CardVM, EpisodeVM, FeedError, FeedVM } from './vm'

const useMockDefault = import.meta.env.VITE_USE_MOCK !== 'false'
const baseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://127.0.0.1:8000'

/** The most recent successfully-resolved feed + the tuning that produced it,
 *  scoped to the viewer that fetched it. `useCard` reads this so Detail opens
 *  from the SAME set the user is looking at — instant, and immune to a
 *  rebuilt-default refetch missing the tapped card (the "not in your current
 *  set" bug). A ref, not state: writes happen inside `useFeed`'s effect and
 *  must never itself trigger a re-render. */
interface FeedSnapshot {
  scopeKey: string
  tuning: TuningState
  feed: FeedVM
}

interface PlannerContextValue {
  client: PlannerClient
  scope: ScopeContext
  feedSnapshot: MutableRefObject<FeedSnapshot | null>
}

const PlannerContext = createContext<PlannerContextValue | null>(null)

export interface PlannerProviderProps {
  scope: ScopeContext
  /** Inject a client (tests, Storybook). Defaults to mock or HTTP by env flag. */
  client?: PlannerClient
  children: ReactNode
}

export function PlannerProvider({ scope, client, children }: PlannerProviderProps) {
  const feedSnapshot = useRef<FeedSnapshot | null>(null)
  const value = useMemo<PlannerContextValue>(
    () => ({
      client: client ?? (useMockDefault ? new MockPlannerClient() : new HttpPlannerClient(baseUrl)),
      scope,
      feedSnapshot,
    }),
    [client, scope],
  )
  return <PlannerContext.Provider value={value}>{children}</PlannerContext.Provider>
}

function usePlanner(): PlannerContextValue {
  const ctx = useContext(PlannerContext)
  if (!ctx) throw new Error('usePlanner must be used within a PlannerProvider')
  return ctx
}

/** A stable primitive key for the full scope (viewer + grants), so every hook
 *  refetches when grants change — not just when the viewer does (R5). */
function scopeKeyOf(scope: ScopeContext): string {
  return `${scope.viewerId}|${scope.grantedIds.join(',')}`
}

export function useIsAnonymous(): boolean {
  return usePlanner().scope.viewerId === 'anonymous'
}

/** Imperative access for actions (recordOutcome). Reads should use the hooks. */
export function usePlannerClient(): PlannerContextValue {
  return usePlanner()
}

export function useRecentEpisodes(): { episodes: EpisodeVM[]; loading: boolean; reload: () => void } {
  const { client, scope } = usePlanner()
  const [episodes, setEpisodes] = useState<EpisodeVM[]>([])
  const [loading, setLoading] = useState(true)
  const [nonce, setNonce] = useState(0)
  const scopeKey = scopeKeyOf(scope)
  useEffect(() => {
    let live = true
    setLoading(true)
    client
      .recentEpisodes(scope)
      .then((eps) => live && setEpisodes(eps))
      .finally(() => live && setLoading(false))
    return () => {
      live = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scopeKey, nonce])
  return { episodes, loading, reload: () => setNonce((n) => n + 1) }
}

export type EpisodeStatus = 'loading' | 'ready' | 'notfound'

export function useEpisode(id: string | null): {
  status: EpisodeStatus
  episode?: EpisodeVM
  reload: () => void
} {
  const { client, scope } = usePlanner()
  const [state, setState] = useState<{ status: EpisodeStatus; episode?: EpisodeVM }>({ status: 'loading' })
  const [nonce, setNonce] = useState(0)
  const scopeKey = scopeKeyOf(scope)
  useEffect(() => {
    if (!id) {
      setState({ status: 'notfound' })
      return
    }
    let live = true
    setState({ status: 'loading' })
    client.getEpisode(id, scope).then((episode) => {
      if (!live) return
      setState(episode ? { status: 'ready', episode } : { status: 'notfound' })
    })
    return () => {
      live = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, scopeKey, nonce])
  return { ...state, reload: () => setNonce((n) => n + 1) }
}

export type FeedStatus = 'loading' | 'ready' | 'empty' | 'error'

/** A still-loading request is "slow" once it crosses this mark — long enough that
 *  a fast response stays silent, short enough to explain a Render cold start
 *  before the 60s /plan budget elapses. Drives the "waking the server" copy. */
const SLOW_LOAD_MS = 8_000

export interface FeedState {
  status: FeedStatus
  feed?: FeedVM
  error?: FeedError
  /** True while `status === 'loading'` past {@link SLOW_LOAD_MS} — the request is
   *  likely waiting on a cold-starting server, so the surface can say so. */
  slow: boolean
  /** Re-run the request (idempotent retry — H9 recovery). */
  reload: () => void
}

export function useFeed(input: PlanInput): FeedState {
  const { client, scope, feedSnapshot } = usePlanner()
  const [state, setState] = useState<{ status: FeedStatus; feed?: FeedVM; error?: FeedError }>({
    status: 'loading',
  })
  const [slow, setSlow] = useState(false)
  // Re-run when the tuning frame, k, viewer, or a manual reload nonce changes.
  const [nonce, setNonce] = useState(0)
  const key = JSON.stringify({ t: input.tuning, k: input.k, v: scope.viewerId, g: scope.grantedIds })

  useEffect(() => {
    let live = true
    setState({ status: 'loading' })
    setSlow(false)
    // Flip to the "waking the server" affordance only if the request is still in
    // flight past the slow mark; cleared on resolve, unmount, or re-key.
    const slowTimer = setTimeout(() => live && setSlow(true), SLOW_LOAD_MS)
    client
      .plan(input, scope)
      .then((feed) => {
        if (!live) return
        if (feed.error) setState({ status: 'error', feed, error: feed.error })
        else {
          // Record the frame that produced this feed so `useCard` can resolve a
          // tapped card in-memory, and — failing that — refetch with THIS
          // tuning rather than a rebuilt default.
          feedSnapshot.current = { scopeKey: scopeKeyOf(scope), tuning: input.tuning, feed }
          if (feed.cards.length === 0) setState({ status: 'empty', feed })
          else setState({ status: 'ready', feed })
        }
      })
      .catch(() => {
        if (!live) return
        // A calm, fixed message rather than the raw exception — a stack trace
        // or "TypeError: Failed to fetch" reads as alarming and tells the user
        // nothing actionable (NNG error-message guidance: say what happened,
        // never the implementation detail).
        setState({
          status: 'error',
          error: { kind: 'offline', message: 'Couldn’t reach the planner. Try again.' },
        })
      })
      .finally(() => {
        if (live) setSlow(false)
        clearTimeout(slowTimer)
      })
    return () => {
      live = false
      clearTimeout(slowTimer)
    }
    // key encodes the meaningful inputs; client/scope are stable per provider.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, nonce])

  return { ...state, slow, reload: () => setNonce((n) => n + 1) }
}

export type CardStatus = 'loading' | 'ready' | 'notfound' | 'error'

export interface CardState {
  status: CardStatus
  card?: CardVM
  reload: () => void
}

export function useCard(id: string | null): CardState {
  const { client, scope, feedSnapshot } = usePlanner()
  const [state, setState] = useState<{ status: CardStatus; card?: CardVM }>({ status: 'loading' })
  const [nonce, setNonce] = useState(0)
  const scopeKey = scopeKeyOf(scope)

  useEffect(() => {
    if (!id) {
      setState({ status: 'notfound' })
      return
    }
    let live = true
    setState({ status: 'loading' })

    // The card the user tapped almost always lives in the feed they tapped it
    // from — resolve it there first: instant, and immune to a refetch running
    // under a different (often thinner) frame than the one that produced the
    // visible set (the "not in your current set" bug). Only a scope match is
    // trusted; a stale snapshot from a different viewer is never reused.
    const snapshot = feedSnapshot.current
    const inMemory =
      snapshot && snapshot.scopeKey === scopeKey ? snapshot.feed.cards.find((c) => c.id === id) : undefined
    if (inMemory) {
      setState({ status: 'ready', card: inMemory })
      return
    }

    // A true deep-link / an id outside the current set: refetch with the
    // CURRENT tuning (the snapshot's, if one exists for this scope) — never a
    // rebuilt default that resets facets the user actually has dialed in.
    const tuning = snapshot && snapshot.scopeKey === scopeKey ? snapshot.tuning : undefined
    client
      .getCard(id, scope, tuning)
      .then((card) => {
        if (!live) return
        setState(card ? { status: 'ready', card } : { status: 'notfound' })
      })
      .catch(() => {
        if (!live) return
        setState({ status: 'error' })
      })
    return () => {
      live = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, scopeKey, nonce])

  return { ...state, reload: () => setNonce((n) => n + 1) }
}
