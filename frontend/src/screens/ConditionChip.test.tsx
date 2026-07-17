import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { ConditionChipModel } from '../design/contracts'
import * as styles from './ConditionChip.css'
import { ConditionChip } from './ConditionChip'

const model = (over: Partial<ConditionChipModel> = {}): ConditionChipModel => ({
  kind: 'weather',
  valueText: '68°F',
  state: 'fresh',
  tier: 'clear',
  ...over,
})

describe('ConditionChip — states', () => {
  it('renders a fresh value with its kind label for assistive tech', () => {
    render(<ConditionChip model={model({ kind: 'air', valueText: 'AQI 54' })} />)
    expect(screen.getByText('AQI 54')).toBeInTheDocument()
    // The kind rides an sr-only label (Icon), so "Air quality" is announced.
    expect(screen.getByText('Air quality')).toBeInTheDocument()
  })

  it('shows a stale chip with its gray age', () => {
    const { container } = render(<ConditionChip model={model({ state: 'stale', valueText: 'AQI 54', ageText: '3h' })} />)
    expect(screen.getByText('3h')).toBeInTheDocument()
    expect(container.querySelector('span')?.className).toContain(styles.state.stale)
  })

  it('renders an unavailable chip as a dashed "—", never a guessed value', () => {
    const { container } = render(<ConditionChip model={model({ state: 'unavailable', valueText: '—' })} />)
    expect(screen.getByText('—')).toBeInTheDocument()
    expect(container.querySelector('span')?.className).toContain(styles.state.unavailable)
  })

  it('renders a pending chip as a shimmer placeholder with no value text', () => {
    const { container } = render(<ConditionChip model={model({ state: 'pending', valueText: '' })} />)
    expect(container.querySelector('span')?.className).toContain(styles.state.pending)
    expect(screen.getByText(/checking/)).toBeInTheDocument()
  })
})

describe('ConditionChip — warning tint (Q5/Q7)', () => {
  it('tints amber for a headsUp kind', () => {
    const { container } = render(<ConditionChip model={model({ tier: 'headsUp' })} />)
    expect(container.querySelector('span')?.className).toContain(styles.tint.headsUp)
  })

  it('tints terracotta for a blocked kind', () => {
    const { container } = render(<ConditionChip model={model({ valueText: 'closed', tier: 'blocked', kind: 'closures' })} />)
    expect(container.querySelector('span')?.className).toContain(styles.tint.blocked)
  })

  it('stays neutral for clear / unknown (no alarm colour, Law 7)', () => {
    const { container } = render(<ConditionChip model={model({ tier: 'unknown' })} />)
    const cls = container.querySelector('span')?.className ?? ''
    expect(cls).not.toContain(styles.tint.headsUp)
    expect(cls).not.toContain(styles.tint.blocked)
  })
})

describe('ConditionChip — interactive (Detail receipt disclosure)', () => {
  it('renders a button with aria-expanded and calls onToggle on tap', async () => {
    const user = userEvent.setup()
    const onToggle = vi.fn()
    render(
      <ConditionChip
        model={model({ receipt: { source: 'AirNow' } })}
        interactive
        isOpen={false}
        onToggle={onToggle}
        receiptRegionId="r"
      />,
    )
    const btn = screen.getByRole('button')
    expect(btn).toHaveAttribute('aria-expanded', 'false')
    expect(btn).toHaveAttribute('aria-controls', 'r')
    await user.click(btn)
    expect(onToggle).toHaveBeenCalledTimes(1)
  })

  it('reflects the open state via aria-expanded', () => {
    render(<ConditionChip model={model({ receipt: { source: 'AirNow' } })} interactive isOpen onToggle={vi.fn()} />)
    expect(screen.getByRole('button')).toHaveAttribute('aria-expanded', 'true')
  })

  it('is a non-interactive span when not interactive (the This-feed strip is read-only)', () => {
    render(<ConditionChip model={model()} />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
