import { style } from '@vanilla-extract/css'

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
