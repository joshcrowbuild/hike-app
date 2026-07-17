import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { ConditionChipModel } from '../design/contracts'
import type { RegionConditionsVM } from '../data/vm'
import * as chipStyles from './ConditionChip.css'
import { ThisFeedCard, type ThisFeedCardProps } from './ThisFeedCard'

const forecast: NonNullable<RegionConditionsVM['forecast']> = {
  days: [
    { key: 'today', label: 'Today', highF: 88, precipPct: 0, short: 'Sunny' },
    { key: 'sat', label: 'Sat', highF: 68, precipPct: 20, short: 'Partly sunny' },
    { key: 'sun', label: 'Sun', highF: 71, precipPct: 10, short: 'Mostly sunny' },
  ],
  targetKey: 'sat',
  source: 'NWS',
  fetchedAgo: 'just now',
}

const recentPrecip: NonNullable<RegionConditionsVM['recentPrecip']> = {
  days: [
    { label: 'Thu', amountIn: 0.8 },
    { label: 'Fri', amountIn: 0.4 },
    { label: 'Today', amountIn: 0 },
  ],
  total48hIn: 1.2,
  source: 'NWS observations',
}

const mud: NonNullable<RegionConditionsVM['mud']> = {
  statement: 'Trails may be muddy',
  evidence: '1.2" of rain in the last 48h',
  source: 'NWS observations',
  provenance: 'inferred',
}

const currentChips: ConditionChipModel[] = [{ kind: 'air', valueText: 'AQI 54', state: 'fresh', tier: 'clear' }]

function props(over: Partial<ThisFeedCardProps> = {}): ThisFeedCardProps {
  return {
    originLabel: 'Front Royal',
    when: 'Weekend morning',
    party: 'Solo',
    effort: 'Moderate',
    anonymous: false,
    onOpenFacet: vi.fn(),
    regionConditions: { forecast, recentPrecip, mud },
    currentChips,
    conditionsPending: false,
    onRefresh: vi.fn(),
    ...over,
  }
}

describe('ThisFeedCard — the facet stack (S1)', () => {
  it('names the card and stacks From / When / Party / Effort as tappable facets', () => {
    render(<ThisFeedCard {...props()} />)
    expect(screen.getByRole('region', { name: 'This feed' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Front Royal' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Weekend morning' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Solo' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Moderate' })).toBeInTheDocument()
  })

  it('opens the matching PanelSheet facet on tap', async () => {
    const user = userEvent.setup()
    const onOpenFacet = vi.fn()
    render(<ThisFeedCard {...props({ onOpenFacet })} />)
    await user.click(screen.getByRole('button', { name: 'Front Royal' }))
    expect(onOpenFacet).toHaveBeenLastCalledWith('origin')
    await user.click(screen.getByRole('button', { name: 'Weekend morning' }))
    expect(onOpenFacet).toHaveBeenLastCalledWith('when')
    await user.click(screen.getByRole('button', { name: 'Solo' }))
    expect(onOpenFacet).toHaveBeenLastCalledWith('party')
    await user.click(screen.getByRole('button', { name: 'Moderate' }))
    expect(onOpenFacet).toHaveBeenLastCalledWith('effort')
  })

  it('hides Party / Effort for anonymous viewers (world facets only)', () => {
    render(<ThisFeedCard {...props({ anonymous: true, party: undefined, effort: undefined })} />)
    expect(screen.getByRole('button', { name: 'Front Royal' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Solo' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Moderate' })).not.toBeInTheDocument()
  })
})

