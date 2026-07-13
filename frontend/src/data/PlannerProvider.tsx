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
import { composeConditions } from './composeConditions'
import { feedKey, readFeedCache, staleAgeLabel, toStalePaint, writeFeedCache } from './feedCache'
import { HttpPlannerClient } from './http/httpPlanner'
import { COLDSTART_MS, REASSURE_MS, type LoadingStage } from './loadingStages'
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
  /** Rendered while the origin-catalog gate blocks (live HTTP mode only) —
   *  the app's true first paint on a cold server (craft review H1). The UI
   *  layer supplies the designed shell (`main.tsx` passes `<BootShell />`) so
   *  this data module never imports a screen — no data→screens edge to grow
   *  into an import cycle. The built-in default is a styled honest minimum,
   *  never the unstyled bare string H1 flagged. */
  fallback?: ReactNode
  children: ReactNode
}

export function PlannerProvider({ scope, client, fallback, children }: PlannerProviderProps) {
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

  // The cold-start gate (craft review H1): on a Render free-tier wake this
  // blocks for up to a minute, so what renders here must be designed — the
  // live mount passes the BootShell (staged copy + skeleton chrome).
  if (!client && !useMockDefault && originsLoading) {
    return (
      <>
        {fallback ?? (
          <div className="app-shell">
            <p className="state-note" role="status">
              Loading…
            </p>
          </div>
        )}
      </>
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

/** The honest progress ladder (D4) now lives in `loadingStages.ts`, shared
 *  with the BootShell gate above; re-exported so existing consumers keep one
 *  import site for feed state. */
export type { LoadingStage } from './loadingStages'

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

/** The calm patch-failure disclosure (Epic 040 AC-3.4): the cards stay usable,
 *  the gap is named, retry re-posts the conditions call only. */
const CONDITIONS_ERROR: FeedError = {
  kind: 'partial',
  message: 'Couldn’t verify current conditions — try again.',
}

export function useFeed(input: PlanInput): FeedState {
  const { client, scope, feedSnapshot } = usePlanner()
  // Two-phase retry seam (Epic 040 AC-3.4): set ONLY while a conditions patch
  // has failed and its phase-1 feed is still on screen — `reload()` then
  // re-posts the conditions call alone instead of re-running the whole plan.
  // Cleared on every effect re-key (a retune invalidates the pending patch).
  const retryConditions = useRef<(() => void) | null>(null)
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
    // A re-key (retune/reload) invalidates any failed patch from the previous
    // frame — its phase-1 feed is no longer the one on screen.
    retryConditions.current = null
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
          const planConditions = client.planConditions?.bind(client)
          if (feed.conditionsPending && planConditions && feed.cards.length > 0) {
            // Two-phase (Epic 040): phase 1 landed — paint the fresh ranked
            // cards NOW (their per-kind `not-fetched` silence is honest on its
            // own, D2), keep `revalidating` up for the feed-level "Checking
            // current conditions…" line, and only then start phase 2 (AC-3.1:
            // the conditions call never blocks this paint). A stale S3 seed is
            // replaced here with `stale` cleared — the cards are no longer
            // stale, only unverified (D4's ladder, step 2).
            const runConditions = () => {
              retryConditions.current = null
              setState({ status: 'ready', feed, stale: false, revalidating: true })
              planConditions(input, scope, feed.cards.map((c) => c.id))
                .then((patch) => {
                  if (!live) return
                  const composed = composeConditions(feed, patch)
                  // D4 write-gate: ONLY the composed (phase-2-complete) feed
                  // reaches the snapshot or the stale-paint cache — an
                  // all-not-fetched frame must never re-serve later as "your
                  // last visit", and Detail must never resolve a card from a
                  // half-composed feed.
                  feedSnapshot.current = { scopeKey: scopeKeyOf(scope), tuning: input.tuning, feed: composed }
                  if (scope.viewerId === 'anonymous' && composed.cards.length > 0) writeFeedCache(key, composed)
                  if (composed.cards.length === 0)
                    setState({ status: 'empty', feed: composed, stale: false, revalidating: false })
                  else setState({ status: 'ready', feed: composed, stale: false, revalidating: false })
                })
                .catch(() => {
                  if (!live) return
                  // The phase-1 cards stay usable and keep their honest
                  // silence; the gap is disclosed, never a blank or a
                  // fake-clear (AC-3.4). Retry re-posts phase 2 only.
                  retryConditions.current = runConditions
                  setState({
                    status: 'ready',
                    feed,
                    stale: false,
                    revalidating: false,
                    revalidateError: CONDITIONS_ERROR,
                  })
                })
            }
            runConditions()
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
      retryConditions.current = null
      clearTimeout(reassureTimer)
      clearTimeout(coldstartTimer)
    }
    // key encodes the meaningful inputs; client/scope are stable per provider.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, nonce])

  const reload = () => {
    // A failed conditions patch retries the conditions call ONLY (Epic 040
    // AC-3.4) — the ranked cards on screen are already the fresh phase-1
    // result; re-running the whole plan would re-spend the rank and could
    // reshuffle what the user is looking at.
    const retry = retryConditions.current
    if (retry) {
      retry()
      return
    }
    setNonce((n) => n + 1)
  }

  return { ...state, loadingStage, reload }
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
