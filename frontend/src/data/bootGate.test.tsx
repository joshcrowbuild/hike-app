import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

// Force the live-HTTP path (the only mode with a gate) and hold /regions in
// its loading state forever — the exact window a Render cold start occupies.
vi.mock('./useMock', () => ({ USE_MOCK: false, shouldUseMock: () => false }))
vi.mock('./regionsCatalog', () => ({
  useOrigins: () => ({ origins: [], loading: true }),
  originCoordsMap: () => ({}),
}))

import { ANON_SCOPE } from './api'
import { PlannerProvider } from './PlannerProvider'

describe('PlannerProvider cold-start gate (craft review H1 — the first paint is the designed shell)', () => {
  it('renders the BootShell — chrome + staged copy — never the bare unstyled "Loading…" string', () => {
    const { container } = render(
      <PlannerProvider scope={ANON_SCOPE}>
        <div data-testid="app-ready" />
      </PlannerProvider>,
    )

    // The app stays gated while /regions is unresolved…
    expect(screen.queryByTestId('app-ready')).toBeNull()
    // …but the gate is the designed shell: wordmark topbar, staged status
    // copy, skeleton cards — not a raw UA-styled paragraph.
    expect(screen.getByRole('status')).toHaveTextContent('Reading conditions…')
    expect(screen.getByText('Curation')).toBeInTheDocument()
    expect(container.querySelectorAll('.skeleton-card').length).toBeGreaterThan(0)
    expect(screen.queryByText('Loading…')).toBeNull()
    expect(container.querySelector('.app-loading')).toBeNull()
  })
})
