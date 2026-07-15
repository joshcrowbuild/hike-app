import type { Meta, StoryObj } from '@storybook/react';
import { MobileHomePrototype, DesktopHomePrototype, createMockCard } from './VisionPrototype';
import React from 'react';

const meta = {
  title: 'Screens/VisionPrototype',
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta;

export default meta;

const confidentCard = createMockCard(
  'card-1',
  'Fox Hollow Trail',
  3.0,
  278,
  35,
  [], // no warnings
  [
    { kind: 'weather', state: 'present', source: 'NWS' },
    { kind: 'fire', state: 'no-hazard', source: 'FIRMS', checkedAgo: '2h ago' }
  ]
);

const hedgedCard = createMockCard(
  'card-2',
  'Hammock Hills',
  3.3,
  450,
  55,
  [], // no warnings
  [
    { kind: 'weather', state: 'stale-degraded', source: 'NWS', checkedAgo: '12h ago' },
    { kind: 'air', state: 'unavailable' }
  ]
);

const warnedCard = createMockCard(
  'card-3',
  'Virginia Capital',
  0.7,
  50,
  15,
  [
    { text: 'Trailhead access road is washed out', source: 'NPS', observedAgo: '2h ago', kind: 'closures', provenance: 'live' }
  ],
  [
    { kind: 'weather', state: 'present', source: 'NWS' }
  ]
);

export const ConfidentCall: StoryObj = {
  render: () => <MobileHomePrototype 
    card={confidentCard} 
    confidenceMode="confident" 
    headline="Good to go — nothing flagged across 6 checks" 
  />,
  parameters: {
    viewport: {
      defaultViewport: 'mobile1',
    },
  },
};

export const HedgedCall: StoryObj = {
  render: () => <MobileHomePrototype 
    card={hedgedCard} 
    confidenceMode="hedged" 
    headline="Good to go — seems clear, but storms possible" 
  />,
  parameters: {
    viewport: {
      defaultViewport: 'mobile1',
    },
  },
};

export const WarnedCall: StoryObj = {
  render: () => <MobileHomePrototype 
    card={warnedCard} 
    confidenceMode="flagged" 
    headline="Heads up — Trailhead access road is washed out" 
  />,
  parameters: {
    viewport: {
      defaultViewport: 'mobile1',
    },
  },
};

export const PendingState: StoryObj = {
  render: () => <MobileHomePrototype 
    card={confidentCard} 
    confidenceMode="pending" 
  />,
  parameters: {
    viewport: {
      defaultViewport: 'mobile1',
    },
  },
};

export const EmptySearch: StoryObj = {
  render: () => <MobileHomePrototype empty={true} />,
  parameters: {
    viewport: {
      defaultViewport: 'mobile1',
    },
  },
};

export const DesktopConfident: StoryObj = {
  render: () => <DesktopHomePrototype 
    card={confidentCard} 
    confidenceMode="confident" 
    headline="Good to go — nothing flagged across 6 checks" 
  />,
  parameters: {
    viewport: {
      defaultViewport: 'desktop',
    },
  },
};
