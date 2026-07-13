import { style } from '@vanilla-extract/css'

import { focusRing } from '../../design/a11y.css'
import { vars } from '../../design/theme.css'

/**
 * Sheet — a focused bottom-sheet modal. Built on React Aria
 * `ModalOverlay` / `Modal` / `Dialog`, which provide the focus trap, focus
 * return, Escape-to-dismiss, scrim click-to-dismiss, and scroll lock that the
 * bespoke prototype sheet lacked. Motion is quiet (rise + fade, sub-160ms) and
 * fully respects prefers-reduced-motion (design-system-v0.1 §6.5).
 *
 * Height contract (craft review C1): the sheet is capped below the viewport
 * and content taller than that scrolls INSIDE `body`, with the Back/Done
 * header pinned above the scroll area — so every action stays reachable no
 * matter how long the content is. Pinned by Sheet.test.tsx; do not remove the
 * cap or the internal scroll without moving the guarantee somewhere real.
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
  transitionTimingFunction: vars.easing.standard,
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
  // C1: never taller than the viewport — a 35-origin list must scroll inside
  // the sheet, not push Back/Done 1,200px off-screen. `dvh` tracks mobile
  // browser chrome; the `vh` entry is the fallback for engines without it.
  maxHeight: ['85vh', '85dvh'],
  display: 'flex',
  flexDirection: 'column',
  background: vars.surface.canvas,
  border: `${vars.stroke.hairline} solid ${vars.border.hairline}`,
  borderRadius: vars.radius.md,
  padding: vars.space[4],
  boxShadow: vars.elevation.overlay,
  transform: 'translateY(0)',
  transitionProperty: 'transform',
  transitionDuration: vars.duration.base,
  transitionTimingFunction: vars.easing.standard,
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
  // Continue the flex chain so `body` (not the dialog) is what scrolls.
  display: 'flex',
  flexDirection: 'column',
  minHeight: 0,
})

export const header = style({
  // Pinned: the header never enters the scroll area, so Back/Done stay
  // reachable at any scroll position (C1).
  flex: 'none',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: vars.space[4],
  marginBottom: vars.space[4],
})

/**
 * The one scrollable region of a sheet. `overscrollBehavior: contain` stops a
 * swipe past the list's end from chaining into the page behind the modal —
 * the live leak C1 measured (the feed scrolled behind the open dialog).
 * The 1-step negative-margin/padding pair keeps row focus rings (outline
 * offset 2px) from being clipped by the scroll box without changing layout.
 */
export const body = style({
  minHeight: 0,
  overflowY: 'auto',
  overscrollBehavior: 'contain',
  padding: vars.space[1],
  margin: `calc(-1 * ${vars.space[1]})`,
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
