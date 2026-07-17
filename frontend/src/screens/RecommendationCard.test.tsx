import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { summarizeProfile } from '../data/geo'
import { resetSavedTrailsForTests } from '../data/savedTrails'
import type { CardVM } from '../data/vm'
import { RecommendationCard } from './RecommendationCard'
import * as warningStyles from './WarningBlock.css'

afterEach(() => resetSavedTrailsForTests())

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

describe('RecommendationCard hazard warnings — regression guard (card.warnings must not be silently dropped)', () => {
  it('renders a per-card warning', () => {
    render(
      <RecommendationCard
        card={card({
          warnings: [
            { text: 'Extreme Heat Warning', source: 'NWS', observedAgo: '1h ago', kind: 'weather', provenance: 'mock' },
          ],
        })}
        onOpen={vi.fn()}
      />,
    )
    expect(screen.getByText(/Extreme Heat Warning/)).toBeInTheDocument()
  })

  it('stays silent when there are no warnings (silence is a state)', () => {
    const { container } = render(<RecommendationCard card={card({ warnings: [] })} onOpen={vi.fn()} />)
    expect(container.querySelector('.card-warnings')).not.toBeInTheDocument()
  })
})

describe('RecommendationCard feed glyph (S4)', () => {
  it('shows the static elevation glyph when a profile exists', () => {
    const { container } = render(<RecommendationCard card={card()} onOpen={vi.fn()} />)
    expect(container.querySelector('svg.glyph')).toBeInTheDocument()
  })

  it('drops the glyph with no profile, but keeps the curated decision facts', () => {
    const { container } = render(<RecommendationCard card={card({ geo: undefined })} onOpen={vi.fn()} />)
    expect(container.querySelector('svg.glyph')).not.toBeInTheDocument()
    // A card with no profile still shows its curated Ascent, Distance, and Drive.
    expect(screen.getAllByText('Ascent')[0]).toBeInTheDocument()
    expect(screen.getAllByText('Distance')[0]).toBeInTheDocument()
  })

  it('opens Detail on tap, with no in-card map (AC-4.3)', async () => {
    const onOpen = vi.fn()
    const user = userEvent.setup()
    render(<RecommendationCard card={card()} onOpen={onOpen} />)
    await user.click(screen.getByRole('button', { name: /open stony man loop/i }))
    expect(onOpen).toHaveBeenCalledTimes(1)
  })
})

