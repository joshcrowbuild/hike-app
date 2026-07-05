import { render, screen } from '@testing-library/react'
import { Car } from 'lucide-react'
import { describe, expect, it } from 'vitest'

import { Icon } from './Icon'

describe('Icon', () => {
  it('renders the glyph as aria-hidden decoration, never a naked icon in the a11y tree', () => {
    const { container } = render(<Icon glyph={Car} label="Drive" />)
    const svg = container.querySelector('svg')
    expect(svg).toBeInTheDocument()
    expect(svg).toHaveAttribute('aria-hidden', 'true')
    // Not keyboard/tab reachable — it's a decoration, not a control.
    expect(svg).toHaveAttribute('focusable', 'false')
  })

  it('exposes its meaning to assistive tech through the required sr-only label', () => {
    render(<Icon glyph={Car} label="Drive" />)
    expect(screen.getByText('Drive')).toBeInTheDocument()
  })

  it('strokes currentColor so it inherits the surrounding text token in either theme', () => {
    const { container } = render(<Icon glyph={Car} label="Drive" />)
    // Lucide binds stroke to currentColor; the wrapper adds no colour of its own,
    // so the accent follows whatever ink its context sets — light or dark.
    expect(container.querySelector('svg')).toHaveAttribute('stroke', 'currentColor')
  })

  it('accepts a positioning className without dropping the base wrapper class', () => {
    const { container } = render(<Icon glyph={Car} label="Drive" className="decision-icon" />)
    const wrapper = container.querySelector('span')
    expect(wrapper?.className).toContain('decision-icon')
    // The base wrapper class is still present alongside the consumer's class.
    expect(wrapper?.className.split(' ').length).toBeGreaterThan(1)
  })
})
