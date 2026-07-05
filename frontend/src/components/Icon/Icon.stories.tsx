import type { Meta, StoryObj } from '@storybook/react-vite'
import { Car, Clock, Mountain, Route } from 'lucide-react'

import { Icon } from './Icon'

const meta = {
  title: 'Foundations/Icon',
  component: Icon,
  tags: ['autodocs'],
  args: {
    glyph: Car,
    label: 'Drive',
  },
} satisfies Meta<typeof Icon>

export default meta
type Story = StoryObj<typeof meta>

/** A bare glyph — aria-hidden, with its meaning carried by the sr-only label. */
export const Default: Story = {}

/**
 * As a LEADING ACCENT beside its word — never a replacement (Epic 021). The word
 * always stays; the glyph inherits the surrounding ink via currentColor.
 */
export const AsFactAccent: Story = {
  render: () => (
    <div style={{ display: 'grid', gap: '0.6rem', fontFamily: 'system-ui' }}>
      {[
        { glyph: Route, label: 'Distance', value: '3.2 mi' },
        { glyph: Car, label: 'Drive', value: '35 min' },
        { glyph: Mountain, label: 'Ascent', value: '1,400 ft' },
        { glyph: Clock, label: 'Duration', value: '2–3 hr' },
      ].map((f) => (
        <span key={f.label} style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3rem' }}>
          <Icon glyph={f.glyph} label={f.label} />
          {f.label}
          <span style={{ marginInlineStart: '0.4rem', fontFamily: 'ui-monospace, monospace' }}>{f.value}</span>
        </span>
      ))}
    </div>
  ),
}
