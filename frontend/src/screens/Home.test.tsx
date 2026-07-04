import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { Home } from './Home'
import { PlannerProvider } from '../data/PlannerProvider'
import { ANON_SCOPE } from '../data/api'
import { resetSavedTrailsForTests, toggleTrailSaved } from '../data/savedTrails'
import type { PlannerClient } from '../data/source'
import type { FeedVM } from '../data/vm'
import type { TuningState } from '../types'

afterEach(() => resetSavedTrailsForTests())

const TUNING: TuningState = {
  origin: 'frontRoyal',
  when: 'weekendMorning',
  effort: 'moderate',
  party: 'solo',
  today: 'standard',
  readinessOn: false,
  prompt: '',
}

const noop = () => {}

/** A client whose plan() never resolves — so Home stays in the loading state and
 *  the slow-flag timer can drive the cold-start copy swap. */
function hangingClient(): PlannerClient {
  return {
    plan: () => new Promise<FeedVM>(() => {}),
    recentEpisodes: () => Promise.resolve([]),
  } as unknown as PlannerClient
}

function renderHome() {
  return render(
    <PlannerProvider scope={ANON_SCOPE} client={hangingClient()}>
      <Home
        tuning={TUNING}
        anonymous
        onOpenTuning={noop}
        onOpenTrail={noop}
        onOpenOutcome={noop}
        onApplyTuning={noop}
      />
    </PlannerProvider>,
  )
}

describe('Home loading progress copy (D4 — never a frozen line past ~10s)', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('shows "Reading conditions…" first, then steps through reassure and cold-start copy', () => {
    renderHome()

    expect(screen.getByText('Reading conditions…')).toBeInTheDocument()
    expect(screen.queryByText(/Still checking conditions/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Waking the server/)).not.toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(10_000)
    })

    expect(screen.getByText(/Still checking conditions/)).toBeInTheDocument()
    expect(screen.queryByText('Reading conditions…')).not.toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(15_000)
    })

    expect(screen.getByText(/Waking the server/)).toBeInTheDocument()
    expect(screen.queryByText(/Still checking conditions/)).not.toBeInTheDocument()
  })

  it('marks the results region aria-busy only while loading', () => {
    const { container } = renderHome()
    expect(container.querySelector('[aria-busy="true"]')).toBeInTheDocument()
  })
})

/** A client whose plan() resolves immediately with the given feed. */
function readyClient(feed: FeedVM): PlannerClient {
  return {
    plan: () => Promise.resolve(feed),
    recentEpisodes: () => Promise.resolve([]),
  } as unknown as PlannerClient
}

function feedWith(overrides: Partial<FeedVM>): FeedVM {
  return {
    query: '',
    cards: [
      { id: 'compton-peak', name: 'Compton Peak', distanceMi: 2.1, conditionLines: [], warnings: [] },
    ],
    notices: [],
    setAside: [],
    heldBack: [],
    readiness: { on: false, state: 'off' },
    dataSource: 'live',
    ...overrides,
  }
}

async function renderHomeWith(feed: FeedVM, tuning: TuningState = TUNING) {
  const result = render(
    <PlannerProvider scope={ANON_SCOPE} client={readyClient(feed)}>
      <Home
        tuning={tuning}
        anonymous
        onOpenTuning={noop}
        onOpenTrail={noop}
        onOpenOutcome={noop}
        onApplyTuning={noop}
      />
    </PlannerProvider>,
  )
  await act(async () => {}) // let the resolved plan() commit
  return result
}

