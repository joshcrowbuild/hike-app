import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ANON_SCOPE } from '../data/api'
import { PlannerProvider } from '../data/PlannerProvider'
import { resetSavedTrailsForTests } from '../data/savedTrails'
import type { PlannerClient } from '../data/source'
import type { CardVM } from '../data/vm'
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

function readyClient(vm: CardVM): PlannerClient {
  return {
    plan: () => Promise.resolve({ query: '', cards: [], notices: [], setAside: [], heldBack: [], readiness: { on: false, state: 'off' }, dataSource: 'live' as const }),
    getCard: () => Promise.resolve(vm),
    recentEpisodes: () => Promise.resolve([]),
    getEpisode: () => Promise.resolve(null),
    recordOutcome: () => Promise.reject(new Error('not used')),
  } as unknown as PlannerClient
}

async function renderDetail(vm: CardVM) {
  const result = render(
    <PlannerProvider scope={ANON_SCOPE} client={readyClient(vm)}>
      <Detail id={vm.id} onBack={vi.fn()} onReplan={vi.fn()} />
    </PlannerProvider>,
  )
  await act(async () => {})
  return result
}

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
