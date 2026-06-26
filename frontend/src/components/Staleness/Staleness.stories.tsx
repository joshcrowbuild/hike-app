import type { Meta, StoryObj } from '@storybook/react-vite'

import { Staleness } from './Staleness'

const meta = {
  title: 'Honesty Primitives/Staleness',
  component: Staleness,
  tags: ['autodocs'],
  args: {
    children: '48m old',
  },
} satisfies Meta<typeof Staleness>

export default meta
type Story = StoryObj<typeof meta>

/** Fresh: a quiet relative-time line in the meta tier. */
export const Fresh: Story = {}

/** Stale: demoted presentation (lighter, italic) — never reordered (Rule #2). */
export const Stale: Story = {
  args: { stale: true, children: 'from a hike last fall' },
}
