/**
 * The calm sign-in affordance (Epic 043 S4; avatar disclosure Epic 057 S2).
 *
 * Placed quietly in the top bar — it OFFERS sign-in, never gates browsing
 * (AC-4.2). Anonymous: a quiet "Sign in" text-action that expands into an inline
 * magic-link form. Signed-in: an initial-circle avatar (the SAME "signed in as
 * {email}" + "Sign out" surface, now behind a tap so the top bar stays quiet at
 * rest) — no new auth logic, just a disclosure over the existing behavior. When
 * Supabase isn't configured (`canSignIn` false) it renders nothing — no dead
 * button.
 *
 * Uses the codebase's plain-button + native-input idiom (same as SearchLine),
 * `.text-action` styling, and a polite `role="status"` for the sent/error state —
 * no new UI dependency, no modal, no nag.
 */
import { useState, type FormEvent } from 'react'

import { useAuth } from '../data/auth/AuthProvider'

/** The avatar's single glyph: the viewer's first initial, or a calm fallback
 *  when a session carries no email (never a blank circle). */
function initialFor(email: string | undefined): string {
  const trimmed = email?.trim()
  return trimmed ? trimmed.charAt(0).toUpperCase() : '?'
}

export function SignInControl() {
  const { status, email, canSignIn, signIn, signOut } = useAuth()
  const [open, setOpen] = useState(false)
  const [accountOpen, setAccountOpen] = useState(false)
  const [value, setValue] = useState('')
  const [phase, setPhase] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle')

  // No sign-in configured (or still resolving a persisted session) → offer nothing.
  if (!canSignIn || status === 'loading') return null

  if (status === 'signed-in') {
    return (
      <span className="signin-control">
        <button
          className="avatar-chip"
          type="button"
          onClick={() => setAccountOpen((v) => !v)}
          aria-expanded={accountOpen}
          aria-label={email ? `Account: ${email}` : 'Account'}
        >
          {initialFor(email)}
        </button>
        {accountOpen ? (
          <span className="signin-account-sheet" role="status">
            {email ? <span className="signin-who">Signed in as {email}</span> : null}
            <button className="text-action" type="button" onClick={() => void signOut()}>
              Sign out
            </button>
          </span>
        ) : null}
      </span>
    )
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const addr = value.trim()
    if (!addr) return
    setPhase('sending')
    try {
      await signIn(addr)
      setPhase('sent')
    } catch {
      setPhase('error')
    }
  }

  if (!open) {
    return (
      <button className="text-action" type="button" onClick={() => setOpen(true)}>
        Sign in
      </button>
    )
  }

  return (
    <form className="signin-form" onSubmit={handleSubmit}>
      <label className="signin-label-wrap">
        <span className="signin-label">Sign in with your email</span>
        <input
          className="signin-input"
          type="email"
          autoComplete="email"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder="you@example.com"
          disabled={phase === 'sending' || phase === 'sent'}
        />
      </label>
      {phase === 'sent' ? (
        <span className="signin-note" role="status">
          Check your email for a sign-in link.
        </span>
      ) : (
        <button className="text-action" type="submit" disabled={phase === 'sending'}>
          {phase === 'sending' ? 'Sending…' : 'Send link'}
        </button>
      )}
      {phase === 'error' ? (
        <span className="signin-note signin-note-error" role="status">
          Couldn’t send the link. Try again.
        </span>
      ) : null}
    </form>
  )
}
