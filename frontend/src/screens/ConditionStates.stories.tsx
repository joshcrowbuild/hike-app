import type { Meta, StoryObj } from '@storybook/react-vite'

import { ConditionStates } from './ConditionStates'

/**
 * The six per-kind condition states (Epic 018 S4f / CDP-02). Every state gets
 * its own story — this file is part of the blocking a11y CI gate
 * (`src/test/a11y.axe.test.tsx`), so each disposition's rendering is axe-audited
 * with its real story args. Checked-clear must read as CALM sourced silence
 * (never a loud "0 detections"), and not-fetched must read visibly different
 * from an outage (unavailable).
 */
const meta = {
  title: 'Honesty Primitives/ConditionStates',
  component: ConditionStates,
  tags: ['autodocs'],
  args: {
    conditions: [{ kind: 'weather', state: 'present', source: 'NWS', checkedAgo: '12m ago' }],
  },
} satisfies Meta<typeof ConditionStates>

export default meta
type Story = StoryObj<typeof meta>

/** A sourced fact renders as a line; the coverage row quietly confirms it. */
export const Present: Story = {}

/** Past its freshness horizon: still shown, wearing its age — never silently dropped. */
export const StaleDegraded: Story = {
  args: {
    conditions: [{ kind: 'water', state: 'stale-degraded', source: 'USGS', checkedAgo: '3h ago' }],
  },
}

/** Checked-clear: calm sourced silence — source + age kept, no "0 detections" noise. */
export const NoHazard: Story = {
  args: {
    conditions: [{ kind: 'fire', state: 'no-hazard', source: 'NASA FIRMS', checkedAgo: '20m ago' }],
  },
}

/** A sourced coverage gap, carrying the adapter's own disclosure. */
export const NoData: Story = {
  args: {
    conditions: [
      {
        kind: 'water',
        state: 'no-data',
        source: 'USGS',
        checkedAgo: '15m ago',
        detail: 'no gauge within 30 mi',
      },
    ],
  },
}

/** Probed, no answer: the flagged couldn't-verify — loud where not-fetched is quiet. */
export const Unavailable: Story = {
  args: {
    conditions: [{ kind: 'weather', state: 'unavailable' }],
  },
}

/** Not probed in this deployment: a quiet open loop, visibly NOT an outage. */
export const NotFetched: Story = {
  args: {
    conditions: [{ kind: 'air', state: 'not-fetched' }],
  },
}

/** Detail's full coverage list: every kind's disposition, all six states at once. */
export const FullCoverage: Story = {
  args: {
    conditions: [
      { kind: 'weather', state: 'present', source: 'NWS', checkedAgo: '12m ago' },
      { kind: 'air', state: 'stale-degraded', source: 'EPA AirNow', checkedAgo: '3h ago' },
      { kind: 'fire', state: 'no-hazard', source: 'NASA FIRMS', checkedAgo: '20m ago' },
      { kind: 'water', state: 'no-data', source: 'USGS', checkedAgo: '15m ago', detail: 'no gauge within 30 mi' },
      { kind: 'closures', state: 'unavailable' },
      { kind: 'permits', state: 'not-fetched' },
    ],
  },
}

/** The card's compact grouped summary — one calm row per state, kinds joined. */
export const CompactSummary: Story = {
  args: {
    compact: true,
    conditions: [
      { kind: 'fire', state: 'no-hazard', source: 'NASA FIRMS', checkedAgo: '20m ago' },
      { kind: 'closures', state: 'no-hazard', source: 'NPS', checkedAgo: '1h ago' },
      { kind: 'water', state: 'no-data', source: 'USGS' },
      { kind: 'weather', state: 'unavailable' },
      { kind: 'air', state: 'not-fetched' },
      { kind: 'permits', state: 'not-fetched' },
    ],
  },
}
