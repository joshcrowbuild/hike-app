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
import { feedKey, readFeedCache, staleAgeLabel, toStalePaint, writeFeedCache } from './feedCache'
import { HttpPlannerClient } from './http/httpPlanner'
import { MockPlannerClient } from './mock/mockPlanner'
import { originCoordsMap, useOrigins } from './regionsCatalog'
import type { PlanInput, PlannerClient } from './source'
import { USE_MOCK } from './useMock'
import type { CardVM, EpisodeVM, FeedError, FeedVM, TrailWaterVM } from './vm'

const useMockDefault = USE_MOCK
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
  // The config-driven origin catalog (Phase 2) — HttpPlannerClient needs the
  // resolved coords before its first /plan call, so real (non-injected) HTTP mode
  // gates rendering until this has loaded (below); mock and injected-client (tests,
  // Storybook) never touch it and render immediately.
  const { origins, loading: originsLoading } = useOrigins()
  const coordsMap = useMemo(() => originCoordsMap(origins), [origins])

  const value = useMemo<PlannerContextValue>(
    () => ({
      client: client ?? (useMockDefault ? new MockPlannerClient() : new HttpPlannerClient(baseUrl, coordsMap)),
      scope,
      feedSnapshot,
    }),
    [client, scope, coordsMap],
  )

  if (!client && !useMockDefault && originsLoading) {
    return (
      <p className="app-loading" role="status">
        Loading…
      </p>
    )
  }

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

/** Where a still-loading request sits on the honest progress ladder (D4 —
 *  perceived performance): a wait past NNG's ~10s attention threshold must keep
 *  saying something new rather than sitting on a line that now reads as frozen.
 *  `reassure` covers ordinary-but-slow live calls; `coldstart` is long enough
 *  that a Render free-tier wake (30-60s) is the more likely explanation, still
 *  well inside the 60s /plan budget. */
export type LoadingStage = 'initial' | 'reassure' | 'coldstart'

const REASSURE_MS = 10_000
const COLDSTART_MS = 25_000

export interface FeedState {
  status: FeedStatus
  feed?: FeedVM
  error?: FeedError
  /** {@link LoadingStage} while `status === 'loading'`; `'initial'` otherwise. */
  loadingStage: LoadingStage
  /** `true` while `feed` is a repainted last-visit cache entry (Epic 039 S3),
   *  not the current fetch's result — the VM itself stays honest via each
   *  card's `stale-degraded` silence; this is the state signal the surface
   *  reads to render the disclosure line. */
  stale: boolean
  /** `true` while a fresh fetch is in flight behind a stale paint. */
  revalidating: boolean
  /** Relative age of the stale paint ("2h ago"), present only while `stale`. */
  staleAsOf?: string
  /** Set when a revalidation attempt fails WHILE a stale feed is showing — the
   *  stale feed stays up (never blanked to the full error screen); absent once
   *  revalidation succeeds or on a fresh retry. */
  revalidateError?: FeedError
  /** Re-run the request (idempotent retry — H9 recovery). */
  reload: () => void
}

interface FeedInternalState {
  status: FeedStatus
  feed?: FeedVM
  error?: FeedError
  stale: boolean
  revalidating: boolean
  staleAsOf?: string
  revalidateError?: FeedError
}

/** Shared by the lazy mount seed and the retune re-hydrate effect so both
 *  behave identically (one helper — see the binding builder note on
 *  `feedKey`). Anonymous-only (Rule #5): a signed-in viewer's feed never
 *  enters `localStorage`, so this returns null before ever touching it. */
function hydrateStale(input: PlanInput, scope: ScopeContext): { feed: FeedVM; staleAsOf: string } | null {
  if (scope.viewerId !== 'anonymous') return null
  const hit = readFeedCache(feedKey(input, scope), Date.now())
  if (!hit || hit.feed.cards.length === 0) return null
  const staleAsOf = staleAgeLabel(hit.savedAt, Date.now())
  return { feed: toStalePaint(hit.feed, staleAsOf), staleAsOf }
}

