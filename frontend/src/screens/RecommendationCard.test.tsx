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

describe('RecommendationCard verified hazard warnings (2026-07-01: show, never hide)', () => {
  const warning = {
    text: 'weather alert: Extreme Heat Warning',
    source: 'NWS api.weather.gov',
    observedAgo: '2h ago',
    kind: 'weather',
    provenance: 'live' as const,
  }

  it('wears a prominent warning with its text, source and age', () => {
    const { container } = render(
      <RecommendationCard card={card({ warnings: [warning] })} onOpen={vi.fn()} />,
    )
    const block = container.querySelector('.card-warnings')
    expect(block).toBeInTheDocument()
    expect(block?.textContent).toContain('weather alert: Extreme Heat Warning')
    expect(block?.textContent).toContain('NWS api.weather.gov') // source-stamped …
    expect(block?.textContent).toContain('2h ago') // … and aged (§7.2)
    // Assistive tech gets the same "Warning" framing sighted users read from the
    // accent treatment — colour is never the only cue.
    expect(screen.getByText('Warning:')).toBeInTheDocument()
  })

  it('renders no warning block on a clean card', () => {
    const { container } = render(<RecommendationCard card={card()} onOpen={vi.fn()} />)
    expect(container.querySelector('.card-warnings')).not.toBeInTheDocument()
  })
})

describe('RecommendationCard silence states (Epic 018 S4, CDP-02)', () => {
  const silence = (over: Partial<CardVM> = {}) =>
    render(<RecommendationCard card={card({ conditionLines: [], enrichment: undefined, ...over })} onOpen={vi.fn()} />)

  it('renders the honest not-fetched state instead of a blank card (AC-4.2)', () => {
    const { container } = silence()
    // The old `return null` produced nothing; now a legible silence shows.
    expect(container.querySelector('.condition-silence--not-fetched')).toBeInTheDocument()
    expect(screen.getByText(/conditions not checked/i)).toBeInTheDocument()
  })

  it('renders four visibly distinct silence states — never the same gray (AC-4.2)', () => {
    const states = ['not-fetched', 'checked-clear', 'no-data', 'stale-degraded'] as const
    const glyphs = new Set<string>()
    const classes = new Set<string>()
    for (const state of states) {
      const { container, unmount } = silence({ conditionSilence: { state } })
      const el = container.querySelector('.condition-silence')
      expect(el, state).toBeInTheDocument()
      expect(el?.className, state).toContain(`condition-silence--${state}`)
      classes.add(el!.className)
      glyphs.add(container.querySelector('.condition-silence-glyph')!.textContent ?? '')
      unmount()
    }
    // Four distinct treatments and four distinct glyphs: no two states collide.
    expect(classes.size).toBe(4)
    expect(glyphs.size).toBe(4)
  })

  it('discloses stale age through the Staleness primitive (AC-4.2)', () => {
    silence({ conditionSilence: { state: 'stale-degraded', detail: '4h ago' } })
    expect(screen.getByText(/last known conditions/i)).toBeInTheDocument()
    expect(screen.getByText('4h ago')).toBeInTheDocument()
  })

  it('shows present lines AND a residual silence so the set is not implied exhaustive (AC-4.3)', () => {
    const { container } = render(
      <RecommendationCard
        card={card({
          enrichment: undefined,
          conditionLines: [{ text: '54°F · clear (NWS, 12m ago)', source: 'NWS', confidence: 'stated', provenance: 'live' }],
          conditionSilence: { state: 'no-data', detail: 'streamflow, air' },
        })}
        onOpen={vi.fn()}
      />,
    )
    expect(container.querySelector('.condition-line')).toBeInTheDocument()
    const note = container.querySelector('.condition-silence--partial')
    expect(note).toBeInTheDocument()
    expect(note?.textContent).toMatch(/other conditions/i)
    expect(note?.textContent).toMatch(/streamflow, air/)
  })
})
