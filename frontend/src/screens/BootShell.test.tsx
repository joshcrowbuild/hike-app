import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { COLDSTART_MS, REASSURE_MS } from '../data/loadingStages'
import { BootShell } from './BootShell'

describe('BootShell (craft review H1 — the first paint is designed, never a bare string)', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('renders the app chrome — wordmark topbar and a skeleton card stack, not an unstyled paragraph', () => {
    const { container } = render(<BootShell />)
    expect(screen.getByText('Curation')).toBeInTheDocument()
    expect(container.querySelector('.app-shell')).not.toBeNull()
    expect(container.querySelectorAll('.skeleton-card').length).toBeGreaterThan(0)
    // The old gate's bare fallback must never come back.
    expect(container.querySelector('.app-loading')).toBeNull()
  })

  it('steps the staged copy initial → reassure → coldstart on elapsed time alone', () => {
    render(<BootShell />)
    const status = screen.getByRole('status')
    expect(status).toHaveTextContent('Reading conditions…')

    act(() => vi.advanceTimersByTime(REASSURE_MS - 1))
    expect(status).toHaveTextContent('Reading conditions…')
    act(() => vi.advanceTimersByTime(1))
    expect(status).toHaveTextContent('Still checking conditions…')

    act(() => vi.advanceTimersByTime(COLDSTART_MS - REASSURE_MS))
    expect(status).toHaveTextContent('Waking the server — this can take up to a minute…')
  })

  it('keeps the skeletons decorative (aria-hidden) with the wait announced once via role=status', () => {
    const { container } = render(<BootShell />)
    const stack = container.querySelector('.card-stack')
    expect(stack).toHaveAttribute('aria-hidden', 'true')
    expect(screen.getByRole('status')).toBeVisible()
  })

  it('clears its stage timers on unmount (no setState-after-unmount leak)', () => {
    const { unmount } = render(<BootShell />)
    unmount()
    // Advancing past both thresholds after unmount must not warn/throw.
    expect(() => act(() => vi.advanceTimersByTime(COLDSTART_MS + 1))).not.toThrow()
    expect(vi.getTimerCount()).toBe(0)
  })
})
