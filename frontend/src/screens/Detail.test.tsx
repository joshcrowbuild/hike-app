import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ANON_SCOPE } from '../data/api'
import { PlannerProvider } from '../data/PlannerProvider'
import { resetSavedTrailsForTests } from '../data/savedTrails'
import type { PlannerClient } from '../data/source'
import type { CardVM, TrailWaterVM } from '../data/vm'
import { Detail } from './Detail'

afterEach(() => resetSavedTrailsForTests())

function card(overrides: Partial<CardVM> = {}): CardVM {
  return {
    id: 'stony-man',
    name: 'Stony Man Loop',
    distanceMi: 3.2,
    conditionLines: [],
    warnings: [],
    geo: {
      geometry: { type: 'LineString', coordinates: [[-78.4, 38.5], [-78.39, 38.51]] },
      trailhead: { lat: 38.5, lon: -78.4 },
      quality: 'confident',
      elevationProfile: null,
    },
    ...overrides,
  }
}

function readyClient(vm: CardVM, water: TrailWaterVM | null = null): PlannerClient {
  return {
    plan: () => Promise.resolve({ query: '', cards: [], notices: [], setAside: [], heldBack: [], readiness: { on: false, state: 'off' }, dataSource: 'live' as const }),
    getCard: () => Promise.resolve(vm),
    // The water answer (Epic 041); null = the not-fetched silence (no row).
    trailWater: () => Promise.resolve(water),
    recentEpisodes: () => Promise.resolve([]),
    getEpisode: () => Promise.resolve(null),
    recordOutcome: () => Promise.reject(new Error('not used')),
  } as unknown as PlannerClient
}

async function renderDetail(vm: CardVM, water: TrailWaterVM | null = null) {
  const result = render(
    <PlannerProvider scope={ANON_SCOPE} client={readyClient(vm, water)}>
      <Detail id={vm.id} onBack={vi.fn()} onReplan={vi.fn()} />
    </PlannerProvider>,
  )
  await act(async () => {})
  return result
}

describe('Detail is the commitment view — it renders the fields relocated off the lean card (Epic 019 AC-19.1.1)', () => {
  const enriched = card({
    conditionLines: [
      { text: '54°F · clear', source: 'NWS', confidence: 'stated', provenance: 'live' },
      { text: 'AQI 32 · good', source: 'AirNow', confidence: 'stated', provenance: 'live' },
    ],
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
      provenance: 'live',
    },
  })

  it('renders placeCue, fitLine, practicalNote, duration and the FULL condition list', async () => {
    await renderDetail(enriched)
    expect(screen.getByText('the granite dome above the valley')).toBeInTheDocument() // placeCue
    expect(screen.getByText('Matches your taste for open summits.')).toBeInTheDocument() // fitLine
    expect(screen.getByText('Arrive early; the lot fills by 9.')).toBeInTheDocument() // practicalNote
    expect(screen.getByText('3–4 hr')).toBeInTheDocument() // duration fact
    // The full multi-line condition list (both lines), not just the card's single slot.
    expect(screen.getByText('54°F · clear')).toBeInTheDocument()
    expect(screen.getByText('AQI 32 · good')).toBeInTheDocument()
  })
})

describe('Card + Detail read the SAME CardVM (Epic 019 AC-19.1.2 — no VM/DTO change)', () => {
  it('one object: the card omits the relocated fields, Detail includes them', async () => {
    const shared = card({
      enrichment: {
        placeCue: 'the granite dome above the valley',
        area: 'Shenandoah',
        distanceMiles: 3.7,
        driveMinutes: 28,
        fitLine: 'Matches your taste for open summits.',
        provenance: 'live',
      },
    })
    // Detail (this file's harness) reads placeCue + fitLine off the shared object…
    await renderDetail(shared)
    expect(screen.getByText('the granite dome above the valley')).toBeInTheDocument()
    expect(screen.getByText('Matches your taste for open summits.')).toBeInTheDocument()
    // …and the card, given the identical object, renders neither (asserted in
    // RecommendationCard.test.tsx). Same shape, two presentations — no adapter fork.
  })
})

