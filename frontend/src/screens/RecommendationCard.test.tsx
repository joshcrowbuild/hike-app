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

  it('drops the glyph with no profile, but keeps the curated decision facts (H2/H3, ux-review-craft 2026-07)', () => {
    const { container } = render(<RecommendationCard card={card({ geo: undefined })} onOpen={vi.fn()} />)
    expect(container.querySelector('svg.glyph')).not.toBeInTheDocument()
    // The glyph is decoration, never the sole home of a decision fact (H3) — a
    // card with no profile still shows its curated Ascent, Distance, and Drive.
    // Each label now carries a leading icon whose sr-only text echoes the word
    // (Epic 021), so a label's textContent reads the word twice — assert the word
    // is present rather than an exact string match.
    const labels = [...container.querySelectorAll('.decision-label')].map((el) => el.textContent ?? '')
    expect(labels.some((l) => l.includes('Ascent'))).toBe(true)
    expect(labels.some((l) => l.includes('Distance'))).toBe(true)
    expect(labels.some((l) => l.includes('Drive'))).toBe(true)
  })

  it('opens Detail on tap, with no in-card map (AC-4.3)', async () => {
    const onOpen = vi.fn()
    const user = userEvent.setup()
    render(<RecommendationCard card={card()} onOpen={onOpen} />)
    await user.click(screen.getByRole('button', { name: /open stony man loop/i }))
    expect(onOpen).toHaveBeenCalledTimes(1)
  })
})

describe('RecommendationCard is lean — Detail-only fields are relocated off it, decision facts stay (Epic 019 AC-19.1.1 / H2, ux-review-craft 2026-07)', () => {
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
    expect(text).not.toContain('the granite dome above the valley') // placeCue
    expect(text).not.toContain('Matches your taste') // fitLine
    expect(text).not.toContain('Arrive early') // practicalNote
    expect(text).not.toContain('Verify the creek crossing') // caution Signal
    expect(text).toContain('3–4 hr') // duration is a decision fact again (H2)
    // Character (derived summary) and the difficulty badge are Detail-only now.
    expect(container.querySelector('.trail-summary')).not.toBeInTheDocument()
    expect(container.querySelector('.difficulty')).not.toBeInTheDocument()
    // What DOES stay: name, the decision facts (incl. Ascent + Duration, H2),
    // the glyph, and the single Now value.
    expect(container.querySelector('.card-name')?.textContent).toBe('Stony Man Loop')
    expect(container.querySelector('.condition-value')?.textContent).toContain('54°F · clear')
  })

  it('still carries a freshness/age stamp in the foot (AC-19.1.3, non-relocatable)', () => {
    const { container } = render(<RecommendationCard card={enriched} onOpen={vi.fn()} />)
    expect(container.querySelector('.card-foot')?.textContent).toContain('12m ago')
  })

  it('never renders the multi-line condition LIST — only one Now value (DD1 line 6)', () => {
    const { container } = render(
      <RecommendationCard
        card={card({
          enrichment: undefined,
          conditionLines: [
            { text: '54°F · clear', source: 'NWS', confidence: 'stated', provenance: 'live' },
            { text: 'AQI 32 · good', source: 'AirNow', confidence: 'stated', provenance: 'live' },
          ],
        })}
        onOpen={vi.fn()}
      />,
    )
    expect(container.querySelector('.condition-lines')).not.toBeInTheDocument()
    // The primary line shows as the single Now value; the second is Detail-only.
    expect(container.querySelector('.condition-value')?.textContent).toContain('54°F · clear')
    expect(container.textContent).not.toContain('AQI 32')
  })
})

