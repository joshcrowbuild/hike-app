import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { summarizeProfile } from '../data/geo'
import { resetSavedTrailsForTests } from '../data/savedTrails'
import type { CardVM } from '../data/vm'
import { RecommendationCard } from './RecommendationCard'

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

describe('RecommendationCard feed glyph (S4)', () => {
  it('shows the static elevation glyph when a profile exists', () => {
    const { container } = render(<RecommendationCard card={card()} onOpen={vi.fn()} />)
    expect(container.querySelector('svg.glyph')).toBeInTheDocument()
  })

  it('degrades to the ascent figure with no glyph when there is no profile (AC-4.2)', () => {
    const { container } = render(<RecommendationCard card={card({ geo: undefined })} onOpen={vi.fn()} />)
    expect(container.querySelector('svg.glyph')).not.toBeInTheDocument()
    // The ascent figure still reads the shape of the day in the decision row.
    // (The derived summary also names the climb in prose, hence scope to the stat.)
    const stats = [...container.querySelectorAll('.decision-value')].map((el) => el.textContent ?? '')
    expect(stats.some((t) => /1,050 ft/.test(t))).toBe(true)
  })

  it('opens Detail on tap, with no in-card map (AC-4.3)', async () => {
    const onOpen = vi.fn()
    const user = userEvent.setup()
    render(<RecommendationCard card={card()} onOpen={onOpen} />)
    await user.click(screen.getByRole('button', { name: /open stony man loop/i }))
    expect(onOpen).toHaveBeenCalledTimes(1)
  })
})

describe('RecommendationCard derived summary + difficulty (2026-07-03)', () => {
  it('renders the derived one-line character in the card', () => {
    const { container } = render(<RecommendationCard card={card()} onOpen={vi.fn()} />)
    // The card's open geometry reads as out-and-back, so the stated mileage is
    // the ROUND TRIP (2 × the curated 3.7 mi one-way figure) — what the hiker
    // actually walks (Josh, 2026-07-03).
    expect(container.querySelector('.trail-summary')?.textContent).toMatch(/7\.4-mile out-and-back, climbing 1,050 ft\./)
  })

  it('renders the difficulty estimate, tagged as an estimate (never a rank)', () => {
    const { container } = render(<RecommendationCard card={card()} onOpen={vi.fn()} />)
    const badge = container.querySelector('.difficulty')
    // Banded off the round-trip 7.4 mi (not the one-way 3.7 mi), so this reads
    // Strenuous rather than Moderate.
    expect(badge?.textContent).toMatch(/Strenuous/)
    expect(badge?.textContent).toMatch(/est\./)
    // Sample data wears the sample tag, mirroring <Confidence>.
    expect(container.querySelector('.difficulty--sample')).toBeInTheDocument()
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

  it('wears a prominent warning with its source and age, collapsed under the verdict headline that already speaks it', () => {
    const { container } = render(
      <RecommendationCard card={card({ warnings: [warning] })} onOpen={vi.fn()} />,
    )
    // The verdict headline above already says the hazard sentence — the block
    // below collapses to source + age so it isn't repeated verbatim twice.
    expect(container.textContent).toContain('weather alert: Extreme Heat Warning')
    const block = container.querySelector('.card-warnings')
    expect(block).toBeInTheDocument()
    expect(block?.textContent).not.toContain('weather alert: Extreme Heat Warning')
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

describe('RecommendationCard accessible name carries the warning state (report #4/#7)', () => {
  const warning = {
    text: 'weather alert: Extreme Heat Warning',
    source: 'NWS api.weather.gov',
    observedAgo: '2h ago',
    kind: 'weather',
    provenance: 'live' as const,
  }

  it('names just the trail when there is nothing to warn about', () => {
    render(<RecommendationCard card={card()} onOpen={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Open Stony Man Loop' })).toBeInTheDocument()
  })

  it('folds the warning into the accessible name so it is never swallowed by aria-label', () => {
    render(<RecommendationCard card={card({ warnings: [warning] })} onOpen={vi.fn()} />)
    // A plain `aria-label="Open {name}"` would hide this from assistive tech
    // entirely, even though the warning renders visibly inside the button.
    expect(
      screen.getByRole('button', { name: /open stony man loop.*extreme heat warning/i }),
    ).toBeInTheDocument()
  })
})

describe('RecommendationCard ascent renders from the live elevation profile when enrichment has none (report #2)', () => {
  it('shows an Ascent figure from the geo profile total gain, null-safe when absent', () => {
    render(
      <RecommendationCard
        card={card({
          enrichment: undefined,
          distanceMi: 3.2,
        })}
        onOpen={vi.fn()}
      />,
    )
    // The fixture's profile climbs from 1000m to 1200m — 200m ≈ 656 ft.
    expect(screen.getByText('656 ft')).toBeInTheDocument()
    expect(screen.getByText('Ascent')).toBeInTheDocument()
  })

  it('renders no Ascent figure when there is no elevation profile at all', () => {
    render(<RecommendationCard card={card({ enrichment: undefined, geo: undefined })} onOpen={vi.fn()} />)
    expect(screen.queryByText('Ascent')).not.toBeInTheDocument()
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

describe('RecommendationCard Directions (surfaced prominently, outside the tap target)', () => {
  it('renders a Directions link to the trailhead when the card has geo', () => {
    render(<RecommendationCard card={card()} onOpen={vi.fn()} />)
    const link = screen.getByRole('link', { name: /directions/i })
    expect(link).toHaveAttribute('href', expect.stringContaining('google.com/maps/dir/'))
    expect(link).toHaveAttribute('href', expect.stringContaining('travelmode=driving'))
    expect(link.getAttribute('href')).toContain(encodeURIComponent('38.5,-78.4'))
    expect(link).toHaveAttribute('target', '_blank')
  })

  it('renders no Directions link when the card has no geo/trailhead', () => {
    render(<RecommendationCard card={card({ geo: undefined })} onOpen={vi.fn()} />)
    expect(screen.queryByRole('link', { name: /directions/i })).not.toBeInTheDocument()
  })

  it('lives outside the card-tap button so it never doubles as the open-detail target', () => {
    const { container } = render(<RecommendationCard card={card()} onOpen={vi.fn()} />)
    const button = container.querySelector('.card-tap')
    const link = screen.getByRole('link', { name: /directions/i })
    expect(button?.contains(link)).toBe(false)
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
    expect(screen.getByText('Saved')).toBeInTheDocument()
  })

  it('toggles back to unsaved on a second tap', async () => {
    const user = userEvent.setup()
    render(<RecommendationCard card={card()} onOpen={vi.fn()} />)
    const save = screen.getByRole('button', { name: /save stony man loop/i })
    await user.click(save)
    await user.click(screen.getByRole('button', { name: /remove stony man loop from saved/i }))
    expect(screen.getByRole('button', { name: /^save stony man loop$/i })).toHaveAttribute('aria-pressed', 'false')
  })

  it('persists the saved state across a remount (localStorage, not component state)', async () => {
    const user = userEvent.setup()
    const { unmount } = render(<RecommendationCard card={card()} onOpen={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: /save stony man loop/i }))
    unmount()

    render(<RecommendationCard card={card()} onOpen={vi.fn()} />)
    expect(screen.getByRole('button', { name: /remove stony man loop from saved/i })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
  })

  it('lives outside the card-tap button so Save never opens Detail', () => {
    const { container } = render(<RecommendationCard card={card()} onOpen={vi.fn()} />)
    const button = container.querySelector('.card-tap')
    const save = screen.getByRole('button', { name: /save stony man loop/i })
    expect(button?.contains(save)).toBe(false)
  })
})
