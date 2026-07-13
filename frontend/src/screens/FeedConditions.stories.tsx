import type { Meta, StoryObj } from '@storybook/react-vite'

import { FeedConditionsRibbon } from './FeedConditions'

/**
 * The feed-level conditions ribbon (ux-review-conditions-2026-07 F3/F9a):
 * region-scope facts stated once. Part of the blocking a11y gate
 * (`src/test/a11y.axe.test.tsx`) — it is a named region landmark carrying the
 * same safety-relevant honesty primitives as a card, so every silence state's
 * rendering is axe-audited here too.
 */
const meta = {
  title: 'Honesty Primitives/FeedConditionsRibbon',
  component: FeedConditionsRibbon,
  tags: ['autodocs'],
  args: {
    conditions: {
      sharedLines: [
        {
          text: 'Mostly Cloudy 61°F · NWS, just now',
          source: 'NWS api.weather.gov',
          confidence: 'stated',
          provenance: 'live',
        },
      ],
      sharedStates: [
        { kind: 'fire', state: 'no-hazard', source: 'NASA FIRMS', checkedAgo: 'just now' },
        { kind: 'closures', state: 'no-hazard', source: 'NPS', checkedAgo: 'just now' },
      ],
      sharedLineKeys: new Set<string>(),
      sharedStateKeys: new Set<string>(),
    },
  },
} satisfies Meta<typeof FeedConditionsRibbon>

export default meta
type Story = StoryObj<typeof meta>

/** A calm all-clear region: one sourced reading + one checked-clear group. */
export const RegionAllClear: Story = {}

/** The Ocracoke shape (F9a): reading + checked-clear + ONE region-wide outage
 *  statement — the three silences stay glyph + copy + treatment distinct. */
export const RegionWithOutage: Story = {
  args: {
    conditions: {
      sharedLines: [
        {
          text: 'Showers And Thunderstorms Likely 77°F · NWS, just now',
          source: 'NWS api.weather.gov',
          confidence: 'stated',
          provenance: 'live',
        },
      ],
      sharedStates: [
        { kind: 'fire', state: 'no-hazard', source: 'NASA FIRMS', checkedAgo: 'just now' },
        { kind: 'air', state: 'unavailable' },
        { kind: 'closures', state: 'not-fetched' },
      ],
      sharedLineKeys: new Set<string>(),
      sharedStateKeys: new Set<string>(),
    },
  },
}

/** Nothing region-shared → the ribbon renders nothing at all. */
export const NothingShared: Story = {
  args: {
    conditions: {
      sharedLines: [],
      sharedStates: [],
      sharedLineKeys: new Set<string>(),
      sharedStateKeys: new Set<string>(),
    },
  },
}
