import type { Meta, StoryObj } from '@storybook/react-vite'
import { Clock, Mountain, Route } from 'lucide-react'

import { MetricRow } from './MetricRow'
import type { MetricItem } from './MetricRow'

const meta = {
  title: 'Primitives/MetricRow',
  component: MetricRow,
  tags: ['autodocs'],
} satisfies Meta<typeof MetricRow>

export default meta
type Story = StoryObj<typeof meta>

const full: MetricItem[] = [
  { kind: 'distance', label: 'Distance', value: '3.2 mi', glyph: Route },
  { kind: 'ascent', label: 'Ascent', value: '1,400 ft', glyph: Mountain },
  { kind: 'duration', label: 'Duration', value: '2–3 hr', glyph: Clock },
]

/** All three facts known — mono, tabular-nums values beside their sentence-case, muted labels. */
export const Default: Story = {
  args: { items: full },
}

/** Distance known, but ascent + duration have no figure — each renders a NAMED disclosure, never a dash. */
export const PartiallyUnavailable: Story = {
  args: {
    items: [
      { kind: 'distance', label: 'Distance', value: '1.5 mi', glyph: Route },
      { kind: 'ascent', label: 'Ascent', value: null, glyph: Mountain },
      { kind: 'duration', label: 'Duration', value: null, glyph: Clock },
    ],
  },
}

/** No glyphs at all — the row still reads cleanly on labels + values alone. */
export const NoGlyphs: Story = {
  args: {
    items: [
      { kind: 'distance', label: 'Distance', value: '3.2 mi' },
      { kind: 'ascent', label: 'Ascent', value: '1,400 ft' },
      { kind: 'duration', label: 'Duration', value: '2–3 hr' },
    ],
  },
}

/** An empty item list renders nothing — there's no trail-shaped row to disclose a gap in. */
export const Empty: Story = {
  args: { items: [] },
}
