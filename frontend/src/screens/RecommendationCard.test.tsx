import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { summarizeProfile } from '../data/geo'
import type { CardVM } from '../data/vm'
import { RecommendationCard } from './RecommendationCard'

function card(overrides: Partial<CardVM> = {}): CardVM {
  return {
    id: 'stony-man',
    name: 'Stony Man Loop',
    distanceMi: null,
    conditionLines: [{ text: '54°F · clear', source: 'NWS', confidence: 'stated', provenance: 'mock' }],
    warnings: [],
    enrichment: {
      area: 'Shenandoah',
      distanceMiles: 3.7,
      ascentFeet: 1050,
      driveMinutes: 28,
      provenance: 'mock',
    },
    geo: {
      geometry: { type: 'LineString', coordinates: [[-78.4, 38.5], [-78.39, 38.51]] },
      trailhead: { lat: 38.5, lon: -78.4 },
      quality: 'confident',
      elevationProfile: summarizeProfile(
        [
          { distanceMeters: 0, elevationMeters: 1000 },
          { distanceMeters: 500, elevationMeters: 1200 },
        ],
        'USGS 3DEP (sample)',
        10,
      ),
    },
    ...overrides,
  }
}

describe('RecommendationCard feed glyph (S4)', () => {
  it('shows the static elevation glyph when a profile exists', () => {
    const { container } = render(<RecommendationCard card={card()} onOpen={vi.fn()} />)
    expect(container.querySelector('svg.glyph')).toBeInTheDocument()
  })

  it('degrades to the ascent figure with no glyph when there is no profile (AC-4.2)', () => {
    const { container } = render(<RecommendationCard card={card({ geo: undefined })} onOpen={vi.fn()} />)
    expect(container.querySelector('svg.glyph')).not.toBeInTheDocument()
    // The ascent figure still reads the shape of the day in text.
    expect(screen.getByText(/1,050 ft/)).toBeInTheDocument()
  })

  it('opens Detail on tap, with no in-card map (AC-4.3)', async () => {
    const onOpen = vi.fn()
    const user = userEvent.setup()
    render(<RecommendationCard card={card()} onOpen={onOpen} />)
    await user.click(screen.getByRole('button', { name: /open stony man loop/i }))
    expect(onOpen).toHaveBeenCalledTimes(1)
  })
})
