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
import type { CardVM, FeedError, FeedVM } from './vm'

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

export type FeedStatus = 'loading' | 'ready' | 'empty' | 'error'

export interface FeedState {
  status: FeedStatus
  feed?: FeedVM
  error?: FeedError
  /** Re-run the request (idempotent retry — H9 recovery). */
  reload: () => void
}

export function useFeed(input: PlanInput): FeedState {
  const { client, scope } = usePlanner()
  const [state, setState] = useState<{ status: FeedStatus; feed?: FeedVM; error?: FeedError }>({
    status: 'loading',
  })
  // Re-run when the tuning frame, k, viewer, or a manual reload nonce changes.
  const [nonce, setNonce] = useState(0)
  const key = JSON.stringify({ t: input.tuning, k: input.k, v: scope.viewerId, g: scope.grantedIds })

  useEffect(() => {
    let live = true
    setState({ status: 'loading' })
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
    return () => {
      live = false
    }
    // key encodes the meaningful inputs; client/scope are stable per provider.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, nonce])

  return { ...state, reload: () => setNonce((n) => n + 1) }
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
  }, [id, origin, scope.viewerId, nonce])

  return { ...state, reload: () => setNonce((n) => n + 1) }
}
