import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ANON_SCOPE } from '../data/api'
import { AuthProvider, type AuthContextValue } from '../data/auth/AuthProvider'
import { SignInControl } from './SignInControl'

function renderWith(overrides: Partial<AuthContextValue>) {
  const value: AuthContextValue = {
    status: 'anonymous',
    scope: ANON_SCOPE,
    canSignIn: true,
    signIn: vi.fn(async () => {}),
    signOut: vi.fn(async () => {}),
    ...overrides,
  }
  render(
    <AuthProvider value={value}>
      <SignInControl />
    </AuthProvider>,
  )
  return value
}

describe('SignInControl (Epic 043 S4 — calm sign-in)', () => {
  it('offers nothing when sign-in is not configured (no dead button)', () => {
    renderWith({ canSignIn: false })
    expect(screen.queryByRole('button', { name: /sign in/i })).not.toBeInTheDocument()
  })

  it('offers nothing while the session is still resolving', () => {
    renderWith({ status: 'loading' })
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('shows a quiet "Sign in" affordance when anonymous (never a gate)', () => {
    renderWith({ status: 'anonymous' })
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
  })

  it('expands to a magic-link form and calls signIn with the email', async () => {
    const user = userEvent.setup()
    const value = renderWith({ status: 'anonymous' })
    await user.click(screen.getByRole('button', { name: /sign in/i }))
    await user.type(screen.getByLabelText(/sign in with your email/i), 'josh@example.com')
    await user.click(screen.getByRole('button', { name: /send link/i }))
    expect(value.signIn).toHaveBeenCalledWith('josh@example.com')
    await waitFor(() => expect(screen.getByText(/check your email/i)).toBeInTheDocument())
  })

  it('surfaces a calm error when the link cannot be sent', async () => {
    const user = userEvent.setup()
    renderWith({ status: 'anonymous', signIn: vi.fn(async () => { throw new Error('boom') }) })
    await user.click(screen.getByRole('button', { name: /sign in/i }))
    await user.type(screen.getByLabelText(/sign in with your email/i), 'josh@example.com')
    await user.click(screen.getByRole('button', { name: /send link/i }))
    await waitFor(() => expect(screen.getByText(/couldn’t send the link/i)).toBeInTheDocument())
  })

  // Epic 057 S2: the signed-in identity/sign-out surface now sits behind an
  // initial-circle avatar, so the top bar reads quiet at rest — same content,
  // same behavior, just disclosed on a tap rather than always visible.
  it('shows a quiet initial-circle avatar when signed in (never the identity at rest)', () => {
    renderWith({
      status: 'signed-in',
      email: 'josh@example.com',
      scope: { viewerId: 'sub-1', grantedIds: [], accessToken: 'jwt' },
    })
    expect(screen.getByRole('button', { name: /account: josh@example\.com/i })).toHaveTextContent('J')
    expect(screen.queryByText(/signed in as josh@example.com/i)).not.toBeInTheDocument()
  })

  it('reveals the signed-in identity and a sign-out action on tap', async () => {
    const user = userEvent.setup()
    const value = renderWith({
      status: 'signed-in',
      email: 'josh@example.com',
      scope: { viewerId: 'sub-1', grantedIds: [], accessToken: 'jwt' },
    })
    await user.click(screen.getByRole('button', { name: /account: josh@example\.com/i }))
    expect(screen.getByText(/signed in as josh@example.com/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /sign out/i }))
    expect(value.signOut).toHaveBeenCalled()
  })

  it('falls back to a calm "?" initial when a signed-in session carries no email', () => {
    renderWith({
      status: 'signed-in',
      email: undefined,
      scope: { viewerId: 'sub-1', grantedIds: [], accessToken: 'jwt' },
    })
    expect(screen.getByRole('button', { name: 'Account' })).toHaveTextContent('?')
  })
})
