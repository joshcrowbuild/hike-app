import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import * as styles from './UpdateChip.css'
import { UpdateChip } from './UpdateChip'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('UpdateChip', () => {
  it('defaults to the stalePaint copy ("Updating conditions…")', () => {
    render(<UpdateChip />)
    expect(screen.getByText('Updating conditions…')).toBeInTheDocument()
  })

  it('accepts a custom label override', () => {
    render(<UpdateChip label="Checking current conditions…" />)
    expect(screen.getByText('Checking current conditions…')).toBeInTheDocument()
  })

  it('announces itself to assistive tech as a polite status region', () => {
    const { container } = render(<UpdateChip />)
    expect(container.querySelector('[role="status"]')).toBeInTheDocument()
  })

  it('hides the decorative pulse dot from assistive tech', () => {
    const { container } = render(<UpdateChip />)
    expect(container.querySelector(`.${styles.dot}`)).toHaveAttribute('aria-hidden', 'true')
  })

  it('pulses by default (no reduced-motion preference)', () => {
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: false }))
    const { container } = render(<UpdateChip />)
    expect(container.querySelector(`.${styles.dotPulse}`)).toBeInTheDocument()
  })

  it('drops the pulse animation class entirely under prefers-reduced-motion', () => {
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: true }))
    const { container } = render(<UpdateChip />)
    expect(container.querySelector(`.${styles.dotPulse}`)).not.toBeInTheDocument()
    // The static dot (and the label) still render — only the motion is dropped.
    expect(container.querySelector(`.${styles.dot}`)).toBeInTheDocument()
    expect(screen.getByText('Updating conditions…')).toBeInTheDocument()
  })

  it('does not error when matchMedia is unavailable (defensive default)', () => {
    vi.stubGlobal('matchMedia', undefined)
    const { container } = render(<UpdateChip />)
    expect(container.querySelector('[role="status"]')).toBeInTheDocument()
  })

  it('forwards a className alongside the chip class', () => {
    const { container } = render(<UpdateChip className="placed" />)
    expect(container.querySelector('[role="status"]')?.className).toContain('placed')
  })
})
