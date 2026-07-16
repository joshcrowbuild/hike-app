import type { Meta, StoryObj } from '@storybook/react-vite'

import { Text } from './Text'

const meta = {
  title: 'Foundations/Text',
  component: Text,
  tags: ['autodocs'],
  args: {
    role: 'body',
    children: 'The quick brown fox jumps over the lazy dog.',
  },
} satisfies Meta<typeof Text>

export default meta
type Story = StoryObj<typeof meta>

/** `type.display` — the Detail hero name. Renders an `h1` by default. */
export const Display: Story = {
  args: { role: 'display', children: 'Old Rag Mountain Loop' },
}

/** `type.title` — the card name. Renders an `h3` by default. */
export const Title: Story = {
  args: { role: 'title', children: 'Old Rag Mountain Loop' },
}

/** `type.lead` — a context sentence / verdict prose. */
export const Lead: Story = {
  args: { role: 'lead', children: 'For tomorrow morning near Cinnamon Bay, solo.' },
}

/** `type.body` — prose (water, character). */
export const Body: Story = {
  args: { role: 'body', children: 'A rocky scramble near the summit gives way to open granite slabs.' },
}

/** `type.body-sm` — secondary + degraded copy. */
export const BodySmall: Story = {
  args: { role: 'bodySm', children: 'Conditions last checked 6 hours ago.' },
}

/**
 * `type.metric` — mono, tabular-nums. Distance / ascent / duration / coords
 * (D2 — mono for metrics only, never prose).
 */
export const Metric: Story = {
  args: { role: 'metric', children: '3.2 mi' },
}

/** `type.metric-label` — the sentence-case, muted "Distance" / "Ascent" caption beside a metric. */
export const MetricLabel: Story = {
  args: { role: 'metricLabel', children: 'Distance' },
}

/** `type.caption` — provenance, source, timestamp. */
export const Caption: Story = {
  args: { role: 'caption', children: 'NWS · 12 min ago' },
}

/** `type.overline` — the one rare kicker. The ONLY role rendered UPPERCASE. */
export const Overline: Story = {
  args: { role: 'overline', children: 'Trail conditions' },
}

/**
 * Every role side-by-side, so the closed scale is inspectable at a glance.
 * `display`/`title` are rendered `as="div"` here ONLY because this gallery is
 * not a real page — a real caller places at most one `display`/`title` inside
 * an actual heading outline (a real page never jumps h1 -> h3, which is what
 * stacking their true defaults in one demo would do).
 */
export const AllRoles: Story = {
  render: () => (
    <div style={{ display: 'grid', gap: '0.75rem' }}>
      <Text role="display" as="div">Display — hero name</Text>
      <Text role="title" as="div">Title — card name</Text>
      <Text role="lead">Lead — context sentence</Text>
      <Text role="body">Body — prose</Text>
      <Text role="bodySm">Body-sm — secondary/degraded copy</Text>
      <Text role="metric">Metric — 1,400 ft</Text>
      <Text role="metricLabel">Metric-label — Ascent</Text>
      <Text role="caption">Caption — NWS · 12 min ago</Text>
      <Text role="overline">Overline — the one rare kicker</Text>
    </div>
  ),
}
