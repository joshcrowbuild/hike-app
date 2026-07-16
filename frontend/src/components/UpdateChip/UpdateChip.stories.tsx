import type { Meta, StoryObj } from '@storybook/react-vite'

import { UpdateChip } from './UpdateChip'

const meta = {
  title: 'Composites/UpdateChip',
  component: UpdateChip,
  tags: ['autodocs'],
} satisfies Meta<typeof UpdateChip>

export default meta
type Story = StoryObj<typeof meta>

/** The default background-revalidate copy (`messages.stalePaint()`), shown behind a cache-first
 * repaint (states-gallery.html §5 "after — instant from cache"). Pulses unless the OS has
 * `prefers-reduced-motion` set — toggle that OS setting to see the static fallback. */
export const Default: Story = {}

/** The two-phase pending variant (Epic 040): the feed-level "still checking" line, same chip. */
export const CheckingConditions: Story = {
  args: { label: 'Checking current conditions…' },
}
