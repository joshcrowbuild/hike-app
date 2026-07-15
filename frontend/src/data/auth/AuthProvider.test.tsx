import { render, screen, waitFor, act } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// A controllable fake Supabase auth, injected via the client module mock so the
// provider runs its real session logic with no live network.
type AuthCallback = (event: string, session: unknown) => void

let currentSession: unknown = null
let authCallback: AuthCallback | null = null
const signInWithOtp = vi.fn(async () => ({ error: null }))
const signOut = vi.fn(async () => {
  currentSession = null
  authCallback?.('SIGNED_OUT', null)
  return { error: null }
})

const fakeSupabase = {
  auth: {
    getSession: async () => ({ data: { session: currentSession } }),
    onAuthStateChange: (cb: AuthCallback) => {
      authCallback = cb
      return { data: { subscription: { unsubscribe: vi.fn() } } }
    },
    signInWithOtp,
    signOut,
  },
}

let configured = true
vi.mock('./supabaseClient', () => ({
  getSupabase: () => (configured ? fakeSupabase : null),
  authConfigured: () => configured,
}))

import { AuthProvider, useAuth } from './AuthProvider'

function Probe() {
  const { status, scope, email, canSignIn } = useAuth()
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="viewer">{scope.viewerId}</span>
      <span data-testid="token">{scope.accessToken ?? '-'}</span>
      <span data-testid="email">{email ?? '-'}</span>
      <span data-testid="cansignin">{String(canSignIn)}</span>
    </div>
  )
}

function renderProbe() {
  return render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  )
}

beforeEach(() => {
  currentSession = null
  authCallback = null
  configured = true
  signInWithOtp.mockClear()
  signOut.mockClear()
})
afterEach(() => vi.clearAllMocks())

describe('AuthProvider (Epic 043 S4)', () => {
  it('starts anonymous when there is no persisted session', async () => {
    renderProbe()
    await waitFor(() => expect(screen.getByTestId('status').textContent).toBe('anonymous'))
    expect(screen.getByTestId('viewer').textContent).toBe('anonymous')
    expect(screen.getByTestId('token').textContent).toBe('-')
  })

  it('derives a signed-in scope from a persisted session — sub is the viewer, token carried', async () => {
    currentSession = {
      access_token: 'jwt-abc',
      user: { id: 'sub-uuid-9', email: 'josh@example.com' },
    }
    renderProbe()
    await waitFor(() => expect(screen.getByTestId('status').textContent).toBe('signed-in'))
    expect(screen.getByTestId('viewer').textContent).toBe('sub-uuid-9') // AC-4.1 / S1
    expect(screen.getByTestId('token').textContent).toBe('jwt-abc')
    expect(screen.getByTestId('email').textContent).toBe('josh@example.com')
  })

  it('upgrades to signed-in when auth state changes after mount', async () => {
    renderProbe()
    await waitFor(() => expect(screen.getByTestId('status').textContent).toBe('anonymous'))
    act(() => {
      authCallback?.('SIGNED_IN', {
        access_token: 'jwt-later',
        user: { id: 'sub-later' },
      })
    })
    await waitFor(() => expect(screen.getByTestId('viewer').textContent).toBe('sub-later'))
    expect(screen.getByTestId('token').textContent).toBe('jwt-later')
  })

  it('reverts to anonymous on sign-out', async () => {
    currentSession = { access_token: 'jwt-abc', user: { id: 'sub-x' } }
    let ctx: ReturnType<typeof useAuth> | null = null
    function Capture() {
      ctx = useAuth()
      return null
    }
    render(
      <AuthProvider>
        <Capture />
        <Probe />
      </AuthProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('status').textContent).toBe('signed-in'))
    await act(async () => {
      await ctx!.signOut()
    })
    await waitFor(() => expect(screen.getByTestId('viewer').textContent).toBe('anonymous'))
  })

  it('stays anonymous-only and offers no sign-in when Supabase is not configured', async () => {
    configured = false
    renderProbe()
    await waitFor(() => expect(screen.getByTestId('cansignin').textContent).toBe('false'))
    expect(screen.getByTestId('status').textContent).toBe('anonymous')
  })

  it('signInWithOtp is called with the email on signIn', async () => {
    let ctx: ReturnType<typeof useAuth> | null = null
    function Capture() {
      ctx = useAuth()
      return null
    }
    render(
      <AuthProvider>
        <Capture />
      </AuthProvider>,
    )
    await act(async () => {
      await ctx!.signIn('me@example.com')
    })
    expect(signInWithOtp).toHaveBeenCalledWith({ email: 'me@example.com' })
  })
})
