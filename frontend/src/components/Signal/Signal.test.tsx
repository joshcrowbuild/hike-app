import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Signal } from './Signal'

describe('Signal', () => {
  it('renders the caution message', () => {
    render(<Signal>Verify creek crossings — running high.</Signal>)
    expect(screen.getByText(/verify creek crossings/i)).toBeInTheDocument()
  })

  it('prefixes a verify cue for assistive tech, beyond the accent colour', () => {
    // The accent treatment is visual-only; AT must still hear the caution
    // framing (design-system-v0.1 §4.3 — colour is never the only cue).
    const { container } = render(<Signal>Closure info here is older than usual.</Signal>)
    expect(container.querySelector('p')?.textContent).toBe(
      'Caution: Closure info here is older than usual.',
    )
  })

  it('accepts a custom lead-in label', () => {
    const { container } = render(<Signal label="Verify before you go">Trail may be icy.</Signal>)
    expect(container.querySelector('p')?.textContent).toBe('Verify before you go: Trail may be icy.')
  })

  it('forwards a className for consumer-controlled placement', () => {
    const { container } = render(<Signal className="placed">x</Signal>)
    expect(container.querySelector('p')?.className).toContain('placed')
  })
})
