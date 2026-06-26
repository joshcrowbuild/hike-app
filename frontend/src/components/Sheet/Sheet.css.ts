import { style } from '@vanilla-extract/css'

import { focusRing } from '../../design/a11y.css'
import { vars } from '../../design/theme.css'

/**
 * Sheet — a focused bottom-sheet modal. Built on React Aria
 * `ModalOverlay` / `Modal` / `Dialog`, which provide the focus trap, focus
 * return, Escape-to-dismiss, scrim click-to-dismiss, and scroll lock that the
 * bespoke prototype sheet lacked. Motion is quiet (rise + fade, sub-160ms) and
 * fully respects prefers-reduced-motion (design-system-v0.1 §6.5).
 */
export const overlay = style({
  position: 'fixed',
  inset: 0,
  zIndex: 50,
  display: 'flex',
  alignItems: 'flex-end',
  justifyContent: 'center',
  padding: vars.space[3],
  background: vars.overlay.scrim,
  opacity: 1,
  transitionProperty: 'opacity',
  transitionDuration: vars.duration.fast,
  '@media': {
    '(prefers-reduced-motion: reduce)': { transitionProperty: 'none' },
  },
  selectors: {
    '&[data-entering]': { opacity: 0 },
    '&[data-exiting]': { opacity: 0 },
  },
})

export const sheet = style({
  // 29rem is a layout max-width (matches the app shell), not a theme size.
  width: 'min(100%, 29rem)',
  background: vars.surface.canvas,
  border: `${vars.stroke.hairline} solid ${vars.border.hairline}`,
  borderRadius: vars.radius.md,
  padding: vars.space[4],
  boxShadow: vars.elevation.overlay,
  transform: 'translateY(0)',
  transitionProperty: 'transform',
  transitionDuration: vars.duration.base,
  '@media': {
    '(prefers-reduced-motion: reduce)': { transitionProperty: 'none' },
  },
  selectors: {
    '&[data-entering]': { transform: `translateY(${vars.space[4]})` },
    '&[data-exiting]': { transform: `translateY(${vars.space[4]})` },
  },
})

export const dialog = style({
  outline: 'none',
})

export const header = style({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: vars.space[4],
  marginBottom: vars.space[4],
})

export const title = style({
  flex: 1,
  margin: 0,
  textAlign: 'center',
  fontSize: vars.size.emphasis,
  fontWeight: vars.font.weight.semibold,
  letterSpacing: '-0.01em',
  color: vars.text.primary,
})

export const headerButton = style({
  flex: 'none',
  fontFamily: vars.font.family.mono,
  fontSize: vars.size.label,
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
  color: vars.text.primary,
  paddingBlock: vars.space[1],
  borderRadius: vars.radius.sm,
  selectors: {
    '&:focus-visible': focusRing,
  },
})
