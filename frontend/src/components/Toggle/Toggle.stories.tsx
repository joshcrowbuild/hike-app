import type { Meta, StoryObj } from '@storybook/react-vite'
import { useState } from 'react'

import { Toggle } from './Toggle'

const meta = {
  title: 'Primitives/Toggle',
  component: Toggle,
  tags: ['autodocs'],
  args: {
    label: 'Match today’s readiness',
    description: 'Hide what today can’t support. Off unless you turn it on.',
    isSelected: false,
    onChange: () => {},
  },
  render: (args) => {
    const [on, setOn] = useState(args.isSelected)
    return <Toggle {...args} isSelected={on} onChange={setOn} />
  },
} satisfies Meta<typeof Toggle>

export default meta
type Story = StoryObj<typeof meta>

/** The readiness filter — off by default, user-initiated, plain about what it does. */
export const ReadinessFilter: Story = {}

export const On: Story = { args: { isSelected: true } }
