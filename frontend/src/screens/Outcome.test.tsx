import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { ScopeContext } from '../data/api'
import { MockPlannerClient } from '../data/mock/mockPlanner'
import { PlannerProvider } from '../data/PlannerProvider'
import { Outcome } from './Outcome'

const JOSH: ScopeContext = { viewerId: 'josh', grantedIds: [] }

function renderOutcome(episodeId: string, onDone = vi.fn()) {
  return render(
    <PlannerProvider scope={JOSH} client={new MockPlannerClient()}>
      <Outcome episodeId={episodeId} onDone={onDone} />
    </PlannerProvider>,
  )
}

describe('Outcome', () => {
  it('shows measured facts as already-known and asks the single question (R3 — no delta)', async () => {
    renderOutcome('ep-hawksbill')
    expect(await screen.findByText(/You hiked Hawksbill Summit/)).toBeInTheDocument()
    // The rating is a single-select radiogroup, not toggle buttons.
    expect(screen.getByRole('radiogroup', { name: /how was it/i })).toBeInTheDocument()
    expect(screen.getAllByRole('radio')).toHaveLength(3)
    // No fabricated delta question is ever shown.
    expect(screen.queryByText(/we figured|anything slow it down/i)).not.toBeInTheDocument()
  })

  it('records one tap and announces the acknowledgment via a live region (WCAG 4.1.3)', async () => {
    const user = userEvent.setup()
    renderOutcome('ep-hawksbill')
    await screen.findByText(/You hiked Hawksbill Summit/)
    await user.click(screen.getByRole('radio', { name: 'Good' }))
    const ack = await screen.findByText('Noted.')
    expect(ack).toBeInTheDocument()
    expect(ack.closest('[role="status"]')).not.toBeNull()
  })

  it('offers an anonymous viewer the on-ramp rather than a fabricated episode (R7)', async () => {
    render(
      <PlannerProvider scope={{ viewerId: 'anonymous', grantedIds: [] }} client={new MockPlannerClient()}>
        <Outcome episodeId="ep-hawksbill" onDone={vi.fn()} />
      </PlannerProvider>,
    )
    expect(await screen.findByText(/Sign in to log your hikes/)).toBeInTheDocument()
  })
})