export function useFeed(input: PlanInput): FeedState {
  const { client, scope, feedSnapshot } = usePlanner()
  // Lazy initializer, not an effect-only seed (FLASH IS REAL): an effect runs
  // AFTER the first commit, so seeding only there would still paint one
  // skeleton frame first. This runs once, synchronously, before that first
  // commit — so an anonymous viewer with a fresh cache entry never sees the
  // skeleton at all (AC-3.1).
  const [state, setState] = useState<FeedInternalState>(() => {
    const seed = hydrateStale(input, scope)
    return seed
      ? { status: 'ready', feed: seed.feed, stale: true, revalidating: true, staleAsOf: seed.staleAsOf }
      : { status: 'loading', stale: false, revalidating: false }
  })
  const [loadingStage, setLoadingStage] = useState<LoadingStage>('initial')
  // Re-run when the tuning frame, k, viewer, or a manual reload nonce changes.
  // Shared with feedCache's storage key (feedKey) so the two can never diverge
  // — a cache entry could otherwise repaint under the wrong frame.
  const [nonce, setNonce] = useState(0)
  const key = feedKey(input, scope)

  useEffect(() => {
    let live = true
    // Re-hydrate on every key change too (a retune), not just on mount — the
    // same helper the lazy initializer used, so mount and retune behave
    // identically.
    const seed = hydrateStale(input, scope)
    let reassureTimer: ReturnType<typeof setTimeout> | undefined
    let coldstartTimer: ReturnType<typeof setTimeout> | undefined
    if (seed) {
      // Cards are already on screen — skip the loading-copy ladder entirely
      // (no reassure/coldstart timers to arm).
      setState({ status: 'ready', feed: seed.feed, stale: true, revalidating: true, staleAsOf: seed.staleAsOf })
    } else {
      setState({ status: 'loading', stale: false, revalidating: false })
      setLoadingStage('initial')
      // Step the copy forward only if the request is still in flight past each
      // mark; cleared on resolve, unmount, or re-key so a retune never leaves
      // stale reassurance copy stuck under the new frame.
      reassureTimer = setTimeout(() => live && setLoadingStage('reassure'), REASSURE_MS)
      coldstartTimer = setTimeout(() => live && setLoadingStage('coldstart'), COLDSTART_MS)
    }
    client
      .plan(input, scope)
      .then((feed) => {
        if (!live) return
        if (feed.error) {
          if (seed) {
            // A revalidation failure while a stale feed is showing — the good
            // cards stay up; never blank a usable view to the error screen
            // (Rule #6: enrichment degrades, it's never a dependency).
            setState({
              status: 'ready',
              feed: seed.feed,
              stale: true,
              revalidating: false,
              staleAsOf: seed.staleAsOf,
              revalidateError: feed.error,
            })
          } else {
            setState({ status: 'error', feed, error: feed.error, stale: false, revalidating: false })
          }
        } else {
          // Record the frame that produced this feed so `useCard` can resolve a
          // tapped card in-memory, and — failing that — refetch with THIS
          // tuning rather than a rebuilt default. Written ONLY on a fresh
          // resolve, never from the stale seed, so a stripped-condition card
          // can never be handed to Detail as authoritative.
          feedSnapshot.current = { scopeKey: scopeKeyOf(scope), tuning: input.tuning, feed }
          if (scope.viewerId === 'anonymous' && feed.cards.length > 0) writeFeedCache(key, feed)
          if (feed.cards.length === 0) setState({ status: 'empty', feed, stale: false, revalidating: false })
          else setState({ status: 'ready', feed, stale: false, revalidating: false })
        }
      })
      .catch(() => {
        if (!live) return
        // A calm, fixed message rather than the raw exception — a stack trace
        // or "TypeError: Failed to fetch" reads as alarming and tells the user
        // nothing actionable (NNG error-message guidance: say what happened,
        // never the implementation detail).
        const error: FeedError = { kind: 'offline', message: 'Couldn’t reach the planner. Try again.' }
        if (seed) {
          setState({
            status: 'ready',
            feed: seed.feed,
            stale: true,
            revalidating: false,
            staleAsOf: seed.staleAsOf,
            revalidateError: error,
          })
        } else {
          setState({ status: 'error', error, stale: false, revalidating: false })
        }
      })
      .finally(() => {
        if (live) setLoadingStage('initial')
        clearTimeout(reassureTimer)
        clearTimeout(coldstartTimer)
      })
    return () => {
      live = false
      clearTimeout(reassureTimer)
      clearTimeout(coldstartTimer)
    }
    // key encodes the meaningful inputs; client/scope are stable per provider.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, nonce])

  return { ...state, loadingStage, reload: () => setNonce((n) => n + 1) }
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

/**
 * The water answer for one trail (Epic 041) — resolved through the client seam
 * so mock and live behave identically. Two-value envelope, no error state by
 * design: `trailWater` degrades every failure to null (silence), and Detail
 * renders a null answer as NO row (CDP-02 not-fetched) — water is enrichment
 * on the commitment view, never a dependency. `loading` lets the surface
 * simply wait (render nothing) rather than flash an answer in.
 */
export function useTrailWater(id: string | null): { water: TrailWaterVM | null; loading: boolean } {
  const { client, scope } = usePlanner()
  const [state, setState] = useState<{ water: TrailWaterVM | null; loading: boolean }>({
    water: null,
    loading: true,
  })
  const scopeKey = scopeKeyOf(scope)

  useEffect(() => {
    if (!id) {
      setState({ water: null, loading: false })
      return
    }
    let live = true
    setState({ water: null, loading: true })
    client
      .trailWater(id, scope)
      .then((water) => live && setState({ water, loading: false }))
      .catch(() => live && setState({ water: null, loading: false }))
    return () => {
      live = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, scopeKey])

  return state
}
