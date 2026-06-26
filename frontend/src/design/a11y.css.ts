import { style } from '@vanilla-extract/css'

import { vars } from './theme.css'

/**
 * The single, neutral keyboard-focus treatment. Ink (not the signal hue) so it
 * reads on both surfaces and never competes with the accent (design-system-v0.1
 * §4.3). Spread into a component's `&[data-focus-visible]` / `&:focus-visible`
 * selector. RAC primitives only flag `data-focus-visible` on keyboard focus.
 */
export const focusRing = {
  outline: `${vars.stroke.path} solid ${vars.focus.ring}`,
  outlineOffset: vars.space[1],
} as const

/**
 * Visually hide content while keeping it in the accessibility tree.
 *
 * The 1px / negative-margin / clip-rect values are the canonical sr-only
 * recipe, not theme sizes — they are implementation constants and therefore
 * exempt from the no-raw-size rule (design-system-v0.1 §3.1).
 */
export const srOnly = style({
  position: 'absolute',
  width: '1px',
  height: '1px',
  padding: 0,
  margin: '-1px',
  overflow: 'hidden',
  clip: 'rect(0, 0, 0, 0)',
  whiteSpace: 'nowrap',
  borderWidth: 0,
})