describe('Home held-back disclosure (Epic 018 S5 — nothing silently vanishes)', () => {
  it('renders a quiet feed-level note naming the count and the causes', async () => {
    await renderHomeWith(
      feedWith({
        heldBack: [
          {
            id: 'a',
            name: 'Foggy Hollow',
            reasons: [
              {
                text: "weather alerts couldn't be verified (NWS api.weather.gov)",
                source: 'NWS api.weather.gov',
                kind: 'weather',
              },
            ],
          },
          {
            id: 'b',
            name: 'Mist Ridge',
            reasons: [
              {
                text: "weather alerts couldn't be verified (NWS api.weather.gov)",
                source: 'NWS api.weather.gov',
                kind: 'weather',
              },
            ],
          },
        ],
      }),
    )
    const note = screen.getByText(/2 trails held back/)
    expect(note).toBeInTheDocument()
    // Duplicate causes collapse to one honest clause, still source-stamped.
    expect(note.textContent).toBe(
      "2 trails held back — weather alerts couldn't be verified (NWS api.weather.gov)",
    )
  })

  it('renders no note when nothing was held back', async () => {
    await renderHomeWith(feedWith({}))
    expect(screen.queryByText(/held back/)).not.toBeInTheDocument()
  })
})

describe('Home region label reflects the actually served trails, never the picker\'s assumption (report #3)', () => {
  const cardAt = (id: string, lat: number, lon: number) => ({
    id,
    name: id,
    distanceMi: 2.1,
    conditionLines: [],
    warnings: [],
    geo: { geometry: null, trailhead: { lat, lon }, quality: 'confident' as const, elevationProfile: null },
  })

  it('shows Shenandoah when the origin is Nags Head but the served trail is actually there (never lets the picker override the results)', async () => {
    const nagsHeadTuning: TuningState = { ...TUNING, origin: 'nagsHead' }
    // Front Royal / Shenandoah coordinates, despite the Outer Banks origin picked.
    await renderHomeWith(feedWith({ cards: [cardAt('compton-peak', 38.918, -78.194)] }), nagsHeadTuning)

    // Both the context sentence and the stack-meta count carry the region tag —
    // both must track the SERVED trails, not the selected origin.
    expect(screen.getAllByText(/Shenandoah/).length).toBeGreaterThan(0)
    expect(screen.queryByText(/Outer Banks/)).not.toBeInTheDocument()
  })

  it('shows Outer Banks when the served trailhead is actually there, regardless of the picked origin', async () => {
    // TUNING.origin is frontRoyal (Shenandoah); the served trail sits in Duck.
    await renderHomeWith(feedWith({ cards: [cardAt('jockeys-ridge', 36.166, -75.75)] }))

    expect(screen.getAllByText(/Outer Banks/).length).toBeGreaterThan(0)
    expect(screen.queryByText(/Shenandoah/)).not.toBeInTheDocument()
  })

  it('falls back to the picked origin\'s region when the served cards carry no coordinate at all', async () => {
    await renderHomeWith(feedWith({})) // the default fixture card has no `geo`
    expect(screen.getAllByText(/Shenandoah/).length).toBeGreaterThan(0)
  })

  it('names the active origin in the anonymous context sentence, not just the region', async () => {
    await renderHomeWith(feedWith({}))
    expect(screen.getByText(/from Front Royal/)).toBeInTheDocument()
  })
})

