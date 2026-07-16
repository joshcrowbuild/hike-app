import type { Meta, StoryObj } from '@storybook/react-vite'

import { Button } from './Button'

const meta = {
  title: 'Primitives/Button',
  component: Button,
  tags: ['autodocs'],
  args: {
    variant: 'primary',
    size: 'md',
    children: 'Save trail',
  },
} satisfies Meta<typeof Button>

export default meta
type Story = StoryObj<typeof meta>

/** The filled-ink primary action. */
export const Primary: Story = {}

/** The outlined secondary action. */
export const Secondary: Story = {
  args: { variant: 'secondary', children: 'View evidence' },
}

/** The bare, quiet ghost action — recovery/reversible actions (retry, widen, show anyway). */
export const Ghost: Story = {
  args: { variant: 'ghost', children: 'Retry' },
}

/** The compact size — still holds the 44px minimum hit target via an invisible extension. */
export const Small: Story = {
  args: { size: 'sm', children: 'Edit' },
}

/** `isDisabled` flattens each variant onto a quiet, muted treatment — never a raw opacity fade. */
export const Disabled: Story = {
  args: { isDisabled: true, children: 'Save trail' },
}

/** Every variant x size x disabled-state combination, for a single visual acceptance pass. */
export const AllVariantsAndStates: Story = {
  render: () => (
    <div style={{ display: 'grid', gap: '1rem' }}>
      <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
        <Button variant="primary" size="md">Primary md</Button>
        <Button variant="primary" size="sm">Primary sm</Button>
        <Button variant="primary" size="md" isDisabled>Primary disabled</Button>
      </div>
      <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
        <Button variant="secondary" size="md">Secondary md</Button>
        <Button variant="secondary" size="sm">Secondary sm</Button>
        <Button variant="secondary" size="md" isDisabled>Secondary disabled</Button>
      </div>
      <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
        <Button variant="ghost" size="md">Ghost md</Button>
        <Button variant="ghost" size="sm">Ghost sm</Button>
        <Button variant="ghost" size="md" isDisabled>Ghost disabled</Button>
      </div>
      <p style={{ fontSize: '0.8rem', color: '#5e636a' }}>
        Hover / press / keyboard-focus states are driven by React Aria's state
        machine (data-hovered / data-pressed / data-focus-visible) — interact
        with the controls above (or Tab to them) to see each treatment.
      </p>
    </div>
  ),
}
