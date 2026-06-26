import type { Preview } from '@storybook/react-vite'

// Load the generated token custom properties + base canvas so every story
// renders against the real matte-cartographic surface, not Storybook defaults.
import '../src/design/tokens.css'
import '../src/styles.css'

const preview: Preview = {
  parameters: {
    layout: 'padded',
    controls: { expanded: true },
    // Run axe on every story; the design system is a product with a11y tests.
    a11y: { test: 'todo' },
  },
}

export default preview
