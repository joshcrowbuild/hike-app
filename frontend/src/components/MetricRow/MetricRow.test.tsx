import { render, screen } from '@testing-library/react'
import { Mountain, Route } from 'lucide-react'
import { describe, expect, it } from 'vitest'

import { MetricRow } from './MetricRow'
import type { MetricItem } from './MetricRow'

describe('MetricRow', () => {
  it('renders nothing for an empty item list', () => {
    const { container } = render(<MetricRow items={[]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders each item label + value', () => {
    const items: MetricItem[] = [
      { kind: 'distance', label: 'Distance', value: '3.2 mi', glyph: Route },
      { kind: 'ascent', label: 'Ascent', value: '1,400 ft', glyph: Mountain },
    ]
    render(<MetricRow items={items} />)
    expect(screen.getByText('3.2 mi')).toBeInTheDocument()
    expect(screen.getByText('1,400 ft')).toBeInTheDocument()
    // "Distance" appears twice: once sr-only (via <Icon>'s required label)
    // and once as the aria-hidden visible echo — see the dedicated
    // double-announcing tests below for the accessible-tree assertions.
    expect(screen.getAllByText('Distance')).toHaveLength(2)
  })

  it.each([
    ['distance', 'distance unavailable'],
    ['ascent', 'ascent unavailable'],
    ['duration', 'time unavailable'],
  ] as const)('renders a NAMED disclosure for a missing %s value, never a bare dash', (kind, expected) => {
    render(<MetricRow items={[{ kind, label: kind, value: null }]} />)
    expect(screen.getByText(expected)).toBeInTheDocument()
    expect(screen.queryByText('—')).not.toBeInTheDocument()
  })

  it('treats an empty-string value the same as a missing one', () => {
    render(<MetricRow items={[{ kind: 'duration', label: 'Duration', value: '' }]} />)
    expect(screen.getByText('time unavailable')).toBeInTheDocument()
  })

  it('renders as an accessible list of facts', () => {
    render(<MetricRow items={[{ kind: 'distance', label: 'Distance', value: '3.2 mi' }]} />)
    expect(screen.getByRole('list')).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(1)
  })

  it('hides the visible label from assistive tech when a glyph already carries it, to avoid double-announcing', () => {
    render(<MetricRow items={[{ kind: 'distance', label: 'Distance', value: '3.2 mi', glyph: Route }]} />)
    const labels = screen.getAllByText('Distance')
    const hiddenCopies = labels.filter((el) => el.getAttribute('aria-hidden') === 'true')
    // One is the aria-hidden visible echo; the other is <Icon>'s sr-only label.
    expect(hiddenCopies).toHaveLength(1)
  })

  it('keeps the visible label announced when there is no glyph', () => {
    render(<MetricRow items={[{ kind: 'distance', label: 'Distance', value: '3.2 mi' }]} />)
    const visibleLabel = screen.getByText('Distance')
    expect(visibleLabel).not.toHaveAttribute('aria-hidden')
  })

  it('forwards a className onto the row', () => {
    render(<MetricRow items={[{ kind: 'distance', label: 'Distance', value: '3.2 mi' }]} className="placed" />)
    expect(screen.getByRole('list').className).toContain('placed')
  })
})
