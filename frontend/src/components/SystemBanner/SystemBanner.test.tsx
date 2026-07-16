import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { liveOutage, systemBannerMessages } from '../../copy/messages'
import * as styles from './SystemBanner.css'
import { SystemBanner } from './SystemBanner'

describe('SystemBanner', () => {
  it('renders the message', () => {
    render(<SystemBanner kind="live-outage" tier="unknown" message="Live conditions are unavailable right now." />)
    expect(screen.getByText('Live conditions are unavailable right now.')).toBeInTheDocument()
  })

  it('announces itself to assistive tech as a status region', () => {
    const { container } = render(<SystemBanner kind="live-outage" tier="unknown" message="x" />)
    expect(container.querySelector('[role="status"]')).toBeInTheDocument()
  })

  it('carries a visually-hidden tier cue beyond colour (Law 7 — colour is never the only signal)', () => {
    render(<SystemBanner kind="regional-alert" tier="blocked" message="Regional closure — check before you go." />)
    expect(screen.getByText('Blocked')).toBeInTheDocument()
  })

  it.each([
    ['unknown', styles.tier.unknown],
    ['headsUp', styles.tier.headsUp],
    ['blocked', styles.tier.blocked],
  ] as const)('applies the %s tier class', (tier, expectedClass) => {
    const { container } = render(<SystemBanner kind="live-outage" tier={tier} message="x" />)
    expect(container.firstElementChild?.className).toContain(expectedClass)
  })

  it('never applies a heads-up/blocked colour class to the unknown tier (unknown is gray, never red)', () => {
    const { container } = render(<SystemBanner kind="live-outage" tier="unknown" message="x" />)
    const cls = container.firstElementChild?.className ?? ''
    expect(cls).not.toContain(styles.tier.headsUp)
    expect(cls).not.toContain(styles.tier.blocked)
  })

  it('renders an optional secondary detail line', () => {
    const copy = liveOutage()
    render(<SystemBanner kind="live-outage" tier="unknown" message={copy.message} secondary={copy.secondary} />)
    expect(screen.getByText(copy.message)).toBeInTheDocument()
    expect(screen.getByText(copy.secondary)).toBeInTheDocument()
  })

  it('renders no secondary line when none is passed', () => {
    const { container } = render(<SystemBanner kind="live-outage" tier="unknown" message="x" />)
    expect(container.querySelectorAll('p')).toHaveLength(1)
  })

  it('renders the tiered systemBannerMessages copy for each kind', () => {
    render(
      <SystemBanner
        kind="personalization-degraded"
        tier="unknown"
        message={systemBannerMessages['personalization-degraded']('unknown')}
      />,
    )
    expect(
      screen.getByText("We couldn't reach your saved preferences. Showing general picks."),
    ).toBeInTheDocument()
  })

  it('forwards a className alongside the base/tier classes', () => {
    const { container } = render(<SystemBanner kind="live-outage" tier="unknown" message="x" className="placed" />)
    expect(container.firstElementChild?.className).toContain('placed')
  })
})
