import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { summarizeProfile } from '../../data/geo'
import { ElevationGlyph } from './ElevationGlyph'

const profile = summarizeProfile(
  [
    { distanceMeters: 0, elevationMeters: 1000 },
    { distanceMeters: 500, elevationMeters: 1100 },
    { distanceMeters: 1000, elevationMeters: 1250 },
  ],
  'USGS 3DEP (sample)',
  10,
)

describe('ElevationGlyph (S4)', () => {
  it('renders a decorative sparkline polyline from the profile', () => {
    const { container } = render(<ElevationGlyph profile={profile} />)
    const svg = container.querySelector('svg.glyph')
    expect(svg).toBeInTheDocument()
    expect(svg).toHaveAttribute('aria-hidden', 'true')
    const polyline = container.querySelector('polyline.glyph-line')
    expect(polyline).toBeInTheDocument()
    // Three samples → three "x,y" point pairs.
    expect(polyline?.getAttribute('points')?.trim().split(/\s+/)).toHaveLength(3)
  })

  it('renders nothing for an empty profile rather than a faked curve (AC-4.2)', () => {
    const empty = summarizeProfile([], 'USGS 3DEP (sample)', 10)
    const { container } = render(<ElevationGlyph profile={empty} />)
    expect(container.querySelector('svg.glyph')).not.toBeInTheDocument()
  })
})