describe('Home hoists a region-wide alert to one feed banner instead of a per-card wall (report #1)', () => {
  const heat = (text: string) => ({
    text,
    source: 'NWS api.weather.gov',
    observedAgo: '2h ago',
    kind: 'weather',
    provenance: 'live' as const,
  })
  const cardWith = (id: string, warnings: ReturnType<typeof heat>[]) => ({
    id,
    name: id,
    distanceMi: 2,
    conditionLines: [],
    warnings,
  })

  it('shows a region-wide alert once at feed level and clears it off every card', async () => {
    const shared = heat('weather alert: Extreme Heat Warning — NWS')
    const cards = [cardWith('a', [shared]), cardWith('b', [shared]), cardWith('c', [shared])]
    const { container } = await renderHomeWith(feedWith({ cards }))

    expect(screen.getAllByText(/Extreme Heat Warning/).length).toBe(1)
    expect(container.querySelector('.feed-alert-banner')).toBeInTheDocument()
    expect(container.querySelectorAll('.card .card-warnings').length).toBe(0)
  })

  it('keeps a trail-specific warning on its own card alongside the hoisted region-wide one', async () => {
    const shared = heat('weather alert: Extreme Heat Warning — NWS')
    const specific = heat('flash flood warning — creek crossing')
    const cards = [cardWith('a', [shared, specific]), cardWith('b', [shared]), cardWith('c', [shared])]
    const { container } = await renderHomeWith(feedWith({ cards }))

    expect(screen.getAllByText(/Extreme Heat Warning/).length).toBe(1)
    // The trail-specific warning stays on its own card: spoken once, as the
    // top-line verdict headline. The sourced warning block below it collapses
    // to just source + age — it doesn't repeat the hazard sentence verbatim.
    expect(container.textContent).toMatch(/flash flood warning/)
    const specificBlock = container.querySelector('.card .card-warnings')
    expect(specificBlock?.textContent).not.toMatch(/flash flood warning/)
    expect(specificBlock?.textContent).toMatch(/NWS api\.weather\.gov/)
    expect(container.querySelectorAll('.card .card-warnings').length).toBe(1)
  })

  it('never stacks a lower-severity near-duplicate once a higher-severity one has been hoisted', async () => {
    const strong = heat('weather alert: Extreme Heat Warning — NWS')
    const weak = heat('weather alert: Heat Advisory — NWS')
    const cards = [cardWith('a', [strong, weak]), cardWith('b', [strong, weak])]
    await renderHomeWith(feedWith({ cards }))

    expect(screen.getAllByText(/Extreme Heat Warning/).length).toBe(1)
    expect(screen.queryByText(/Heat Advisory/)).not.toBeInTheDocument()
  })

  it('renders no banner when no warning is shared across the feed', async () => {
    const { container } = await renderHomeWith(feedWith({}))
    expect(container.querySelector('.feed-alert-banner')).not.toBeInTheDocument()
  })
})

describe('Home loading state (skeleton placeholders, NNG structured wait)', () => {
  it('renders card-shaped skeletons immediately instead of a bare loading line', () => {
    const { container } = renderHome()
    expect(container.querySelectorAll('.skeleton-card').length).toBe(3)
  })

  it('keeps the skeletons visible once the "waking the server" copy appears', () => {
    vi.useFakeTimers()
    const { container } = renderHome()
    act(() => {
      vi.advanceTimersByTime(25_000)
    })
    expect(screen.getByText(/Waking the server/)).toBeInTheDocument()
    expect(container.querySelectorAll('.skeleton-card').length).toBe(3)
    vi.useRealTimers()
  })
})

describe('Home progressive card reveal (D4 — cards settle in, not a flat pop-in)', () => {
  it('staggers each card with an increasing reveal delay', async () => {
    const cards = [
      { id: 'a', name: 'A', distanceMi: 1, conditionLines: [], warnings: [] },
      { id: 'b', name: 'B', distanceMi: 2, conditionLines: [], warnings: [] },
      { id: 'c', name: 'C', distanceMi: 3, conditionLines: [], warnings: [] },
    ]
    const { container } = await renderHomeWith(feedWith({ cards }))
    const reveals = container.querySelectorAll('.card-reveal')
    expect(reveals.length).toBe(3)
    const delays = Array.from(reveals).map((el) => parseInt((el as HTMLElement).style.animationDelay, 10))
    expect(delays).toEqual([0, 45, 90])
  })

  it('applies no reveal animation under prefers-reduced-motion', async () => {
    const matchMediaMock = vi.fn().mockReturnValue({ matches: true })
    vi.stubGlobal('matchMedia', matchMediaMock)
    const cards = [{ id: 'a', name: 'A', distanceMi: 1, conditionLines: [], warnings: [] }]
    const { container } = await renderHomeWith(feedWith({ cards }))
    expect(container.querySelectorAll('.card-reveal').length).toBe(0)
    expect(container.querySelector('.card')).toBeInTheDocument()
    vi.unstubAllGlobals()
  })
})

