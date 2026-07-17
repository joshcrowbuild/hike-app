import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { CardVM } from '../data/vm'
import { DetailConditions } from './DetailConditions'

function card(over: Partial<CardVM> = {}): CardVM {
  return {
    id: 'old-rag',
    name: 'Old Rag',
    distanceMi: null,
    conditionLines: [
      { text: '73°F · partly cloudy', source: 'NWS', confidence: 'stated', provenance: 'live' },
      { text: 'AQI 54 · good', source: 'AirNow', confidence: 'stated', provenance: 'live' },
    ],
    conditions: [
      { kind: 'weather', state: 'present', source: 'NWS', checkedAgo: '2m ago' },
      { kind: 'air', state: 'present', source: 'AirNow', checkedAgo: '2m ago' },
      { kind: 'closures', state: 'present', source: 'NPS', checkedAgo: '1h ago' },
      { kind: 'water', state: 'unavailable' },
    ],
    warnings: [{ text: 'Ridge closed', source: 'NPS', kind: 'closures', provenance: 'live', severity: 'blocked' }],
    ...over,
  }
}

describe('DetailConditions — the per-kind strip', () => {
  it('renders the "Current conditions" strip of this trail’s chips', () => {
    render(<DetailConditions card={card()} />)
    expect(screen.getByText('Current conditions')).toBeInTheDocument()
    expect(screen.getByText('73°F')).toBeInTheDocument()
    expect(screen.getByText('AQI 54')).toBeInTheDocument()
  })

  it('renders nothing when the card has no conditions and no lines (silence is a state)', () => {
    const { container } = render(<DetailConditions card={card({ conditions: [], conditionLines: [] })} />)
    expect(container.firstChild).toBeNull()
  })
})

describe('DetailConditions — tap-to-reveal receipt (Q6)', () => {
  it('is collapsed by default: no receipt line until a chip is tapped', () => {
    render(<DetailConditions card={card()} />)
    expect(screen.queryByText(/single source/)).not.toBeInTheDocument()
  })

  it('reveals ONE receipt line below the strip on tap (source · age · confidence)', async () => {
    const user = userEvent.setup()
    render(<DetailConditions card={card()} />)
    await user.click(screen.getByRole('button', { name: /Weather/ }))
    // The single receipt line for the tapped kind.
    expect(screen.getByText(/NWS · 2m ago · single source/)).toBeInTheDocument()
  })

  it('swaps the receipt to the newly-tapped chip', async () => {
    const user = userEvent.setup()
    render(<DetailConditions card={card()} />)
    await user.click(screen.getByRole('button', { name: /Weather/ }))
    expect(screen.getByText(/NWS · 2m ago/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Air quality/ }))
    expect(screen.getByText(/AirNow · 2m ago/)).toBeInTheDocument()
    // Only one receipt line is ever shown — the previous one is gone.
    expect(screen.queryByText(/NWS · 2m ago/)).not.toBeInTheDocument()
  })

  it('closes the receipt when the open chip is tapped again', async () => {
    const user = userEvent.setup()
    render(<DetailConditions card={card()} />)
    const weather = screen.getByRole('button', { name: /Weather/ })
    await user.click(weather)
    expect(screen.getByText(/NWS · 2m ago/)).toBeInTheDocument()
    await user.click(weather)
    expect(screen.queryByText(/NWS · 2m ago/)).not.toBeInTheDocument()
    expect(weather).toHaveAttribute('aria-expanded', 'false')
  })

  it('leaves an unavailable chip inert — there is no source to disclose', () => {
    render(<DetailConditions card={card()} />)
    // The four buttons are the sourced kinds; the unavailable water chip is a span.
    const buttons = screen.getAllByRole('button')
    expect(buttons).toHaveLength(3) // weather, air, closures — not the unavailable water probe
  })
})