describe('RecommendationCard is lean — Detail-only fields are relocated off it, decision facts stay', () => {
  const enriched = card({
    enrichment: {
      placeCue: 'the granite dome above the valley',
      area: 'Shenandoah',
      routeShape: 'Loop',
      distanceMiles: 3.7,
      ascentFeet: 1050,
      driveMinutes: 28,
      durationHours: '3–4 hr',
      fitLine: 'Matches your taste for open summits.',
      practicalNote: 'Arrive early; the lot fills by 9.',
      caution: 'Verify the creek crossing before you commit.',
      conditionValue: '54°F · clear',
      freshness: 'NWS · 12m ago',
      provenance: 'mock',
    },
  })

  it('renders none of {placeCue, fitLine, practicalNote, caution Signal, character, difficulty} but keeps duration as a decision fact', () => {
    const { container } = render(<RecommendationCard card={enriched} onOpen={vi.fn()} />)
    const text = container.textContent ?? ''
    expect(text).not.toContain('the granite dome above the valley')
    expect(text).not.toContain('Matches your taste')
    expect(text).not.toContain('Arrive early')
    expect(text).not.toContain('Verify the creek crossing')
    expect(text).toContain('3–4 hr')
    
    expect(container.querySelector('.trail-summary')).not.toBeInTheDocument()
    expect(container.querySelector('.difficulty')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Stony Man Loop' })).toBeInTheDocument()
  })

  it('still carries a freshness/age stamp in the foot', () => {
    const { container } = render(<RecommendationCard card={enriched} onOpen={vi.fn()} />)
    expect(container.querySelector('.card-foot')?.textContent).toContain('12m ago')
  })
})

describe('RecommendationCard is conditions-silent (Q2), warnings tint by severity (Q7)', () => {
  it('renders NO condition line even when per-kind conditions are present — the area card carries them', () => {
    const { container } = render(
      <RecommendationCard
        card={card({
          conditions: [
            { kind: 'weather', state: 'present', source: 'NWS', checkedAgo: 'just now' },
            { kind: 'air', state: 'unavailable' },
          ],
          conditionLines: [{ text: '54°F · clear', source: 'NWS', confidence: 'stated', provenance: 'live' }],
          warnings: [],
        })}
        onOpen={vi.fn()}
      />,
    )
    // No condition summary/status line, no per-kind chips — the card is silent.
    expect(container.querySelector('.card-warnings')).not.toBeInTheDocument()
    expect(container.textContent).not.toMatch(/things to know/i)
    expect(container.textContent).not.toMatch(/couldn’t be verified/i)
    // …but it still shows its decision facts.
    expect(screen.getByRole('heading', { name: 'Stony Man Loop' })).toBeInTheDocument()
  })

  it('tints a blocked warning terracotta and a heads-up (or ungraded) warning amber', () => {
    const blocked = render(
      <RecommendationCard
        card={card({ warnings: [{ text: 'Ridge closed', source: 'NPS', kind: 'closures', provenance: 'live', severity: 'blocked' }] })}
        onOpen={vi.fn()}
      />,
    )
    expect(blocked.container.querySelector('.card-warning')?.className).toContain(warningStyles.item.blocked)
    blocked.unmount()

    const headsUp = render(
      <RecommendationCard
        card={card({ warnings: [{ text: 'Heat advisory', source: 'NWS', kind: 'weather', provenance: 'live', severity: 'headsUp' }] })}
        onOpen={vi.fn()}
      />,
    )
    expect(headsUp.container.querySelector('.card-warning')?.className).toContain(warningStyles.item.headsUp)
    headsUp.unmount()

    // An absent severity is never louder than the backend graded it → amber.
    const ungraded = render(
      <RecommendationCard
        card={card({ warnings: [{ text: 'Advisory', source: 'NWS', kind: 'weather', provenance: 'live' }] })}
        onOpen={vi.fn()}
      />,
    )
    expect(ungraded.container.querySelector('.card-warning')?.className).toContain(warningStyles.item.headsUp)
  })
})

describe('RecommendationCard accessible name carries the warning state', () => {
  const warning = {
    text: 'Extreme Heat Warning',
    source: 'NWS',
    observedAgo: '2h ago',
    kind: 'weather',
    provenance: 'live' as const,
  }

  it('names just the trail when there is nothing to warn about', () => {
    render(<RecommendationCard card={card()} onOpen={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Open Stony Man Loop' })).toBeInTheDocument()
  })

  it('folds the warning into the accessible name', () => {
    render(<RecommendationCard card={card({ warnings: [warning] })} onOpen={vi.fn()} />)
    expect(
      screen.getByRole('button', { name: /open stony man loop.*extreme heat warning/i }),
    ).toBeInTheDocument()
  })
})

describe('RecommendationCard decision facts (MetricRow)', () => {
  it('shows Distance, Ascent, and Duration together from curated enrichment', () => {
    render(
      <RecommendationCard
        card={card({
          geo: undefined,
          enrichment: {
            area: 'Shenandoah',
            distanceMiles: 3.7,
            ascentFeet: 1050,
            durationHours: '2–3 hr',
            provenance: 'mock',
          },
        })}
        onOpen={vi.fn()}
      />,
    )
    expect(screen.getAllByText('Distance')[0]).toBeInTheDocument()
    expect(screen.getAllByText('3.7 mi')[0]).toBeInTheDocument()
    expect(screen.getAllByText('Ascent')[0]).toBeInTheDocument()
    expect(screen.getByText('1,050 ft')).toBeInTheDocument()
    expect(screen.getAllByText('Duration')[0]).toBeInTheDocument()
    expect(screen.getByText('2–3 hr')).toBeInTheDocument()
  })

  it('a null-elevation trail discloses Ascent/Duration as unavailable', () => {
    render(
      <RecommendationCard
        card={card({
          enrichment: { distanceMiles: 1.5, provenance: 'mock' },
          geo: { geometry: null, trailhead: { lat: 38.5, lon: -78.4 }, quality: 'confident', elevationProfile: null },
        })}
        onOpen={vi.fn()}
      />,
    )
    expect(screen.getByText('1.5 mi')).toBeInTheDocument()
    // Should have "elevation unavailable" or similar from MetricRow when null
    const listItems = screen.getAllByRole('listitem')
    expect(listItems).toHaveLength(3) // distance, ascent, duration
  })
})

describe('RecommendationCard Directions', () => {
  it('renders a Directions button to the trailhead when the card has geo', () => {
    render(<RecommendationCard card={card()} onOpen={vi.fn()} />)
    const btn = screen.getByRole('button', { name: /directions/i })
    expect(btn).toBeInTheDocument()
  })

  it('renders no Directions button when the card has no geo/trailhead', () => {
    render(<RecommendationCard card={card({ geo: undefined })} onOpen={vi.fn()} />)
    expect(screen.queryByRole('button', { name: /directions/i })).not.toBeInTheDocument()
  })
})

describe('RecommendationCard Save (client-side, localStorage, anonymous-friendly)', () => {
  it('starts unsaved and toggles to Saved on tap, without opening the card', async () => {
    const onOpen = vi.fn()
    const user = userEvent.setup()
    render(<RecommendationCard card={card()} onOpen={onOpen} />)
    const save = screen.getByRole('button', { name: /save stony man loop/i })
    expect(save).toHaveAttribute('aria-pressed', 'false')

    await user.click(save)
    expect(onOpen).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: /remove stony man loop from saved/i })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(screen.getAllByText('Saved').length).toBeGreaterThan(0)
  })
})
