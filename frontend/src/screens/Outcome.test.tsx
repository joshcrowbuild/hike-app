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

describe('Outcome uses a real screen title, not the quiet .wordmark slot (Epic 020, AC-20.4.1)', () => {
  it('renders .screen-title instead of .wordmark', async () => {
    const { container } = renderOutcome('ep-hawksbill')
    await screen.findByText(/You hiked Hawksbill Summit/)
    expect(container.querySelector('.wordmark')).not.toBeInTheDocument()
    expect(container.querySelector('.screen-title')).toBeInTheDocument()
  })
})

describe('Outcome for a manual trip log (Epic 042 S2)', () => {
  async function renderManual() {
    const client = new MockPlannerClient()
    const episode = await client.logTrip({ id: 'stony-man', name: 'Stony Man Loop' }, '2026-11-13', JOSH)
    const view = render(
      <PlannerProvider scope={JOSH} client={client}>
        <Outcome episodeId={episode.id} onDone={vi.fn()} />
      </PlannerProvider>,
    )
    await screen.findByText(/You hiked Stony Man Loop/)
    return { ...view, client, episode }
  }

  it('AC-1.2: opens with the trail pre-filled', async () => {
    await renderManual()
    expect(screen.getByRole('radiogroup', { name: /how was it/i })).toBeInTheDocument()
  })

  it('AC-2.4: hides the Measured block entirely — no label, no zeros, no sample-watch strip', async () => {
    const { container } = await renderManual()
    expect(screen.queryByText('Measured')).not.toBeInTheDocument()
    expect(container.querySelector('.measured')).toBeNull()
    expect(container.querySelector('.sample-strip')).toBeNull()
    const facts = container.querySelector('.outcome-facts')
    expect(facts).toHaveTextContent(/^Today$/)
    expect(container.textContent).not.toMatch(/0\.0 mi|0 ft|0h|moving/i)
  })

  it('AC-3.1: the rating goes through the same recordOutcome call a watch episode uses', async () => {
    const user = userEvent.setup()
    const { client, episode } = await renderManual()
    const spy = vi.spyOn(client, 'recordOutcome')
    await user.click(screen.getByRole('radio', { name: 'Good' }))
    expect(await screen.findByText('Noted.')).toBeInTheDocument()
    expect(spy).toHaveBeenCalledWith(episode.id, { overall: 3, skipped: false }, [], JOSH)
  })

  it('still shows the Measured block for a watch episode (regression guard)', async () => {
    renderOutcome('ep-hawksbill')
    await screen.findByText(/You hiked Hawksbill Summit/)
    expect(screen.getByText('Measured')).toBeInTheDocument()
    expect(screen.getByText('2h 05m moving')).toBeInTheDocument()
  })
})
