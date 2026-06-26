import type { Meta, StoryObj } from '@storybook/react-vite'

import { Confidence } from './Confidence'

const meta = {
  title: 'Honesty Primitives/Confidence',
  component: Confidence,
  tags: ['autodocs'],
  args: {
    level: 'stated',
    provenance: 'live',
    children: 'Sunny, 54°F (NWS, 12m ago)',
  },
} satisfies Meta<typeof Confidence>

export default meta
type Story = StoryObj<typeof meta>

/** High confidence: a plain, verified statement — no chrome, no hedge. */
export const Stated: Story = {}

/** Medium: quieter; the hedge ("likely") lives in the copy, not a number. */
export const Hedged: Story = {
  args: { level: 'hedged', children: 'Likely breezy this afternoon (NWS, 1h ago)' },
}

/** Low / safety-relevant: the verify accent, the only place the hue appears. */
export const Flagged: Story = {
  args: { level: 'flagged', children: 'Couldn’t confirm the creek level — verify before you go' },
}

/** Non-live data is demoted and tagged so it can never pass as verified (R1). */
export const SampleData: Story = {
  args: { level: 'stated', provenance: 'mock', children: '54°F · breezy · clear' },
}
