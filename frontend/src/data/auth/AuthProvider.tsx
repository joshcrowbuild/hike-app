/**
 * Auth context (Epic 043 S4) — the calm sign-in seam.
 *
 * Holds the Supabase session and derives the `ScopeContext` the planner threads
 * through every call: signed-in → `{ viewerId: sub, accessToken }`; otherwise the
 * anonymous scope. The session persists across reloads (supabase-js localStorage)
 * and this provider re-derives the scope on every auth change (AC-4.1).
 *
 * Calm by construction (AC-4.2): this NEVER gates rendering — the app mounts
 * anonymous and browsing is always available. A private action (save / log a trip)
 * offers sign-in where it's needed; nothing here nags or wall the world.
 *
 * When Supabase isn't configured (`getSupabase()` null), `status` is `'anonymous'`
 * forever and `signIn` is a no-op that surfaces an honest unavailability — the app
 * runs exactly as it did before managed auth, anonymous-only.
 */
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import type { Session } from '@supabase/supabase-js'

import { ANON_SCOPE, type ScopeContext } from '../api'
import { evictFeedCache } from '../feedCache'
import { authConfigured, getSupabase } from './supabaseClient'

export type AuthStatus = 'loading' | 'anonymous' | 'signed-in'

export interface AuthContextValue {
  status: AuthStatus
  /** The viewer scope for the planner — anonymous until a session lands. */
  scope: ScopeContext
  /** The signed-in user's email, for a quiet "signed in as" affordance. */
  email?: string
  /** Whether sign-in is even possible (Supabase configured) — the UI hides the
   *  affordance entirely when false, never a dead button. */
  canSignIn: boolean
  /** Send a magic-link / OTP sign-in email. Rejects when auth isn't configured. */
  signIn: (email: string) => Promise<void>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

function scopeFromSession(session: Session | null): ScopeContext {
  if (!session?.user?.id || !session.access_token) return ANON_SCOPE
  // The verified identity the backend trusts is the token's `sub` (== user.id);
  // grants stay empty until the household model lands (Phase F).
  return { viewerId: session.user.id, grantedIds: [], accessToken: session.access_token }
}

export interface AuthProviderProps {
  children: ReactNode
  /** Test seam: inject a ready value to render screens without a live Supabase. */
  value?: AuthContextValue
}

export function AuthProvider({ children, value }: AuthProviderProps) {
  if (value) {
    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
  }
  return <LiveAuthProvider>{children}</LiveAuthProvider>
}

function LiveAuthProvider({ children }: { children: ReactNode }) {
  const supabase = getSupabase()
  const canSignIn = authConfigured()
  // Start anonymous, not blocked: if a persisted session exists it lands via the
  // effect below and the scope upgrades — browsing is never gated on that check.
  const [session, setSession] = useState<Session | null>(null)
  const [resolved, setResolved] = useState(!supabase)

  useEffect(() => {
    if (!supabase) return
    let live = true
    supabase.auth.getSession().then(({ data }) => {
      if (!live) return
      setSession(data.session)
      setResolved(true)
    })
    const { data: sub } = supabase.auth.onAuthStateChange((_event, next) => {
      if (live) setSession(next)
    })
    return () => {
      live = false
      sub.subscription.unsubscribe()
    }
  }, [supabase])

  const ctx = useMemo<AuthContextValue>(() => {
    const scope = scopeFromSession(session)
    const status: AuthStatus = !resolved
      ? 'loading'
      : scope.viewerId === 'anonymous'
        ? 'anonymous'
        : 'signed-in'
    return {
      status,
      scope,
      email: session?.user?.email ?? undefined,
      canSignIn,
      signIn: async (email: string) => {
        if (!supabase) throw new Error('Sign-in is not available in this build.')
        const { error } = await supabase.auth.signInWithOtp({ email })
        if (error) throw error
      },
      signOut: async () => {
        // Epic 052 WP-5 / spec III.2: evict THIS viewer's cached feed on
        // sign-out (Rule #5 — a signed-out viewer's derived feed must never
        // linger, readable, for whoever uses the device next). Captured
        // before the network call and evicted in `finally` so a failed/slow
        // remote sign-out can never leave the local cache behind — the local
        // guarantee doesn't depend on the network succeeding.
        const viewerId = session?.user?.id
        try {
          if (supabase) await supabase.auth.signOut()
        } finally {
          if (viewerId) evictFeedCache(viewerId)
        }
      },
    }
  }, [session, resolved, canSignIn, supabase])

  return <AuthContext.Provider value={ctx}>{children}</AuthContext.Provider>
}

/** A safe anonymous, no-op auth context — the value `useAuth` returns when no
 *  `AuthProvider` is above it (Storybook, an isolated screen test, the gallery).
 *  A leaf affordance like `SignInControl` then simply renders nothing rather than
 *  crashing an unrelated screen; `canSignIn: false` guarantees it. */
const ANON_AUTH: AuthContextValue = {
  status: 'anonymous',
  scope: ANON_SCOPE,
  canSignIn: false,
  signIn: async () => {
    throw new Error('Sign-in is not available here.')
  },
  signOut: async () => {},
}

export function useAuth(): AuthContextValue {
  return useContext(AuthContext) ?? ANON_AUTH
}
