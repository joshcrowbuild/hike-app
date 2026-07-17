import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'

import App from './App'
import { ANON_SCOPE } from './data/api'
import { resetFeedCacheForTests } from './data/feedCache'
import { MockPlannerClient } from './data/mock/mockPlanner'
import { PlannerProvider } from './data/PlannerProvider'
import { readStoredTuning, resetStoredTuningForTests, writeStoredTuning } from './data/tuningStorage'
import type { TuningState } from './types'

const BASE: TuningState = {
  origin: 'frontRoyal',
  when: 'weekendMorning',
  effort: 'moderate',
  party: 'solo',
  today: 'standard',
  readinessOn: false,
  prompt: '',
}

function renderApp() {
  return render(
    <PlannerProvider scope={ANON_SCOPE} client={new MockPlannerClient()}>
      <App />
    </PlannerProvider>,
  )
}

afterEach(() => {
  resetStoredTuningForTests()
  resetFeedCacheForTests()
  window.location.hash = ''
})

describe('App tuning persistence (craft review M4 — no amnesia on reload)', () => {
  it('boots from the persisted frame: a stored Luray origin paints as the From facet, not the default', async () => {
    writeStoredTuning({ ...BASE, origin: 'luray' })
    renderApp()
    expect(await screen.findByRole('button', { name: 'Luray' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Front Royal' })).toBeNull()
  })

  it('persists an origin change the moment it is applied (From facet → pick)', async () => {
    const user = userEvent.setup()
    renderApp()
    // The From facet opens the origin PanelSheet directly (no Adjust hub).
    await user.click(await screen.findByRole('button', { name: 'Front Royal' }))

    const originSheet = await screen.findByRole('dialog', { name: 'Starting point' })
    await user.click(within(originSheet).getByRole('radio', { name: 'Duck, Outer Banks' }))

    await waitFor(() => expect(readStoredTuning()?.origin).toBe('duck'))
  })

  it('falls back to the built-in default when the persisted origin no longer exists in the catalog', async () => {
    writeStoredTuning({ ...BASE, origin: 'a-region-since-removed' })
    renderApp()
    // Once the catalog loads, the unknown key resolves to the default origin
    // (and the corrected frame is what gets re-persisted).
    expect(await screen.findByRole('button', { name: 'Front Royal' })).toBeInTheDocument()
    await waitFor(() => expect(readStoredTuning()?.origin).toBe('frontRoyal'))
  })
})
