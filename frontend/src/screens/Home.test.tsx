import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { Home } from './Home'
import { PlannerProvider } from '../data/PlannerProvider'
import { ANON_SCOPE } from '../data/api'
import { feedKey, resetFeedCacheForTests, writeFeedCache } from '../data/feedCache'
import { resetSavedTrailsForTests, toggleTrailSaved } from '../data/savedTrails'
import type { PlannerClient } from '../data/source'
import type { FeedVM } from '../data/vm'
import type { TuningState } from '../types'

afterEach(() => resetSavedTrailsForTests())
// A successful anonymous resolve now write-throughs to the feed cache (Epic
// 039 S3) — clear it after every test so one test's write (many share the
// same TUNING/ANON_SCOPE key) can never seed a stale paint in the next.
afterEach(() => resetFeedCacheForTests())

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
        onOpenFacet={noop}
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
        onOpenFacet={noop}
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

  it('renders just the count, no dangling em-dash, when a held-back trail carries no disclosed reasons (Epic 046 S4 AC-4.3 / D10)', async () => {
    await renderHomeWith(
      feedWith({
        heldBack: [{ id: 'a', name: 'Foggy Hollow', reasons: [] }],
      }),
    )
    const note = screen.getByText(/1 trail held back/)
    expect(note.textContent).toBe('1 trail held back')
    expect(note.textContent).not.toMatch(/—/)
  })
})