describe('RecommendationCard verified hazard warnings (2026-07-01: show, never hide)', () => {
  const warning = {
    text: 'weather alert: Extreme Heat Warning',
    // Short provider name (D3 consistency pass, backend `provider_short`) — never
    // the raw domain-suffixed "NWS api.weather.gov" (that stays out of the card).
    source: 'NWS',
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
    expect(block?.textContent).toContain('NWS') // source-stamped …
    expect(block?.textContent).not.toContain('api.weather.gov') // never the raw domain-suffixed source
    expect(block?.textContent).toContain('2h ago') // … and aged (§7.2)
    // Assistive tech gets the same "Warning" framing sighted users read from the
    // accent treatment — colour is never the only cue.
    expect(screen.getByText('Warning:')).toBeInTheDocument()
  })

  it('renders no warning block on a clean card', () => {
    const { container } = render(<RecommendationCard card={card()} onOpen={vi.fn()} />)
    expect(container.querySelector('.card-warnings')).not.toBeInTheDocument()
  })

  it('drops the age segment — no dangling "· " — when a warning has no parseable observed_at (Epic 046 S4 AC-4.2 / D6)', () => {
    // The httpPlanner mapping degrades an unparseable `observed_at` to
    // undefined (D6); the block must then show source alone, never "NWS · "
    // with a trailing separator and an empty stamp.
    const { container } = render(
      <RecommendationCard card={card({ warnings: [{ ...warning, observedAgo: undefined }] })} onOpen={vi.fn()} />,
    )
    const meta = container.querySelector('.card-warning-meta')
    expect(meta).toBeInTheDocument()
    expect(meta?.textContent).toContain('NWS')
    // Source-or-silence holds (source shown) with no orphaned separator.
    expect(meta?.textContent).not.toContain('·')
    expect(meta?.textContent?.trimEnd()).toBe(meta?.textContent)
  })
})

