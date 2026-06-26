import type { Meta, StoryObj } from '@storybook/react-vite'
import { useState } from 'react'

import { OptionButton, OptionGroup } from './OptionGroup'

const meta = {
  title: 'Primitives/OptionGroup',
  component: OptionGroup,
  tags: ['autodocs'],
  args: {
    label: 'Effort',
    value: 'moderate',
    onChange: () => {},
    children: null,
  },
  render: (args) => {
    const [value, setValue] = useState(args.value)
    return (
      <OptionGroup {...args} value={value} onChange={setValue}>
        <OptionButton value="easy">Easy</OptionButton>
        <OptionButton value="moderate">Moderate</OptionButton>
        <OptionButton value="bigDay">Big day</OptionButton>
      </OptionGroup>
    )
  },
} satisfies Meta<typeof OptionGroup>

export default meta
type Story = StoryObj<typeof meta>

/** Pick one effort. Selection is structural (ink border + weight), not accent. */
export const Effort: Story = {}