describe('Home disclosure tiering (Epic 025 — safety ≠ housekeeping ≠ build note)', () => {
  const heldBackFixture = [
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
  ]

  it('groups the held-back/set-aside/notices housekeeping disclosures into one recessive, open-by-default <details>', async () => {
    const { container } = await renderHomeWith(
      feedWith({
        heldBack: heldBackFixture,
        setAside: [{ id: 'x', name: 'Old Rag', reason: 'party gate', kind: 'party', restorable: true }],
        notices: ['Drive times unavailable this run'],
      }),
    )

    const details = container.querySelector('.housekeeping') as HTMLDetailsElement
    expect(details).toBeInTheDocument()
    expect(details.tagName).toBe('DETAILS')
    // Open by default — nothing is hidden un-inspectably (AC-25.1.2).
    expect(details.open).toBe(true)

    // All three still reachable within the same group, not removed.
    expect(details.textContent).toMatch(/held back/)
    expect(details.textContent).toMatch(/Old Rag set aside/)
    expect(details.textContent).toMatch(/Drive times unavailable this run/)

    // A real, accessible expand control (native <summary>), not a bare div.
    const summary = details.querySelector('summary')
    expect(summary).toBeInTheDocument()
  })

  it('renders no housekeeping disclosure when the frame has nothing to disclose', async () => {
    // Two cards (not one) so the sparse note doesn't fire on the default fixture.
    const cards = [
      { id: 'a', name: 'A', distanceMi: 1, conditionLines: [], warnings: [] },
      { id: 'b', name: 'B', distanceMi: 2, conditionLines: [], warnings: [] },
    ]
    const { container } = await renderHomeWith(feedWith({ cards }))
    expect(container.querySelector('.housekeeping')).not.toBeInTheDocument()
  })

  it('is keyboard-focusable and, once activated, collapses the group without deleting its content (Rule 1)', async () => {
    const { container } = await renderHomeWith(feedWith({ heldBack: heldBackFixture }))
    const details = container.querySelector('.housekeeping') as HTMLDetailsElement
    expect(details.open).toBe(true)

    const summary = details.querySelector('summary') as HTMLElement
    // Native <summary> is keyboard-focusable and Enter/Space-activatable by
    // default — no tabindex or key handler needed for AC-25.1.2 to hold.
    summary.focus()
    expect(summary).toHaveFocus()

    await userEvent.click(summary)
    expect(details.open).toBe(false)
    // Collapsed, not deleted — still inspectable, still in the DOM (Rule 1).
    expect(details.textContent).toMatch(/held back/)
  })

  it('keeps the readiness disclosure in its own recessive, collapsible housekeeping shell', async () => {
    const { container } = await renderHomeWith(
      feedWith({ readiness: { on: true, state: 'applied', rationale: 'Trimmed for wet-trail risk today.' } }),
    )
    const readinessText = screen.getByText('Trimmed for wet-trail risk today.')
    const details = readinessText.closest('details')
    expect(details).toHaveClass('housekeeping')
    expect(details).toHaveAttribute('open')
  })

  it('never nests the safety banner inside the housekeeping tier — it stands apart, always shown', async () => {
    const shared = {
      text: 'weather alert: Extreme Heat Warning — NWS',
      source: 'NWS api.weather.gov',
      observedAgo: '2h ago',
      kind: 'weather',
      provenance: 'live' as const,
    }
    const cards = [
      { id: 'a', name: 'a', distanceMi: 2, conditionLines: [], warnings: [shared] },
      { id: 'b', name: 'b', distanceMi: 2, conditionLines: [], warnings: [shared] },
    ]
    const { container } = await renderHomeWith(feedWith({ cards, heldBack: heldBackFixture }))

    const banner = container.querySelector('.feed-alert-banner')
    expect(banner).toBeInTheDocument()
    expect(banner?.closest('.housekeeping')).toBeNull()
  })

  it('renders the sample-data note as a plain, unboxed line, never inside the collapsible housekeeping tier', async () => {
    const { container } = await renderHomeWith(feedWith({ dataSource: 'mock', heldBack: heldBackFixture }))
    const strip = container.querySelector('.sample-strip')
    expect(strip).toBeInTheDocument()
    expect(strip?.closest('.housekeeping')).toBeNull()
    expect(strip?.closest('details')).toBeNull()
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

  it('names the active origin as the This-feed card’s From facet', async () => {
    await renderHomeWith(feedWith({}))
    expect(screen.getByRole('button', { name: 'Front Royal' })).toBeInTheDocument()
  })
})

describe('Home — the This feed card replaces the context ribbon (Epic 055 S1/S3/S5)', () => {
  const weatherLine = (text = 'Mostly Cloudy 61°F · NWS, just now') => ({
    text,
    source: 'NWS api.weather.gov',
    confidence: 'stated' as const,
    provenance: 'live' as const,
  })
  const regionCard = (id: string, over: Record<string, unknown> = {}) => ({
    id,
    name: id,
    distanceMi: 2,
    conditionLines: [weatherLine()],
    conditions: [
      { kind: 'weather', state: 'present' as const, source: 'NWS', checkedAgo: 'just now' },
      { kind: 'fire', state: 'no-hazard' as const, source: 'NASA FIRMS', checkedAgo: 'just now' },
      { kind: 'air', state: 'unavailable' as const },
    ],
    warnings: [],
    ...over,
  })

  it('renders one "This feed" card carrying the frame as tappable facets', async () => {
    await renderHomeWith(feedWith({ cards: [regionCard('a')] }))
    const feedCard = screen.getByRole('region', { name: 'This feed' })
    expect(feedCard).toBeInTheDocument()
    // From + When are facets, each a control opening its own panel.
    expect(screen.getByRole('button', { name: 'Front Royal' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Weekend morning' })).toBeInTheDocument()
  })

  it('opens the origin PanelSheet directly when the From facet is tapped', async () => {
    const user = userEvent.setup()
    const onOpenFacet = vi.fn()
    render(
      <PlannerProvider scope={ANON_SCOPE} client={readyClient(feedWith({ cards: [regionCard('a')] }))}>
        <Home
          tuning={TUNING}
          anonymous
          onOpenTuning={noop}
          onOpenFacet={onOpenFacet}
          onOpenTrail={noop}
          onOpenOutcome={noop}
          onApplyTuning={noop}
        />
      </PlannerProvider>,
    )
    await screen.findByRole('region', { name: 'This feed' })
    await user.click(screen.getByRole('button', { name: 'Front Royal' }))
    expect(onOpenFacet).toHaveBeenCalledWith('origin')
  })

  it('states the region-shared reading ONCE inside the card, and keeps the cards conditions-silent (Q2)', async () => {
    const cards = [regionCard('a'), regionCard('b'), regionCard('c')]
    const { container } = await renderHomeWith(feedWith({ cards }))

    const feedCard = screen.getByRole('region', { name: 'This feed' })
    // The shared reading appears once, in the card's right-now strip.
    expect(screen.getAllByText('Mostly Cloudy 61°F').length).toBe(1)
    expect(feedCard.textContent).toMatch(/Mostly Cloudy 61°F/)
    // The feed cards themselves say nothing about conditions (Q2).
    for (const cardEl of container.querySelectorAll('.card')) {
      expect(cardEl.textContent).not.toMatch(/Mostly Cloudy/)
    }
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
          onOpenFacet={noop}
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

describe('Home top bar + stack controls chrome (Epic 057 S1/S2)', () => {
  it('shows the quiet "Browsing" chip for an anonymous viewer', async () => {
    await renderHomeWith(feedWith({}))
    expect(screen.getByText('Browsing')).toBeInTheDocument()
  })

  it('places the Saved pill and the trail count together in the same controls row', async () => {
    const cards = [
      { id: 'compton-peak', name: 'Compton Peak', distanceMi: 2.1, conditionLines: [], warnings: [] },
      { id: 'old-rag', name: 'Old Rag', distanceMi: 3.2, conditionLines: [], warnings: [] },
    ]
    toggleTrailSaved('compton-peak')
    const { container } = await renderHomeWith(feedWith({ cards }))
    const controls = container.querySelector('.stack-controls')
    expect(controls).toContainElement(screen.getByRole('button', { name: /saved \(1\)/i }))
    expect(controls).toContainElement(screen.getByText(/2 trails/))
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

describe('Home keeps the persistent quiet .wordmark (Epic 020, AC-20.4.1)', () => {
  it('renders .wordmark — the only screen that should', async () => {
    const { container } = await renderHomeWith(feedWith({}))
    expect(container.querySelector('.wordmark')).toBeInTheDocument()
  })
})

describe('Home stale-while-revalidate disclosure (AC-3.8, Epic 039 S3)', () => {
  function seedAnonCache(feed: FeedVM, tuning: TuningState = TUNING) {
    writeFeedCache(feedKey({ tuning }, ANON_SCOPE), feed)
  }

  it('shows a calm role=status aria-live=polite note while revalidating, and does not mark the results busy', () => {
    seedAnonCache(feedWith({}))
    // hangingClient's plan() never resolves — revalidation stays in flight.
    const { container } = renderHome()

    const note = screen.getByText(/Showing your last visit/)
    expect(note).toHaveAttribute('role', 'status')
    expect(note).toHaveAttribute('aria-live', 'polite')
    expect(note.textContent).toMatch(/checking current conditions/)

    // A usable stale feed is perceivable content, not a busy wait.
    expect(container.querySelector('[aria-busy="true"]')).not.toBeInTheDocument()
  })

  it('clears the disclosure once the fresh feed resolves', async () => {
    seedAnonCache(feedWith({}))
    const freshFeed = feedWith({
      cards: [{ id: 'old-rag', name: 'Old Rag', distanceMi: 3, conditionLines: [], warnings: [] }],
    })
    render(
      <PlannerProvider scope={ANON_SCOPE} client={readyClient(freshFeed)}>
        <Home
          tuning={TUNING}
          anonymous
          onOpenTuning={noop}
          onOpenFacet={noop}
          onOpenTrail={noop}
          onOpenOutcome={noop}
          onApplyTuning={noop}
        />
      </PlannerProvider>,
    )
    await act(async () => {})

    expect(screen.queryByText(/Showing your last visit/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open Old Rag' })).toBeInTheDocument()
  })

  it('is absent on a cold load with empty storage (no cache entry to seed a stale paint)', () => {
    renderHome()
    expect(screen.queryByText(/Showing your last visit/)).not.toBeInTheDocument()
  })
})

describe('Home two-phase pending + patch-failure surfaces (Epic 040 S3)', () => {
  function pendingClient(feed: FeedVM): PlannerClient {
    return {
      plan: () => Promise.resolve({ ...feed, conditionsPending: true }),
      // Never resolves: the conditions patch stays in flight.
      planConditions: () => new Promise(() => {}),
      recentEpisodes: () => Promise.resolve([]),
    } as unknown as PlannerClient
  }

  function failingPatchClient(feed: FeedVM): PlannerClient {
    return {
      plan: () => Promise.resolve({ ...feed, conditionsPending: true }),
      planConditions: () => Promise.reject(new Error('boom')),
      recentEpisodes: () => Promise.resolve([]),
    } as unknown as PlannerClient
  }

  it('AC-3.3: fresh phase-1 cards show with a polite "Checking current conditions…" line, never busy', async () => {
    const { container } = render(
      <PlannerProvider scope={ANON_SCOPE} client={pendingClient(feedWith({}))}>
        <Home
          tuning={TUNING}
          anonymous
          onOpenTuning={noop}
          onOpenFacet={noop}
          onOpenTrail={noop}
          onOpenOutcome={noop}
          onApplyTuning={noop}
        />
      </PlannerProvider>,
    )
    await act(async () => {})

    const note = screen.getByText('Checking current conditions…')
    expect(note).toHaveAttribute('role', 'status')
    expect(note).toHaveAttribute('aria-live', 'polite')
    // The fresh cards are NOT a stale paint — the S3 line must not show.
    expect(screen.queryByText(/Showing your last visit/)).not.toBeInTheDocument()
    // Perceivable ranked cards are content, not a busy wait (aria-busy stays loading-only).
    expect(container.querySelector('[aria-busy="true"]')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open Compton Peak' })).toBeInTheDocument()
  })

  it('AC-3.4: a patch failure keeps the cards and shows the calm verify-retry note', async () => {
    render(
      <PlannerProvider scope={ANON_SCOPE} client={failingPatchClient(feedWith({}))}>
        <Home
          tuning={TUNING}
          anonymous
          onOpenTuning={noop}
          onOpenFacet={noop}
          onOpenTrail={noop}
          onOpenOutcome={noop}
          onApplyTuning={noop}
        />
      </PlannerProvider>,
    )
    await act(async () => {})

    expect(screen.getByText(/verify current conditions/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()
    // Never a blank: the phase-1 cards stay on screen behind the disclosure.
    expect(screen.getByRole('button', { name: 'Open Compton Peak' })).toBeInTheDocument()
  })
})

describe('Home Omnibox trail-name search line (Epic 038/B001 build lane)', () => {
  /** A client whose plan() resolves with the tuned feed and whose search()
   *  is the caller-supplied stub — so each test controls the search leg
   *  independently of the always-present tuned feed underneath it. */
  function clientWith(feed: FeedVM, search: PlannerClient['search']): PlannerClient {
    return {
      plan: () => Promise.resolve(feed),
      search,
      recentEpisodes: () => Promise.resolve([]),
    } as unknown as PlannerClient
  }

  async function renderHomeSearch(search: PlannerClient['search'], feed: FeedVM = feedWith({})) {
    const result = render(
      <PlannerProvider scope={ANON_SCOPE} client={clientWith(feed, search)}>
        <Home
          tuning={TUNING}
          anonymous
          onOpenTuning={noop}
          onOpenFacet={noop}
          onOpenTrail={noop}
          onOpenOutcome={noop}
          onApplyTuning={noop}
        />
      </PlannerProvider>,
    )
    await act(async () => {}) // let the tuned feed's plan() commit first
    return result
  }

  it('renders a labeled, always-visible search input at the top of the feed, its accessible name spelling out "by name" (ux-review 2026-07 Finding 3)', async () => {
    await renderHomeSearch(vi.fn())
    const input = screen.getByRole('searchbox', { name: 'Search trails, or browse below' })
    expect(input).toBeInTheDocument()
    expect(input).toHaveAttribute('placeholder', 'Trail name, e.g. “Old Rag”…')
  })

  it('submitting calls the search client with the typed query', async () => {
    const search = vi.fn().mockResolvedValue({ ...feedWith({}), cards: [] })
    await renderHomeSearch(search)

    await userEvent.type(screen.getByRole('searchbox', { name: 'Search trails, or browse below' }), 'old rag')
    await userEvent.keyboard('{Enter}')

    expect(search).toHaveBeenCalledWith('old rag', ANON_SCOPE)
  })

  it('renders the matched cards using the same card component the tuned feed uses', async () => {
    const search = vi.fn().mockResolvedValue(
      feedWith({ cards: [{ id: 'old-rag', name: 'Old Rag', distanceMi: 3, conditionLines: [], warnings: [] }] }),
    )
    await renderHomeSearch(search)

    await userEvent.type(screen.getByRole('searchbox', { name: 'Search trails, or browse below' }), 'old rag')
    await userEvent.keyboard('{Enter}')
    await act(async () => {})

    expect(screen.getByRole('button', { name: 'Open Old Rag' })).toBeInTheDocument()
    expect(screen.getByText(/1 match/)).toBeInTheDocument()
    // The tuned feed's own card (Compton Peak) is replaced while search is active.
    expect(screen.queryByRole('button', { name: 'Open Compton Peak' })).not.toBeInTheDocument()
  })

  it('shows the honest empty state naming the query when nothing matches — never fabricated', async () => {
    const search = vi.fn().mockResolvedValue({ ...feedWith({}), cards: [] })
    await renderHomeSearch(search)

    await userEvent.type(screen.getByRole('searchbox', { name: 'Search trails, or browse below' }), 'nonexistent trail xyz')
    await userEvent.keyboard('{Enter}')
    await act(async () => {})

    expect(screen.getByText('No trails match “nonexistent trail xyz”.')).toBeInTheDocument()
  })

  it('shows a calm error state mirroring the httpPlanner error mapping on failure', async () => {
    const search = vi.fn().mockResolvedValue({
      ...feedWith({}),
      cards: [],
      error: { kind: 'offline' as const, message: 'Couldn’t reach the planner. Showing nothing live right now.' },
    })
    await renderHomeSearch(search)

    await userEvent.type(screen.getByRole('searchbox', { name: 'Search trails, or browse below' }), 'old rag')
    await userEvent.keyboard('{Enter}')
    await act(async () => {})

    expect(
      screen.getByText('Couldn’t reach the planner. Showing nothing live right now.'),
    ).toBeInTheDocument()
  })

  it('shows a loading state while the search is in flight', async () => {
    const pending = new Promise<FeedVM>(() => {})
    const search = vi.fn().mockReturnValue(pending)
    await renderHomeSearch(search)

    await userEvent.type(screen.getByRole('searchbox', { name: 'Search trails, or browse below' }), 'old rag')
    await userEvent.keyboard('{Enter}')

    expect(screen.getByText('Searching…')).toBeInTheDocument()
  })

  it('restores the normal tuned feed when the search box is cleared', async () => {
    const search = vi.fn().mockResolvedValue(
      feedWith({ cards: [{ id: 'old-rag', name: 'Old Rag', distanceMi: 3, conditionLines: [], warnings: [] }] }),
    )
    await renderHomeSearch(search)

    const input = screen.getByRole('searchbox', { name: 'Search trails, or browse below' })
    await userEvent.type(input, 'old rag')
    await userEvent.keyboard('{Enter}')
    await act(async () => {})
    expect(screen.getByRole('button', { name: 'Open Old Rag' })).toBeInTheDocument()

    await userEvent.clear(input)
    await userEvent.click(screen.getByRole('button', { name: 'Clear' }))

    // Back to the normal intent/origin feed — its own card is visible again.
    expect(screen.getByRole('button', { name: 'Open Compton Peak' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Open Old Rag' })).not.toBeInTheDocument()
  })

  it('never breaks the existing tuned feed while search is idle', async () => {
    await renderHomeSearch(vi.fn())
    // The normal context sentence + card stack render exactly as before search existed.
    expect(screen.getByRole('button', { name: 'Open Compton Peak' })).toBeInTheDocument()
  })
})

describe('Home personalization-degraded banner (Q8 — disclosed, dismissible, retryable)', () => {
  it('renders only when the feed says personalization degraded', async () => {
    const { container } = await renderHomeWith(feedWith({ personalizationDegraded: true }))
    expect(container.querySelector('.personalization-degraded')).not.toBeNull()

    const clean = await renderHomeWith(feedWith({}))
    expect(clean.container.querySelector('.personalization-degraded')).toBeNull()
  })

  it('dismiss hides it; it does not resurrect on rerender', async () => {
    const { container } = await renderHomeWith(feedWith({ personalizationDegraded: true }))
    const dismiss = Array.from(container.querySelectorAll('.personalization-degraded button')).find(
      (b) => b.textContent === 'Dismiss',
    )
    expect(dismiss).toBeDefined()
    await act(async () => {
      ;(dismiss as HTMLButtonElement).click()
    })
    expect(container.querySelector('.personalization-degraded')).toBeNull()
  })

  it('retry re-runs the plan (a real refetch, not a decoration)', async () => {
    const feed = feedWith({ personalizationDegraded: true })
    const plan = vi.fn(() => Promise.resolve(feed))
    const client = { plan, recentEpisodes: () => Promise.resolve([]) } as unknown as PlannerClient
    const { container } = render(
      <PlannerProvider scope={ANON_SCOPE} client={client}>
        <Home
          tuning={TUNING}
          anonymous
          onOpenTuning={noop}
          onOpenFacet={noop}
          onOpenTrail={noop}
          onOpenOutcome={noop}
          onApplyTuning={noop}
        />
      </PlannerProvider>,
    )
    await act(async () => {})
    const before = plan.mock.calls.length
    const retry = Array.from(container.querySelectorAll('.personalization-degraded button')).find(
      (b) => b.textContent === 'Retry',
    )
    expect(retry).toBeDefined()
    await act(async () => {
      ;(retry as HTMLButtonElement).click()
    })
    await act(async () => {})
    expect(plan.mock.calls.length).toBeGreaterThan(before)
  })
})