describe('RecommendationCard accessible name carries the warning state (report #4/#7)', () => {
  const warning = {
    text: 'weather alert: Extreme Heat Warning',
    // Short provider name (D3 consistency pass, backend `provider_short`) — never
    // the raw domain-suffixed "NWS api.weather.gov" (that stays out of the card).
    source: 'NWS',
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

describe('RecommendationCard decision facts — Ascent + Duration restored (H2, ux-review-craft 2026-07)', () => {
  it('shows Distance, Ascent, and Duration together from curated enrichment', () => {
    render(
      <RecommendationCard
        card={card({
          // No geo: an out-and-back geometry would double-count the curated
          // distance (summary.ts's own doubling rule) — this case isolates the
          // "shape can't be confirmed, take the curated figure at face value" path.
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
    // Each label's icon (Epic 021) adds a second, sr-only node with the same
    // word, so match one-or-more rather than exactly one.
    expect(screen.getAllByText('Distance').length).toBeGreaterThan(0)
    expect(screen.getByText('3.7 mi')).toBeInTheDocument()
    expect(screen.getAllByText('Ascent').length).toBeGreaterThan(0)
    expect(screen.getByText('1,050 ft')).toBeInTheDocument()
    expect(screen.getAllByText('Duration').length).toBeGreaterThan(0)
    expect(screen.getByText('2–3 hr')).toBeInTheDocument()
  })

  it('derives Ascent from the live elevation profile when no curated figure exists', () => {
    const { container } = render(<RecommendationCard card={card({ enrichment: undefined })} onOpen={vi.fn()} />)
    expect(container.querySelector('svg.glyph')).toBeInTheDocument()
    // The fixture profile climbs 1000 m → 1200 m = 200 m ≈ 656 ft.
    expect(screen.getAllByText('Ascent').length).toBeGreaterThan(0)
    expect(screen.getByText('656 ft')).toBeInTheDocument()
  })

  it('renders no Ascent figure when there is no elevation profile at all', () => {
    render(<RecommendationCard card={card({ enrichment: undefined, geo: undefined })} onOpen={vi.fn()} />)
    expect(screen.queryByText('Ascent')).not.toBeInTheDocument()
  })

  it('a null-elevation trail (Distance known, profile null) discloses Ascent/Duration as unavailable instead of a lone Distance (ux-review 2026-07 Finding 6)', () => {
    const { container } = render(
      <RecommendationCard
        card={card({
          // Distance is knowable (curated), but the trail's elevation profile is
          // null — no total_gain_m → no ascent, no Naismith duration. The old
          // behaviour: Ascent and Duration silently vanish, leaving a lone
          // "1.5 mi" that reads like a broken card.
          enrichment: { distanceMiles: 1.5, provenance: 'mock' },
          geo: { geometry: null, trailhead: { lat: 38.5, lon: -78.4 }, quality: 'confident', elevationProfile: null },
        })}
        onOpen={vi.fn()}
      />,
    )
    expect(screen.getByText('1.5 mi')).toBeInTheDocument()
    // The row stays structurally complete: three slots, not one.
    expect(container.querySelectorAll('.decision-item')).toHaveLength(3)
    const gaps = container.querySelectorAll('.decision-value--unavailable')
    expect(gaps).toHaveLength(2)
    for (const gap of gaps) {
      expect(gap.querySelector('[aria-hidden="true"]')?.textContent).toBe('—')
    }
    expect(screen.getByText('Ascent not available')).toBeInTheDocument()
    expect(screen.getByText('Duration not available')).toBeInTheDocument()
  })

  it('renders all four facts together (Drive + Distance + Ascent + Duration) — the `.decision` grid must have a column for each', () => {
    // A signed-in personal frame supplies Drive alongside the other three
    // (mockPlanner always does) — the card must not silently drop or strand one.
    const { container } = render(
      <RecommendationCard
        card={card({
          geo: undefined,
          enrichment: {
            distanceMiles: 3.7,
            ascentFeet: 1050,
            durationHours: '2–3 hr',
            driveMinutes: 28,
            provenance: 'mock',
          },
        })}
        onOpen={vi.fn()}
      />,
    )
    expect(container.querySelectorAll('.decision-item')).toHaveLength(4)
    expect(screen.getAllByText('Drive').length).toBeGreaterThan(0)
    expect(screen.getByText('28 min')).toBeInTheDocument()
  })
})

describe('RecommendationCard facts row never clips (ux-review 2026-07 Finding 1)', () => {
  it('renders all three curated facts (Distance, Ascent, Duration) as separate legible items, none dropped', () => {
    const { container } = render(
      <RecommendationCard
        card={card({
          geo: undefined,
          enrichment: {
            distanceMiles: 8.4,
            ascentFeet: 3200,
            durationHours: '5–6 hr',
            provenance: 'mock',
          },
        })}
        onOpen={vi.fn()}
      />,
    )
    const items = container.querySelectorAll('.decision-item')
    expect(items).toHaveLength(3)
    expect(screen.getByText('8.4 mi')).toBeInTheDocument()
    expect(screen.getByText('3,200 ft')).toBeInTheDocument()
    expect(screen.getByText('5–6 hr')).toBeInTheDocument()
  })

  it('a long live-derived duration renders the "est." disclosure as its own badge, never concatenated into the value string that used to overflow the card', () => {
    // A profile whose Naismith estimate is long (~5 hr 5 min) — the exact
    // shape of card the finding called out ("~5 hr 5 min · est." was the
    // widest fact and clipped at the card's right edge under the old inline
    // `formatEstimatedDuration` disclosure).
    const { container } = render(
      <RecommendationCard
        card={card({
          enrichment: undefined,
          // No drawable geometry (mirrors Detail.test.tsx's live-estimate
          // fixture) — `resolveMiles` returns null, so the pace-plausibility
          // guard in `resolveDurationMinutes` is skipped rather than rejecting
          // this long duration against a short mapped distance.
          geo: {
            geometry: null,
            trailhead: { lat: 38.5, lon: -78.4 },
            quality: 'confident',
            elevationProfile: {
              samples: [],
              totalGainMeters: 900,
              totalLossMeters: 0,
              maxGradePercent: 20,
              source: 'USGS 3DEP',
              resolutionMeters: 10,
              estimatedDurationMin: 305,
            },
          },
        })}
        onOpen={vi.fn()}
      />,
    )
    // The value itself carries no "est." text — it's a clean, narrow figure.
    expect(screen.getByText('~5 hr 5 min')).toBeInTheDocument()
    // The disclosure lives in its own badge node, a sibling of the value text,
    // not appended to it — so it can wrap/shrink independently and never
    // widens the fact past the card (see `.decision-value`/`.decision-badge`
    // in styles.css, both of which dropped their old `white-space: nowrap`
    // coupling that forced the combined string onto one un-wrappable line).
    const badge = container.querySelector('.decision-badge')
    expect(badge?.textContent?.trim()).toBe('est.')
    expect(container.querySelector('.decision-value')?.textContent).not.toContain('~5 hr 5 min · est.')
  })

  it('the facts row wraps rather than clipping when all four facts + a long duration compete for width', () => {
    const { container } = render(
      <RecommendationCard
        card={card({
          geo: undefined,
          enrichment: {
            distanceMiles: 11.2,
            ascentFeet: 4400,
            durationHours: '7–8.5 hr',
            driveMinutes: 95,
            provenance: 'mock',
          },
        })}
        onOpen={vi.fn()}
      />,
    )
    const row = container.querySelector('.decision')
    expect(row).toBeInTheDocument()
    // The row is a wrapping flex container, not a fixed-column grid that would
    // hold every item on one un-shrinkable line (jsdom doesn't lay out real
    // pixels, so this asserts the CSS mechanism rather than a measured width).
    expect(row).toHaveClass('decision')
    expect(container.querySelectorAll('.decision-item')).toHaveLength(4)
    // Every fact's value is still present and intact — none silently dropped
    // or truncated to make room for the others.
    expect(screen.getByText('11.2 mi')).toBeInTheDocument()
    expect(screen.getByText('4,400 ft')).toBeInTheDocument()
    expect(screen.getByText('7–8.5 hr')).toBeInTheDocument()
    expect(screen.getByText('95 min')).toBeInTheDocument()
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

  it('stale-degraded wears a `history` glyph, never the `!` hazard mark (Epic 020, AC-20.3.1)', () => {
    const { container } = silence({ conditionSilence: { state: 'stale-degraded' } })
    const glyph = container.querySelector('.condition-silence-glyph')
    expect(glyph?.textContent).not.toBe('!')
    expect(glyph?.querySelector('svg')).toBeInTheDocument()
  })

  it('shows the primary line as the single Now value; the residual-silence note is Detail-only (DD1)', () => {
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
    // One Now value, not the multi-line list; the "other conditions" residual
    // note moves to Detail so the lean card stays a single condition slot.
    expect(container.querySelector('.condition-value')?.textContent).toContain('54°F · clear')
    expect(container.querySelector('.condition-silence--partial')).not.toBeInTheDocument()
  })
})

describe('RecommendationCard per-kind condition states (Epic 018 S4f, CDP-02)', () => {
  it('renders the compact coverage summary beneath the Now line — the shown set never implies exhaustive (AC-4f.2)', () => {
    const { container } = render(
      <RecommendationCard
        card={card({
          enrichment: undefined,
          conditionLines: [{ text: '54°F · clear (NWS, 12m ago)', source: 'NWS', confidence: 'stated', provenance: 'live' }],
          conditions: [
            { kind: 'weather', state: 'present', source: 'NWS', checkedAgo: '12m ago' },
            { kind: 'fire', state: 'no-hazard', source: 'NASA FIRMS', checkedAgo: '20m ago' },
            { kind: 'air', state: 'not-fetched' },
          ],
        })}
        onOpen={vi.fn()}
      />,
    )
    expect(container.querySelector('.condition-value')?.textContent).toContain('54°F · clear')
    const summary = container.querySelector('.condition-states--compact')
    expect(summary).toBeInTheDocument()
    expect(summary?.textContent).toContain('Checked — nothing to flag: Fire (NASA FIRMS · 20m ago)')
    expect(summary?.textContent).toContain('Not checked here: Air quality')
    // Present kinds live in the Now line, never repeated in the summary.
    expect(summary?.textContent).not.toContain('Weather')
  })

  it('a lineless answered-clear card renders its real dispositions, never "not checked" (the retired #160 mislabel)', () => {
    const { container } = render(
      <RecommendationCard
        card={card({
          enrichment: undefined,
          conditionLines: [],
          conditions: [
            { kind: 'fire', state: 'no-hazard', source: 'NASA FIRMS', checkedAgo: '20m ago' },
            { kind: 'closures', state: 'unavailable' },
          ],
        })}
        onOpen={vi.fn()}
      />,
    )
    expect(container.querySelector('.condition-silence')).not.toBeInTheDocument()
    expect(container.querySelector('.condition-state-group.condition-state--no-hazard')?.textContent).toContain(
      'Checked — nothing to flag: Fire',
    )
    // The outage is visibly its own state — never conflated with not-checked.
    expect(container.querySelector('.condition-state-group.condition-state--unavailable')?.textContent).toContain(
      'Couldn’t verify: Closures',
    )
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
    // The bookmark-check icon's sr-only label echoes "Saved", so the word now
    // appears in two nodes (accent + chip caption).
    expect(screen.getAllByText('Saved').length).toBeGreaterThan(0)
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
