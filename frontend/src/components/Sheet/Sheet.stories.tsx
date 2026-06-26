import type { Meta, StoryObj } from '@storybook/react-vite'
import { useState } from 'react'

import { OptionButton, OptionGroup } from '../OptionGroup'
import { Sheet } from './Sheet'

const meta = {
  title: 'Primitives/Sheet',
  component: Sheet,
  parameters: { layout: 'fullscreen' },
  args: {
    isOpen: false,
    onClose: () => {},
    title: 'Effort',
    children: null,
  },
  render: (args) => {
    const [open, setOpen] = useState(false)
    const [value, setValue] = useState('moderate')
    return (
      <div style={{ padding: '1.5rem' }}>
        <button type="button" onClick={() => setOpen(true)}>
          Open sheet
        </button>
        <Sheet {...args} isOpen={open} onClose={() => setOpen(false)}>
          <OptionGroup
            label={args.title}
            value={value}
            onChange={(next) => {
              setValue(next)
              setOpen(false)
            }}
          >
            <OptionButton value="easy">Easy</OptionButton>
            <OptionButton value="moderate">Moderate</OptionButton>
            <OptionButton value="bigDay">Big day</OptionButton>
          </OptionGroup>
        </Sheet>
      </div>
    )
  },
} satisfies Meta<typeof Sheet>

export default meta
type Story = StoryObj<typeof meta>

/**
 * One concern per sheet. Opens from a trigger; React Aria provides the focus
 * trap, Escape / scrim dismiss, and focus return.
 */
export const FacetSheet: Story = {}
