/**
 * A tiny owned router — no dependency, matching the owned-component ethos. Hash
 * based so a deep-link (`#/trail/stony-man`) resolves on reload with no server
 * config, which the anonymous world-browsing path needs (R7).
 *
 * History contract (R12): full routes push history (browser Back moves between
 * screens); sheets are component state and do NOT push (Escape/scrim closes
 * them, Back leaves the screen). Keeping sheets out of the router is what makes
 * Back never surprising.
 */
import { useCallback, useEffect, useState } from 'react'

export type Route =
  | { name: 'home' }
  | { name: 'trail'; id: string }
  | { name: 'trips' }
  | { name: 'outcome'; episodeId: string }
  | { name: 'memory' }
  | { name: 'belief'; id: string }

export function parseHash(hash: string): Route {
  const path = hash.replace(/^#/, '').replace(/^\/+/, '').replace(/\/+$/, '')
  const parts = path.split('/').filter(Boolean)
  if (parts.length === 0) return { name: 'home' }
  if (parts[0] === 'trail' && parts[1]) return { name: 'trail', id: decodeURIComponent(parts[1]) }
  if (parts[0] === 'trips') return { name: 'trips' }
  if (parts[0] === 'trip' && parts[1] && parts[2] === 'outcome')
    return { name: 'outcome', episodeId: decodeURIComponent(parts[1]) }
  if (parts[0] === 'memory' && parts[1]) return { name: 'belief', id: decodeURIComponent(parts[1]) }
  if (parts[0] === 'memory') return { name: 'memory' }
  return { name: 'home' }
}

export function formatRoute(route: Route): string {
  switch (route.name) {
    case 'home':
      return '#/'
    case 'trail':
      return `#/trail/${encodeURIComponent(route.id)}`
    case 'trips':
      return '#/trips'
    case 'outcome':
      return `#/trip/${encodeURIComponent(route.episodeId)}/outcome`
    case 'memory':
      return '#/memory'
    case 'belief':
      return `#/memory/${encodeURIComponent(route.id)}`
  }
}

export interface Router {
  route: Route
  navigate: (route: Route) => void
  back: () => void
}

export function useRoute(): Router {
  const [route, setRoute] = useState<Route>(() =>
    parseHash(typeof window === 'undefined' ? '' : window.location.hash),
  )

  useEffect(() => {
    const onHash = () => setRoute(parseHash(window.location.hash))
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const navigate = useCallback((next: Route) => {
    const hash = formatRoute(next)
    if (window.location.hash !== hash) window.location.hash = hash
    else setRoute(next)
  }, [])

  const back = useCallback(() => window.history.back(), [])

  return { route, navigate, back }
}
