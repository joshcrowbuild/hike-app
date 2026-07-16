import type { Meta, StoryObj } from '@storybook/react-vite'

import { liveOutage, personalizationDegraded, systemBannerMessages } from '../../copy/messages'
import { SystemBanner } from './SystemBanner'

const meta = {
  title: 'Composites/SystemBanner',
  component: SystemBanner,
  tags: ['autodocs'],
  args: {
    kind: 'live-outage',
    tier: 'unknown',
    message: 'Live conditions are unavailable right now.',
  },
} satisfies Meta<typeof SystemBanner>

export default meta
type Story = StoryObj<typeof meta>

/** `unknown` — a source is down. Gray, calm, never alarm-toned (Law 7). */
export const LiveOutage: Story = {
  args: {
    kind: 'live-outage',
    tier: 'unknown',
    ...liveOutage(),
  },
}

/** `unknown` — signed in but personalization failed to load; still constructive. */
export const PersonalizationDegraded: Story = {
  args: {
    kind: 'personalization-degraded',
    tier: 'unknown',
    message: personalizationDegraded().headline,
    secondary: personalizationDegraded().secondary,
  },
}

/** `headsUp` — actionable but not blocking (e.g. a regional advisory, not a closure). */
export const RegionalAlertHeadsUp: Story = {
  args: {
    kind: 'regional-alert',
    tier: 'headsUp',
    message: systemBannerMessages['regional-alert']('headsUp'),
  },
}

/** `blocked` — a genuine barrier (a regional closure). The only firm colour in the system. */
export const RegionalAlertBlocked: Story = {
  args: {
    kind: 'regional-alert',
    tier: 'blocked',
    message: systemBannerMessages['regional-alert']('blocked'),
  },
}

/** Every kind x tier combination the component actually renders, side by side. */
export const AllTiers: Story = {
  render: () => (
    <div style={{ display: 'grid', gap: '0.75rem' }}>
      <SystemBanner kind="live-outage" tier="unknown" {...liveOutage()} />
      <SystemBanner kind="regional-alert" tier="headsUp" message={systemBannerMessages['regional-alert']('headsUp')} />
      <SystemBanner kind="regional-alert" tier="blocked" message={systemBannerMessages['regional-alert']('blocked')} />
    </div>
  ),
}
