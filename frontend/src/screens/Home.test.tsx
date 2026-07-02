import { act, render, screen } from '@testing-library/react'
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
