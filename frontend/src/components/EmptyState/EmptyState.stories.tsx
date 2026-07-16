import type { Meta, StoryObj } from '@storybook/react-vite'

import { emptyFilters, emptySearch } from '../../copy/messages'
import { EmptyState } from './EmptyState'

const meta = {
  title: 'Composites/EmptyState',
  component: EmptyState,
  tags: ['autodocs'],
  args: {
    headline: 'Nothing to show.',
    secondary: 'Try loosening one thing.',
    cta: 'Reset',
    onAction: () => {},
  },
} satisfies Meta<typeof EmptyState>

export default meta
type Story = StoryObj<typeof meta>

/** Search found nothing (states-gallery.html §4 "search — no match"): sourced from `messages.emptySearch`. */
export const SearchNoMatch: Story = {
  args: {
    ...emptySearch('old rug', 'St. John', 10),
    onAction: () => {},
  },
}

/** Filters are too tight (states-gallery.html §4 "filters — too tight"): sourced from `messages.emptyFilters`,
 * whose CTA reads the resulting value ("up to 3 mi"), distinct from the secondary line's verb phrase
 * ("Widen the distance"). */
export const FiltersTooTight: Story = {
  args: {
    ...emptyFilters('a solo dawn hike under 1 mile', 'St. John', 'Widen the distance', 6, 'up to 3 mi'),
    onAction: () => {},
  },
}