describe('Detail Duration — live estimate disclosed as such (Epic 022)', () => {
  it('renders the Naismith estimate with an "est." disclosure when no mock duration string is present', async () => {
    const { container } = await renderDetail(
      card({
        geo: {
          geometry: null,
          trailhead: { lat: 38.5, lon: -78.4 },
          quality: 'confident',
          elevationProfile: {
            samples: [],
            totalGainMeters: 200,
            totalLossMeters: 0,
            maxGradePercent: 40,
            source: 'USGS 3DEP',
            resolutionMeters: 10,
            estimatedDurationMin: 26,
          },
        },
      }),
    )
    // The "est." disclosure is now its own badge element beside the value
    // (ux-review 2026-07 Finding 1: a single concatenated "~25 min · est."
    // string was the widest decision fact and clipped the card's right edge)
    // — assert the value and the badge as the two nodes they now are, rather
    // than one combined text match.
    expect(screen.getByText('~25 min')).toBeInTheDocument()
    expect(container.querySelector('.decision-badge')?.textContent?.trim()).toBe('est.')
  })

  it('renders no Duration fact when NOTHING resolves (no distance either) — nothing to disclose a gap in', async () => {
    await renderDetail(card({ geo: { geometry: null, trailhead: { lat: 38.5, lon: -78.4 }, quality: 'confident', elevationProfile: null } }))
    expect(screen.queryByText(/Duration/)).not.toBeInTheDocument()
  })

  it('discloses Ascent + Duration as honestly unavailable ("—"), never a silent omission, once Distance anchors the row (Finding 6)', async () => {
    const { container } = await renderDetail(
      card({
        // A real Distance (via enrichment, independent of geometry) with a null
        // elevation profile — exactly the null-elevation shape Finding 6 named:
        // Ascent/Duration have no figure, but the trail is real and Distance shows.
        enrichment: { distanceMiles: 4.2, provenance: 'live' },
        geo: { geometry: null, trailhead: { lat: 38.5, lon: -78.4 }, quality: 'confident', elevationProfile: null },
      }),
    )
    expect(screen.getByText('4.2 mi')).toBeInTheDocument()
    // Ascent and Duration stay in the row — as a disclosed gap, not a vanished fact.
    expect(screen.getAllByText('Ascent').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Duration').length).toBeGreaterThan(0)
    const gaps = container.querySelectorAll('.decision-value--unavailable')
    expect(gaps).toHaveLength(2)
    for (const gap of gaps) {
      expect(gap.querySelector('[aria-hidden="true"]')?.textContent).toBe('—')
    }
    expect(screen.getByText('Ascent not available')).toBeInTheDocument()
    expect(screen.getByText('Duration not available')).toBeInTheDocument()
  })
})

describe('Detail Directions (prominent, no longer buried in the map controls)', () => {
  it('renders a Directions link near the top when the trail has geo', async () => {
    await renderDetail(card())
    const link = screen.getByRole('link', { name: /directions to the stony man loop trailhead/i })
    expect(link).toHaveAttribute('href', expect.stringContaining('google.com/maps/dir/'))
    expect(link).toHaveAttribute('href', expect.stringContaining('travelmode=driving'))
    expect(link.getAttribute('href')).toContain(encodeURIComponent('38.5,-78.4'))
  })

  it('renders no Directions link when the trail has no geo', async () => {
    await renderDetail(card({ geo: undefined }))
    expect(screen.queryByRole('link', { name: /directions/i })).not.toBeInTheDocument()
  })
})

describe('Detail Send-to-device (GPX export, Epic 028)', () => {
  it('renders a GPX download link with the export href when the trail has route geometry', async () => {
    await renderDetail(card())
    const link = screen.getByRole('link', { name: /download the stony man loop route as a gpx file/i })
    expect(link).toHaveAttribute('download')
    expect(link.getAttribute('href')).toContain('/trail/stony-man/export.gpx')
  })

  it('renders no GPX download link when card.geo is undefined', async () => {
    await renderDetail(card({ geo: undefined }))
    expect(screen.queryByRole('link', { name: /gpx file/i })).not.toBeInTheDocument()
  })

  it('renders no GPX download link when card.geo.geometry is null', async () => {
    await renderDetail(
      card({ geo: { geometry: null, trailhead: { lat: 38.5, lon: -78.4 }, quality: 'confident', elevationProfile: null } }),
    )
    expect(screen.queryByRole('link', { name: /gpx file/i })).not.toBeInTheDocument()
  })
})

describe('Detail Save (client-side, localStorage, anonymous-friendly)', () => {
  it('toggles saved state', async () => {
    const user = userEvent.setup()
    await renderDetail(card())
    const save = screen.getByRole('button', { name: /save stony man loop/i })
    expect(save).toHaveAttribute('aria-pressed', 'false')

    await user.click(save)
    expect(screen.getByRole('button', { name: /remove stony man loop from saved/i })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
  })

  it('reflects a save made on the feed card once Detail mounts (same localStorage-backed state)', async () => {
    const { toggleTrailSaved } = await import('../data/savedTrails')
    toggleTrailSaved('stony-man')
    await renderDetail(card())
    expect(screen.getByRole('button', { name: /remove stony man loop from saved/i })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
  })
})

describe('Detail uses a real screen title, not the quiet .wordmark slot (Epic 020, AC-20.4.1)', () => {
  it('renders .screen-title instead of .wordmark', async () => {
    const { container } = await renderDetail(card())
    expect(container.querySelector('.wordmark')).not.toBeInTheDocument()
    expect(container.querySelector('.screen-title')).toBeInTheDocument()
  })
})

describe('Detail water fact (Epic 041) — one answer line, CDP-02 three ways', () => {
  const answered: TrailWaterVM = {
    state: 'sources',
    basis: 'route',
    radiusM: 200,
    source: 'OSM',
    sources: [
      { id: 'water:osm:node/1', type: 'spring', name: 'Furnace Spring', lat: 38.5, lon: -78.4, distanceM: 64, seasonal: 'yes' },
      { id: 'water:osm:node/2', type: 'spring', lat: 38.51, lon: -78.39, distanceM: 118 },
      { id: 'water:osm:node/3', type: 'water_tap', lat: 38.5, lon: -78.41, distanceM: 22 },
    ],
    provenance: 'live',
  }

  it('answered: renders ONE water line with counts, radius, basis, and the not-verified-live hedge', async () => {
    const { container } = await renderDetail(card(), answered)
    expect(screen.getByText('2 springs, 1 tap within ~650 ft of the route')).toBeInTheDocument()
    // The row label carries "Water" exactly once for AT (sr-only via Icon; the
    // visible twin is aria-hidden — the DecisionItem pattern).
    const label = container.querySelector('.detail-water-label')
    expect(label?.textContent).toContain('Water')
    expect(label?.querySelector('span[aria-hidden="true"]')?.textContent).toBe('Water')
    const note = container.querySelector('.detail-water-note')
    expect(note?.textContent).toContain('OpenStreetMap')
    expect(note?.textContent).toContain('not verified live')
    expect(note?.textContent).toContain('springs may be seasonal')
    // One row, not a ledger.
    expect(container.querySelectorAll('.detail-water')).toHaveLength(1)
  })

  it('answered-empty: renders the calm carry-what-you-need answer, never the flagged treatment', async () => {
    const { container } = await renderDetail(card(), { ...answered, state: 'none-nearby', sources: [] })
    expect(
      screen.getByText('No mapped water within ~650 ft of the route — carry what you need.'),
    ).toBeInTheDocument()
    // An answered-empty is an ANSWER: it must not wear the couldn't-verify signal.
    expect(container.querySelector('.detail-water .signal')).not.toBeInTheDocument()
    expect(container.querySelector('.detail-water-note')?.textContent).toContain('not verified live')
  })

  it('silence: a null answer renders NO water row at all (not an empty claim)', async () => {
    const { container } = await renderDetail(card(), null)
    expect(container.querySelector('.detail-water')).not.toBeInTheDocument()
    expect(screen.queryByText(/No mapped water/)).not.toBeInTheDocument()
    expect(screen.queryByText('Water')).not.toBeInTheDocument()
  })

  it('never claims potability in either answered state', async () => {
    const { container } = await renderDetail(card(), answered)
    const text = (container.querySelector('.detail-water')?.textContent ?? '').toLowerCase()
    for (const banned of ['potable', 'drinkable', 'safe']) {
      expect(text).not.toContain(banned)
    }
  })
})

describe('Detail per-kind condition coverage (Epic 018 S4f, CDP-02)', () => {
  it('renders the full row-per-kind coverage list, one row per kind', async () => {
    const { container } = await renderDetail(
      card({
        conditionLines: [{ text: '54°F · clear', source: 'NWS', confidence: 'stated', provenance: 'live' }],
        conditions: [
          { kind: 'weather', state: 'present', source: 'NWS', checkedAgo: '12m ago' },
          { kind: 'fire', state: 'no-hazard', source: 'NASA FIRMS', checkedAgo: '20m ago' },
          { kind: 'water', state: 'no-data', source: 'USGS', detail: 'no gauge within 30 mi' },
          { kind: 'closures', state: 'unavailable' },
          { kind: 'permits', state: 'not-fetched' },
        ],
      }),
    )
    const rows = container.querySelectorAll('.condition-state')
    expect(rows).toHaveLength(5)
    // Each state is its own legible disposition — answered-clear ≠ outage ≠ not-checked.
    expect(container.querySelector('.condition-state--no-hazard')?.textContent).toContain('checked — nothing to flag')
    expect(container.querySelector('.condition-state--no-data')?.textContent).toContain('no gauge within 30 mi')
    expect(container.querySelector('.condition-state--unavailable')?.textContent).toContain(
      'couldn’t be verified right now',
    )
    expect(container.querySelector('.condition-state--not-fetched')?.textContent).toContain('not checked here')
    // The payload supersedes the legacy blanket silence note.
    expect(container.querySelector('.condition-silence')).not.toBeInTheDocument()
  })

  it('a lineless card with a payload renders the coverage list, never the legacy not-fetched blanket', async () => {
    const { container } = await renderDetail(
      card({
        conditionLines: [],
        conditions: [{ kind: 'fire', state: 'no-hazard', source: 'NASA FIRMS', checkedAgo: '20m ago' }],
      }),
    )
    expect(container.querySelector('.condition-silence')).not.toBeInTheDocument()
    expect(container.querySelector('.condition-state--no-hazard')).toBeInTheDocument()
  })
})

describe('Detail conditions render ONCE — no duplicate prose+table for the same fact (ux-review 2026-07 Finding 4/7)', () => {
  const merged = card({
    conditionLines: [
      { text: 'Sunny 90°F', source: 'NWS', confidence: 'stated', provenance: 'live' },
      { text: 'AQI 45 (Good)', source: 'EPA', confidence: 'hedged', provenance: 'live' },
    ],
    conditions: [
      { kind: 'weather', state: 'present', source: 'NWS', checkedAgo: '4m ago' },
      { kind: 'air', state: 'present', source: 'EPA', checkedAgo: '4m ago' },
      { kind: 'fire', state: 'no-hazard', source: 'NASA FIRMS', checkedAgo: '20m ago' },
    ],
  })

  it('never renders the legacy prose <ul> alongside the per-kind table', async () => {
    const { container } = await renderDetail(merged)
    // The table is present…
    expect(container.querySelector('.condition-states')).toBeInTheDocument()
    // …and the old prose list is gone — no second representation of the same facts.
    expect(container.querySelector('.condition-lines')).not.toBeInTheDocument()
  })

  it('folds each line\'s value into its matching per-kind row instead of dropping it', async () => {
    const { container } = await renderDetail(merged)
    const weatherRow = container.querySelector('.condition-state--present')
    expect(weatherRow?.textContent).toContain('Sunny 90°F')
    const rows = [...container.querySelectorAll('.condition-state')]
    const airRow = rows.find((r) => r.textContent?.includes('Air quality'))
    expect(airRow?.textContent).toContain('AQI 45 (Good)')
    // No value is dropped in the merge: both prose facts appear exactly once each.
    expect(container.textContent?.match(/Sunny 90°F/g)).toHaveLength(1)
    expect(container.textContent?.match(/AQI 45 \(Good\)/g)).toHaveLength(1)
  })

  it('a matched row uses ONE honest framing — the row still confirms via its disposition label, not the line\'s own separately-hedged copy', async () => {
    const { container } = await renderDetail(merged)
    // The hedged AQI line ("AQI 45 (Good)") merges into a `present` row, which
    // reads with the table's own confident "reported" framing — never the
    // prose's separate hedge ("Likely: …") duplicating the same fact.
    expect(container.querySelector('.condition-states')?.textContent).not.toContain('Likely')
    const airRow = [...container.querySelectorAll('.condition-state')].find((r) =>
      r.textContent?.includes('Air quality'),
    )
    expect(airRow?.textContent).toContain('reported')
  })

  it('a line with no matching per-kind row (a divergent payload) still surfaces as a residual line, never silently dropped', async () => {
    const { container } = await renderDetail(
      card({
        conditionLines: [{ text: 'Sunny 90°F', source: 'NWS', confidence: 'stated', provenance: 'live' }],
        conditions: [{ kind: 'fire', state: 'no-hazard', source: 'NASA FIRMS', checkedAgo: '20m ago' }],
      }),
    )
    // No conditions row claims this line's source (no weather kind at all) —
    // the table still renders as authoritative for the kinds it does cover…
    expect(container.querySelector('.condition-states')).toBeInTheDocument()
    // …and the unclaimed fact is never dropped: it surfaces as its own residual line.
    expect(container.querySelector('.condition-lines--residual')).toBeInTheDocument()
    expect(screen.getByText('Sunny 90°F')).toBeInTheDocument()
  })
})

describe('Detail conditions fold on the REAL live wire shape — FULL line source vs SHORT status source (Epic 045 S1 AC-1.2/1.3, the A1 live-data regression)', () => {
  it('renders each condition once — no residual list — when lines carry the FULL backend source and statuses carry the SHORT one', async () => {
    const live = card({
      conditionLines: [
        {
          text: 'Sunny 90°F · NWS, just now',
          body: 'Sunny 90°F',
          source: 'NWS api.weather.gov · single authoritative source (NWS LWX 56,65)',
          age: 'just now',
          confidence: 'stated',
          provenance: 'live',
        },
        {
          text: 'AQI 45 (Good) · AirNow, just now',
          body: 'AQI 45 (Good)',
          source: 'AirNow · single aggregated source',
          age: 'just now',
          confidence: 'stated',
          provenance: 'live',
        },
      ],
      conditions: [
        { kind: 'weather', state: 'present', source: 'NWS', checkedAgo: 'just now' },
        { kind: 'air', state: 'present', source: 'AirNow', checkedAgo: 'just now' },
      ],
    })
    const { container } = await renderDetail(live)
    // A1's fold-is-inert defect: on the real wire shape (FULL line source, SHORT
    // status source), the naive equality check never matched, so BOTH facts
    // used to fall through to the residual prose list — asserting it stays gone.
    expect(container.querySelector('.condition-lines--residual')).not.toBeInTheDocument()
    expect(container.querySelector('.condition-lines')).not.toBeInTheDocument()
    expect(container.textContent?.match(/Sunny 90°F/g)).toHaveLength(1)
    expect(container.textContent?.match(/AQI 45 \(Good\)/g)).toHaveLength(1)
  })

  it('never re-welds the line\'s own source+age into the folded value (the A3 in-row double ConditionStates.tsx:203 would resurface)', async () => {
    const live = card({
      conditionLines: [
        {
          text: 'Sunny 90°F · NWS, just now',
          body: 'Sunny 90°F',
          source: 'NWS api.weather.gov · single authoritative source (NWS LWX 56,65)',
          age: 'just now',
          confidence: 'stated',
          provenance: 'live',
        },
      ],
      conditions: [{ kind: 'weather', state: 'present', source: 'NWS', checkedAgo: 'just now' }],
    })
    const { container } = await renderDetail(live)
    // The folded value is `body` alone — never `text` (which welds "· NWS, just
    // now" onto the value).
    expect(container.querySelector('.condition-state-value')?.textContent).toBe('Sunny 90°F · ')
    // Source + age still state exactly once EACH inside the row's own meta —
    // not a second time baked into the value too (the in-row double A3 caused).
    const meta = container.querySelector('.condition-state--present .condition-state-meta')
    expect(meta?.textContent).toBe(' · NWS · just now')
  })
})

describe('Detail Sources section states its shared single-source descriptor once (A5, Epic 045 S1 AC-1.5)', () => {
  const liveConditions = card({
    conditionLines: [
      {
        text: 'Sunny 90°F · NWS, just now',
        body: 'Sunny 90°F',
        source: 'NWS api.weather.gov · single authoritative source (NWS LWX 56,65)',
        age: 'just now',
        confidence: 'stated',
        provenance: 'live',
      },
      {
        text: 'AQI 45 (Good) · AirNow, just now',
        body: 'AQI 45 (Good)',
        source: 'AirNow · single aggregated source',
        age: 'just now',
        confidence: 'stated',
        provenance: 'live',
      },
      {
        text: '0 active-fire detection(s) nearby · FIRMS, just now',
        body: '0 active-fire detection(s) nearby',
        source: 'FIRMS · single authoritative source (FIRMS Aqua/N)',
        age: 'just now',
        confidence: 'stated',
        provenance: 'live',
      },
    ],
    conditions: [
      { kind: 'weather', state: 'present', source: 'NWS', checkedAgo: 'just now' },
      { kind: 'air', state: 'present', source: 'AirNow', checkedAgo: 'just now' },
      { kind: 'fire', state: 'present', source: 'FIRMS', checkedAgo: 'just now' },
    ],
  })

  it('states the majority descriptor ONCE instead of on every source row', async () => {
    const { container } = await renderDetail(liveConditions)
    // Two of three rows share "single authoritative source" — stated once as a
    // section-level note, not repeated on both of their rows.
    expect(container.textContent?.match(/single authoritative source/g)).toHaveLength(1)
    const items = [...container.querySelectorAll('.source-list li')].map((li) => li.textContent)
    expect(items).toContain('NWS api.weather.gov (NWS LWX 56,65)')
    expect(items).toContain('FIRMS (FIRMS Aqua/N)')
    expect(container.querySelector('.source-note')?.textContent).toContain('single authoritative source')
  })

  it('keeps the minority (aggregated) row\'s own descriptor fully disclosed inline', async () => {
    const { container } = await renderDetail(liveConditions)
    const items = [...container.querySelectorAll('.source-list li')].map((li) => li.textContent)
    expect(items).toContain('AirNow · single aggregated source')
  })
})
