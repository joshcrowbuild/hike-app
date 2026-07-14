import type { Meta, StoryObj } from '@storybook/react';
import { MobileHomePrototype, DesktopHomePrototype } from './VisionPrototype';

const meta = {
  title: 'Screens/VisionPrototype',
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta;

export default meta;

export const Mobile: StoryObj = {
  render: () => <MobileHomePrototype />,
  parameters: {
    viewport: {
      defaultViewport: 'mobile1',
    },
  },
};

export const Desktop: StoryObj = {
  render: () => <DesktopHomePrototype />,
  parameters: {
    viewport: {
      defaultViewport: 'desktop',
    },
  },
};
