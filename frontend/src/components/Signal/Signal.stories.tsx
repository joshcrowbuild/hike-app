import type { Meta, StoryObj } from '@storybook/react-vite'

import { Signal } from './Signal'

const meta = {
  title: 'Honesty Primitives/Signal',
  component: Signal,
  tags: ['autodocs'],
  args: {
    children: 'Verify creek crossings — running high after rain.',
  },
} satisfies Meta<typeof Signal>

export default meta
type Story = StoryObj<typeof meta>

/** The default verify-before-you-go line, as it rides beside the decision facts. */
export const Default: Story = {}

/** A staleness-flavoured caution — the message, not colour, carries the meaning. */
export const StaleClosure: Story = {
  args: { children: 'Closure info here is older than usual.' },
}

/** The visually-hidden lead-in is configurable for assistive-tech framing. */
export const CustomLeadIn: Story = {
  args: { label: 'Verify before you go', children: 'Trail may be icy above the falls.' },
}
