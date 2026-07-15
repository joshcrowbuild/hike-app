import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Staleness } from './Staleness'

describe('Staleness', () => {
  it('renders the caller-supplied relative-time string', () => {
    render(<Staleness>48m old</Staleness>)
    expect(screen.getByText('48m old')).toBeInTheDocument()
  })

  it('applies a distinct treatment when stale (demote, never reorder)', () => {
    const { rerender } = render(<Staleness>2h old</Staleness>)
    const fresh = screen.getByText('2h old').className
    rerender(<Staleness stale>2 days ago</Staleness>)
    const stale = screen.getByText('2 days ago').className
    expect(stale).not.toEqual(fresh)
  })

  it('renders nothing for a missing or blank age, never an empty tag standing in for a stamp (Epic 046 S4 AC-4.2)', () => {
    const { container: undef } = render(<Staleness>{undefined}</Staleness>)
    expect(undef).toBeEmptyDOMElement()
    const { container: blank } = render(<Staleness>{''}</Staleness>)
    expect(blank).toBeEmptyDOMElement()
  })
})