describe('ThisFeedCard — forecast zone + day toggle (S2)', () => {
  it('defaults the toggle to the frame’s target day and shows its reading', () => {
    render(<ThisFeedCard {...props()} />)
    const toggle = screen.getByRole('group', { name: 'Forecast day' })
    expect(within(toggle).getByRole('button', { name: 'Sat' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText('68°F')).toBeInTheDocument()
    expect(screen.getByText('20%')).toBeInTheDocument()
  })

  it('switches days on the client with no refetch (onRefresh never fires)', async () => {
    const user = userEvent.setup()
    const onRefresh = vi.fn()
    render(<ThisFeedCard {...props({ onRefresh })} />)
    const toggle = screen.getByRole('group', { name: 'Forecast day' })
    await user.click(within(toggle).getByRole('button', { name: 'Today' }))
    expect(screen.getByText('88°F')).toBeInTheDocument()
    expect(screen.queryByText('68°F')).not.toBeInTheDocument()
    expect(onRefresh).not.toHaveBeenCalled()
  })

  it('renders skeleton chips while pending and a muted line on degrade — never a fabricated value', () => {
    const { container, rerender } = render(
      <ThisFeedCard {...props({ regionConditions: null, conditionsPending: true, currentChips: [] })} />,
    )
    expect(container.querySelector(`.${chipStyles.state.pending}`)).toBeInTheDocument()
    rerender(<ThisFeedCard {...props({ regionConditions: { forecast: null }, conditionsPending: false, currentChips: [] })} />)
    expect(screen.getByText('Forecast unavailable right now')).toBeInTheDocument()
  })
})

describe('ThisFeedCard — right-now zone (S3)', () => {
  it('renders the region-shared current chips with a "current" tag', () => {
    render(<ThisFeedCard {...props()} />)
    expect(screen.getByText('AQI 54')).toBeInTheDocument()
    expect(screen.getByText('current')).toBeInTheDocument()
  })

  it('caveats "may change by ‹day›" only when the frame targets a future day', () => {
    const { rerender } = render(<ThisFeedCard {...props()} />)
    expect(screen.getByText(/may change by Sat/)).toBeInTheDocument()
    rerender(
      <ThisFeedCard {...props({ regionConditions: { forecast: { ...forecast, targetKey: 'today' } } })} />,
    )
    expect(screen.queryByText(/may change by/)).not.toBeInTheDocument()
  })

  it('fires the one on-demand refetch from the Refresh action (Q10)', async () => {
    const user = userEvent.setup()
    const onRefresh = vi.fn()
    render(<ThisFeedCard {...props({ onRefresh })} />)
    await user.click(screen.getByRole('button', { name: /refresh/i }))
    expect(onRefresh).toHaveBeenCalledTimes(1)
  })
})

describe('ThisFeedCard — past 3 days + mud (S4)', () => {
  it('keeps the reveal collapsed by default and opens the recent-rain row on tap', async () => {
    const user = userEvent.setup()
    render(<ThisFeedCard {...props()} />)
    const toggle = screen.getByRole('button', { name: /past 3 days/i })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('Rain, last 3 days')).not.toBeInTheDocument()
    await user.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('Rain, last 3 days')).toBeInTheDocument()
    expect(screen.getByText('0.8"')).toBeInTheDocument()
  })

  it('renders the hedged mud read ONLY when mud is present', async () => {
    const user = userEvent.setup()
    const { rerender } = render(<ThisFeedCard {...props()} />)
    await user.click(screen.getByRole('button', { name: /past 3 days/i }))
    expect(screen.getByText('Trails may be muddy')).toBeInTheDocument()
    expect(screen.getByText('inferred')).toBeInTheDocument()

    // Re-render with mud removed; the reveal stays open (client state persists),
    // so the recent-rain row is still shown but the mud read is gone.
    rerender(<ThisFeedCard {...props({ regionConditions: { forecast, recentPrecip, mud: null } })} />)
    expect(screen.getByText('Rain, last 3 days')).toBeInTheDocument()
    expect(screen.queryByText('Trails may be muddy')).not.toBeInTheDocument()
  })

  it('renders no reveal at all when there is no recent-precip data', () => {
    render(<ThisFeedCard {...props({ regionConditions: { forecast, recentPrecip: null, mud: null } })} />)
    expect(screen.queryByRole('button', { name: /past 3 days/i })).not.toBeInTheDocument()
  })
})
