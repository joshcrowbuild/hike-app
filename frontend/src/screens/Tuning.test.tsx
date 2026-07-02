import { useState } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { PanelSheet } from './Tuning'
import type { TuningState } from '../types'

const BASE: TuningState = {
  origin: 'frontRoyal',
  when: 'weekendMorning',
  effort: 'moderate',
  party: 'solo',
  today: 'standard',
  readinessOn: false,
  prompt: '',
}

/** A thin stateful harness — PanelSheet is controlled, so the test drives it
 *  the way App.tsx does: real useState, not a mock setState. */
function OriginPanel() {
  const [state, setState] = useState<TuningState>(BASE)
  return <PanelSheet panel="origin" state={state} setState={setState} onClose={() => {}} onBack={() => {}} />
}

afterEach(() => vi.restoreAllMocks())

describe('"Near me" origin control', () => {
  it('requests location only on tap, then drives the origin from the live fix', async () => {
    const getCurrentPosition = vi.fn((ok) => ok({ coords: { latitude: 39.05, longitude: -77.7 } }))
    Object.defineProperty(navigator, 'geolocation', { value: { getCurrentPosition }, configurable: true })
    const user = userEvent.setup()
    render(<OriginPanel />)

    expect(getCurrentPosition).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: /near me.*use current location/i }))
    expect(getCurrentPosition).toHaveBeenCalledTimes(1)

    // The control swaps to its active state — proof the tuning frame now
    // carries the live fix rather than a named origin.
    expect(await screen.findByText(/use a named place instead/i)).toBeInTheDocument()
    // The named picker is still present and usable underneath (never removed).
    expect(screen.getByRole('radio', { name: 'Luray' })).toBeInTheDocument()
  })

  it('discloses a denial and falls back to the manual picker — never fabricates a position', async () => {
    const getCurrentPosition = vi.fn((_ok, err) => err({ code: 1, PERMISSION_DENIED: 1, message: 'denied' }))
    Object.defineProperty(navigator, 'geolocation', { value: { getCurrentPosition }, configurable: true })
    const user = userEvent.setup()
    render(<OriginPanel />)

    await user.click(screen.getByRole('button', { name: /near me.*use current location/i }))
    expect(await screen.findByText(/location permission denied/i)).toBeInTheDocument()
    // No fabricated fix: the control stays in its inactive state.
    expect(screen.queryByText(/use a named place instead/i)).not.toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Front Royal' })).toBeInTheDocument()
  })

  it('discloses unavailable geolocation honestly (older browser / insecure context)', async () => {
    Object.defineProperty(navigator, 'geolocation', { value: undefined, configurable: true })
    const user = userEvent.setup()
    render(<OriginPanel />)

    await user.click(screen.getByRole('button', { name: /near me.*use current location/i }))
    expect(await screen.findByText(/location isn.t available here/i)).toBeInTheDocument()
  })

  it('clears the live fix when a named origin is picked (named origins unchanged)', async () => {
    const getCurrentPosition = vi.fn((ok) => ok({ coords: { latitude: 39.05, longitude: -77.7 } }))
    Object.defineProperty(navigator, 'geolocation', { value: { getCurrentPosition }, configurable: true })
    const user = userEvent.setup()
    render(<OriginPanel />)

    await user.click(screen.getByRole('button', { name: /near me.*use current location/i }))
    expect(await screen.findByText(/use a named place instead/i)).toBeInTheDocument()

    await user.click(screen.getByRole('radio', { name: 'Luray' }))
    expect(screen.queryByText(/use a named place instead/i)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /near me.*use current location/i })).toBeInTheDocument()
  })
})
