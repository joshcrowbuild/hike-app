/**
 * The data seam wired into React. One provider chooses the adapter (mock by
 * default; HTTP when `VITE_USE_MOCK=false`) and carries the viewer scope. Screens
 * read data only through `useFeed` / `useCard`, which expose an async status
 * envelope from day one — so loading / empty / error / not-found states exist
 * before the network ever lands (no second rewrite when HTTP goes live).
 */
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

import type { OriginKey } from '../types'
import type { ScopeContext } from './api'
import { HttpPlannerClient } from './http/httpPlanner'
import { MockPlannerClient } from './mock/mockPlanner'
import type { PlanInput, PlannerClient } from './source'
import type { CardVM, EpisodeVM, FeedError, FeedVM } from './vm'

const useMockDefault = import.meta.env.VITE_USE_MOCK !== 'false'
const baseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://127.0.0.1:8000'

interface PlannerContextValue {
  client: PlannerClient
  scope: ScopeContext
}

const PlannerContext = createContext<PlannerContextValue | null>(null)

export interface PlannerProviderProps {
  scope: ScopeContext
  /** Inject a client (tests, Storybook). Defaults to mock or HTTP by env flag. */
  client?: PlannerClient
  children: ReactNode
}

export function PlannerProvider({ scope, client, children }: PlannerProviderProps) {
  const value = useMemo<PlannerContextValue>(
    () => ({
      client: client ?? (useMockDefault ? new MockPlannerClient() : new HttpPlannerClient(baseUrl)),
      scope,
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

/** The current viewer scope. `viewerId === 'anonymous'` is the n=0 world-browse. */
export function useScope(): ScopeContext {
  return usePlanner().scope
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
  const { client, scope } = usePlanner()
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
        else if (feed.cards.length === 0) setState({ status: 'empty', feed })
        else setState({ status: 'ready', feed })
      })
      .catch((err: unknown) => {
        if (!live) return
        setState({ status: 'error', error: { kind: 'offline', message: String(err) } })
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

export function useCard(id: string | null, origin?: OriginKey): CardState {
  const { client, scope } = usePlanner()
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
    client
      .getCard(id, scope, origin)
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
  }, [id, origin, scopeKey, nonce])

  return { ...state, reload: () => setNonce((n) => n + 1) }
}
