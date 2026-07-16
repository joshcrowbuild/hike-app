import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { emptyFilters, emptySearch } from '../../copy/messages'
import { EmptyState } from './EmptyState'

describe('EmptyState', () => {
  it('renders the headline, secondary, and CTA text', () => {
    render(
      <EmptyState
        headline="No trails named &quot;old rug&quot; near here."
        secondary="Check the spelling, or browse the 10 picks for St. John."
        cta="Clear search & browse"
        onAction={() => {}}
      />,
    )
    expect(screen.getByText(/no trails named/i)).toBeInTheDocument()
    expect(screen.getByText(/check the spelling/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Clear search & browse' })).toBeInTheDocument()
  })

  it('fires onAction when the CTA is pressed', async () => {
    const onAction = vi.fn()
    render(<EmptyState headline="h" secondary="s" cta="Reset" onAction={onAction} />)
    await userEvent.click(screen.getByRole('button', { name: 'Reset' }))
    expect(onAction).toHaveBeenCalledTimes(1)
  })

  it('is keyboard-activatable (Enter) via the shared Button primitive', async () => {
    const onAction = vi.fn()
    render(<EmptyState headline="h" secondary="s" cta="Reset" onAction={onAction} />)
    const btn = screen.getByRole('button', { name: 'Reset' })
    btn.focus()
    await userEvent.keyboard('{Enter}')
    expect(onAction).toHaveBeenCalledTimes(1)
  })

  it('announces itself to assistive tech as a status region', () => {
    const { container } = render(<EmptyState headline="h" secondary="s" cta="Reset" onAction={() => {}} />)
    expect(container.querySelector('[role="status"]')).toBeInTheDocument()
  })

  it('forwards a className alongside the container class', () => {
    const { container } = render(
      <EmptyState headline="h" secondary="s" cta="Reset" onAction={() => {}} className="placed" />,
    )
    expect(container.querySelector('[role="status"]')?.className).toContain('placed')
  })

  it('renders the search-no-match copy produced by messages.emptySearch verbatim', () => {
    const copy = emptySearch('old rug', 'St. John', 10)
    render(<EmptyState {...copy} onAction={() => {}} />)
    expect(screen.getByText(copy.headline)).toBeInTheDocument()
    expect(screen.getByText(copy.secondary)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: copy.cta })).toBeInTheDocument()
  })

  it('renders the filters-too-tight copy produced by messages.emptyFilters verbatim, with the CTA reading a value, not the sentence verb phrase', () => {
    const copy = emptyFilters('a solo dawn hike under 1 mile', 'St. John', 'Widen the distance', 6, 'up to 3 mi')
    render(<EmptyState {...copy} onAction={() => {}} />)
    expect(screen.getByText('Nothing matches a solo dawn hike under 1 mile here.')).toBeInTheDocument()
    expect(screen.getByText('Widen the distance and 6 trails come back.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Show trails up to 3 mi' })).toBeInTheDocument()
  })
})
