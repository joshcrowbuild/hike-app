import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { Home } from './Home'
import { PlannerProvider } from '../data/PlannerProvider'
import { ANON_SCOPE } from '../data/api'
import type { PlannerClient } from '../data/source'
import type { FeedVM } from '../data/vm'
import type { TuningState } from '../types'

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

describe('Home cold-start loading copy', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('shows "Reading conditions…" first, then "Waking the server…" after the slow mark', () => {
    renderHome()

    expect(screen.getByText('Reading conditions…')).toBeInTheDocument()
    expect(screen.queryByText(/Waking the server/)).not.toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(8_000)
    })

    expect(screen.getByText(/Waking the server/)).toBeInTheDocument()
    expect(screen.queryByText('Reading conditions…')).not.toBeInTheDocument()
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

async function renderHomeWith(feed: FeedVM) {
  render(
    <PlannerProvider scope={ANON_SCOPE} client={readyClient(feed)}>
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
  await act(async () => {}) // let the resolved plan() commit
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

describe('Home region tag tracks the selected origin (fixes the stuck "Shenandoah" label)', () => {
  it('shows the Outer Banks region once the origin is Nags Head, not the Shenandoah default', async () => {
    const nagsHeadTuning: TuningState = { ...TUNING, origin: 'nagsHead' }
    render(
      <PlannerProvider scope={ANON_SCOPE} client={readyClient(feedWith({}))}>
        <Home
          tuning={nagsHeadTuning}
          anonymous
          onOpenTuning={noop}
          onOpenTrail={noop}
          onOpenOutcome={noop}
          onApplyTuning={noop}
        />
      </PlannerProvider>,
    )
    await act(async () => {})

    // Both the context sentence and the stack-meta count carry the region tag —
    // both must track the selected origin, not the Shenandoah default.
    expect(screen.getAllByText(/Outer Banks/).length).toBeGreaterThan(0)
    expect(screen.queryByText(/Shenandoah/)).not.toBeInTheDocument()
  })

  it('keeps the Shenandoah tag for a Shenandoah origin like Front Royal', async () => {
    await renderHomeWith(feedWith({}))
    expect(screen.getAllByText(/Shenandoah/).length).toBeGreaterThan(0)
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
      vi.advanceTimersByTime(8_000)
    })
    expect(screen.getByText(/Waking the server/)).toBeInTheDocument()
    expect(container.querySelectorAll('.skeleton-card').length).toBe(3)
    vi.useRealTimers()
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