describe('Home empty state (NNG: say what happened + what to do)', () => {
  it('names the empty frame and offers the one-tap widen', async () => {
    await renderHomeWith(feedWith({ cards: [] }))
    expect(screen.getByText('Nothing holds under this frame right now.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Include a bigger day' })).toBeInTheDocument()
  })

  it('falls back to "Adjust search" once the frame is already at its widest (never a dead end)', async () => {
    const widestTuning: TuningState = { ...TUNING, effort: 'bigDay' }
    const onOpenTuning = vi.fn()
    render(
      <PlannerProvider scope={ANON_SCOPE} client={readyClient(feedWith({ cards: [] }))}>
        <Home
          tuning={widestTuning}
          anonymous
          onOpenTuning={onOpenTuning}
          onOpenTrail={noop}
          onOpenOutcome={noop}
          onApplyTuning={noop}
        />
      </PlannerProvider>,
    )
    await act(async () => {})
    await userEvent.click(screen.getByRole('button', { name: 'Adjust search' }))
    expect(onOpenTuning).toHaveBeenCalled()
  })
})

describe('Home error state (NNG: calm, actionable, retryable)', () => {
  it('shows a calm error message and a retry action', async () => {
    await renderHomeWith(
      feedWith({
        cards: [],
        error: { kind: 'offline', message: 'Couldn’t reach the planner. Try again.' },
      }),
    )
    expect(screen.getByText('Couldn’t reach the planner. Try again.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})

describe('Home Saved filter (client-side, localStorage, no backend/auth)', () => {
  const cardNamed = (id: string, name: string) => ({
    id,
    name,
    distanceMi: 2.1,
    conditionLines: [],
    warnings: [],
  })

  it('renders no Saved toggle when nothing is served and nothing is saved', async () => {
    await renderHomeWith(feedWith({ cards: [] }))
    expect(screen.queryByRole('button', { name: /^saved/i })).not.toBeInTheDocument()
  })

  it('filters the stack to only saved trails when toggled on', async () => {
    toggleTrailSaved('compton-peak')
    const cards = [cardNamed('compton-peak', 'Compton Peak'), cardNamed('old-rag', 'Old Rag')]
    await renderHomeWith(feedWith({ cards }))

    expect(screen.getByRole('button', { name: 'Open Compton Peak' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open Old Rag' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /saved \(1\)/i }))

    expect(screen.getByRole('button', { name: 'Open Compton Peak' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Open Old Rag' })).not.toBeInTheDocument()
  })

  it('shows the honest "No saved trails yet" empty state when nothing has ever been saved', async () => {
    const cards = [cardNamed('compton-peak', 'Compton Peak')]
    await renderHomeWith(feedWith({ cards }))
    // No saved ids at all: the toggle only appears once something is saved or
    // served, and here it's served — the count-less "Saved" label starts it.
    await userEvent.click(screen.getByRole('button', { name: /^saved$/i }))
    expect(screen.getByText('No saved trails yet.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /open compton peak/i })).not.toBeInTheDocument()
  })

  it('shows a distinct honest note when saved trails exist but none match this frame', async () => {
    toggleTrailSaved('elsewhere-trail')
    const cards = [cardNamed('compton-peak', 'Compton Peak')]
    await renderHomeWith(feedWith({ cards }))
    await userEvent.click(screen.getByRole('button', { name: /saved \(1\)/i }))
    expect(screen.getByText('None of your saved trails are in this frame.')).toBeInTheDocument()
  })

  it('toggles back to showing all trails via "Show all"', async () => {
    toggleTrailSaved('compton-peak')
    const cards = [cardNamed('compton-peak', 'Compton Peak'), cardNamed('old-rag', 'Old Rag')]
    await renderHomeWith(feedWith({ cards }))

    await userEvent.click(screen.getByRole('button', { name: /saved \(1\)/i }))
    expect(screen.queryByRole('button', { name: 'Open Old Rag' })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /show all/i }))
    expect(screen.getByRole('button', { name: 'Open Old Rag' })).toBeInTheDocument()
  })
})
