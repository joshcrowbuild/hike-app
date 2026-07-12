import { render } from '@testing-library/react'
import { composeStories, setProjectAnnotations } from '@storybook/react-vite'
import axe from 'axe-core'
import { describe, expect, it } from 'vitest'

import * as preview from '../../.storybook/preview'
import * as ConfidenceStories from '../components/Confidence/Confidence.stories'
import * as SignalStories from '../components/Signal/Signal.stories'
import * as StalenessStories from '../components/Staleness/Staleness.stories'
import * as ConditionStatesStories from '../screens/ConditionStates.stories'

// The a11y baseline gate (path-to-complete §Phase B): every story of the
// safety-relevant honesty primitives — Confidence (hedge/flag presentation),
// Signal (verify-before-you-go), Staleness (demoted-not-reordered) — must be
// axe-clean. These are the components a user relies on to judge whether a
// fact is trustworthy, so they must survive assistive tech, not just sight.
// Generic chrome (Sheet, Toggle, OptionGroup, Icon) is out of scope here.
setProjectAnnotations([preview.default])

const suites = [
  ['Confidence', composeStories(ConfidenceStories)],
  ['Signal', composeStories(SignalStories)],
  ['Staleness', composeStories(StalenessStories)],
  // The six per-kind condition states (Epic 018 S4f) are the same
  // safety-relevant honesty surface: a user reads them to judge whether an
  // absent condition was checked-clear, unreachable, or never checked.
  ['ConditionStates', composeStories(ConditionStatesStories)],
] as const

async function runAxe(container: HTMLElement) {
  return axe.run(container, {
    rules: {
      // jsdom computes styles but paints nothing, so contrast is untestable
      // here; the token palette's contrast is owned by the design system.
      'color-contrast': { enabled: false },
    },
  })
}

function formatViolations(violations: axe.Result[]): string {
  return violations
    .map(
      (v) =>
        `${v.id} (${v.impact}): ${v.help}\n` +
        v.nodes.map((n) => `  ${n.html}`).join('\n'),
    )
    .join('\n')
}

for (const [component, stories] of suites) {
  describe(`${component} stories (axe)`, () => {
    for (const [name, Story] of Object.entries(stories)) {
      it(`${name} has no axe violations`, async () => {
        const { container } = render(<Story />)
        const results = await runAxe(container)
        expect(formatViolations(results.violations)).toBe('')
      })
    }
  })
}
