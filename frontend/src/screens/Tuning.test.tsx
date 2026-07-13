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
    // Accessible names carry the region ("Luray, Shenandoah") — the visual
    // group headers are divs and never reach the accessibility tree.
    expect(screen.getByRole('radio', { name: 'Luray, Shenandoah' })).toBeInTheDocument()
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
    expect(screen.getByRole('radio', { name: 'Front Royal, Shenandoah' })).toBeInTheDocument()
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

    await user.click(screen.getByRole('radio', { name: 'Luray, Shenandoah' }))
    expect(screen.queryByText(/use a named place instead/i)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /near me.*use current location/i })).toBeInTheDocument()
  })
})

describe('origin picker grouping + ordering (craft review C1/M4 — region-grouped, never 35 flat rows)', () => {
  // `role=radio` lands on react-aria-components' bare <input>, whose visible
  // label sits in a sibling node (no text content on the input itself) — its
  // `value` attribute is the origin key, so order is asserted against that.
  it('groups origins under region headers, catalog order, alphabetical within each region (no location)', async () => {
    render(<OriginPanel />)
    const keys = (await screen.findAllByRole('radio')).map((r) => r.getAttribute('value'))
    expect(keys).toEqual([
      // Shenandoah
      'charlottesville',
      'frontRoyal',
      'luray',
      // Richmond
      'richmond',
      // Outer Banks
      'duck',
      'hatteras',
      'nagsHead',
      'ocracoke',
    ])
    // The headers themselves, in catalog order.
    const headers = [...document.querySelectorAll('.origin-group-label')].map((el) => el.textContent)
    expect(headers).toEqual(['Shenandoah', 'Richmond', 'Outer Banks'])
  })

  it('re-ranks regions and their origins nearest-first the instant a live fix lands ("Near me")', async () => {
    // A fix right on top of Luray: Shenandoah leads (Luray → Front Royal →
    // Charlottesville by live haversine), then Richmond, then the Outer Banks
    // origins by their own distance from Luray — proof both grouping levels
    // re-rank on proximity, not a fixed list.
    const getCurrentPosition = vi.fn((ok) => ok({ coords: { latitude: 38.665, longitude: -78.459 } }))
    Object.defineProperty(navigator, 'geolocation', { value: { getCurrentPosition }, configurable: true })
    const user = userEvent.setup()
    render(<OriginPanel />)

    await screen.findAllByRole('radio')
    await user.click(screen.getByRole('button', { name: /near me.*use current location/i }))
    await screen.findByText(/use a named place instead/i)

    const keys = screen.getAllByRole('radio').map((r) => r.getAttribute('value'))
    expect(keys).toEqual([
      'luray',
      'frontRoyal',
      'charlottesville',
      'richmond',
      'duck',
      'nagsHead',
      'ocracoke',
      'hatteras',
    ])
    const headers = [...document.querySelectorAll('.origin-group-label')].map((el) => el.textContent)
    expect(headers).toEqual(['Shenandoah', 'Richmond', 'Outer Banks'])
  })

  it('keeps the whole grouped list inside one radiogroup — a single choice, not per-region choices', async () => {
    render(<OriginPanel />)
    await screen.findAllByRole('radio')
    expect(screen.getAllByRole('radiogroup')).toHaveLength(1)
  })

  it('scrolls the SHEET BODY — never an ancestor chain — to reveal the selected origin on open (C1)', async () => {
    const scrolled: Element[] = []
    // jsdom implements no Element scrolling; install a scrollTo that records
    // its receiver. scrollIntoView is deliberately NOT shimmed: if the
    // implementation ever regresses to it (which can walk scrollable
    // ancestors past the modal and shift the feed behind it), this test's
    // assertion below goes unmet and fails.
    Object.defineProperty(HTMLElement.prototype, 'scrollTo', {
      value(this: Element) {
        scrolled.push(this)
      },
      configurable: true,
      writable: true,
    })
    try {
      render(<OriginPanel />)
      await screen.findAllByRole('radio')
      expect(scrolled.length).toBeGreaterThan(0)
      // The scrolled element is the Sheet's own internal scroll region — the
      // one element whose scrolling cannot leak into the page behind the modal
      // — and it contains the selected row it is revealing.
      expect(scrolled[0]).toHaveAttribute('data-sheet-body')
      expect(scrolled[0].querySelector('[data-selected]')?.textContent).toContain('Front Royal')
    } finally {
      // @ts-expect-error test-only cleanup of the jsdom shim
      delete HTMLElement.prototype.scrollTo
    }
  })
})
