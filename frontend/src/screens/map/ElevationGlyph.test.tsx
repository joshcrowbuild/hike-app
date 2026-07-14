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

  it('scales relief against a shared reference across cards — 13 ft of dune draws visibly flatter than 278 ft of ridge (H3, ux-review-craft 2026-07)', () => {
    const dune = summarizeProfile(
      [
        { distanceMeters: 0, elevationMeters: 10 },
        { distanceMeters: 500, elevationMeters: 13.96 }, // ~13 ft relief
      ],
      'USGS 3DEP (sample)',
      10,
    )
    const ridge = summarizeProfile(
      [
        { distanceMeters: 0, elevationMeters: 300 },
        { distanceMeters: 500, elevationMeters: 384.74 }, // ~278 ft relief
      ],
      'USGS 3DEP (sample)',
      10,
    )
    const verticalRange = (container: HTMLElement): number => {
      const ys = container
        .querySelector('polyline.glyph-line')!
        .getAttribute('points')!
        .trim()
        .split(/\s+/)
        .map((pair) => Number(pair.split(',')[1]))
      return Math.max(...ys) - Math.min(...ys)
    }
    const { container: duneContainer } = render(<ElevationGlyph profile={dune} />)
    const { container: ridgeContainer } = render(<ElevationGlyph profile={ridge} />)
    // Before H3's fix both profiles auto-ranged to their OWN min/max and so
    // occupied the identical full-frame vertical span, regardless of relief —
    // that's the exact bug: this asserts the ridge now draws visibly taller.
    expect(verticalRange(ridgeContainer)).toBeGreaterThan(verticalRange(duneContainer))
  })
})
