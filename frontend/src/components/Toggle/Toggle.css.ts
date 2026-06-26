import { style } from '@vanilla-extract/css'

import { focusRing } from '../../design/a11y.css'
import { vars } from '../../design/theme.css'

/**
 * Toggle — an explicit on/off setting (e.g. the readiness filter). Built on the
 * React Aria `Switch` (role="switch", keyboard + focus handled for us); the
 * visual is an owned, fully token-derived sliding switch. radius.pill is
 * reserved for this switch only (design-system-v0.1 §6.2).
 *
 * Switch geometry is composed entirely from the space scale, so the thumb's
 * travel stays in rhythm with the rest of the system:
 *   track = space.8 + space.2 (40) x space.6 (24); thumb = space.4 (16);
 *   inset = space.1 (4); travel = space.4 (16).
 */
export const root = style({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: vars.space[4],
  width: '100%',
  background: vars.surface.raised,
  border: `${vars.stroke.hairline} solid ${vars.border.hairline}`,
  borderRadius: vars.radius.sm,
  padding: vars.space[4],
  textAlign: 'left',
  cursor: 'pointer',
  selectors: {
    '&[data-selected]': { borderColor: vars.text.primary },
    '&[data-focus-visible]': focusRing,
  },
})

export const text = style({
  display: 'grid',
  gap: vars.space[1],
  minWidth: 0,
})

export const label = style({
  color: vars.text.primary,
  fontWeight: vars.font.weight.semibold,
})

export const description = style({
  margin: 0,
  fontSize: vars.size.meta,
  lineHeight: 1.4,
  color: vars.text.secondary,
})

export const track = style({
  position: 'relative',
  flex: 'none',
  width: `calc(${vars.space[8]} + ${vars.space[2]})`,
  height: vars.space[6],
  borderRadius: vars.radius.pill,
  background: vars.surface.press,
  border: `${vars.stroke.hairline} solid ${vars.border.hairline}`,
  transitionProperty: 'background, border-color',
  transitionDuration: vars.duration.fast,
  transitionTimingFunction: vars.easing.standard,
  '@media': {
    '(prefers-reduced-motion: reduce)': { transitionProperty: 'none' },
  },
  selectors: {
    [`${root}[data-selected] &`]: {
      background: vars.text.primary,
      borderColor: vars.text.primary,
    },
  },
})

export const thumb = style({
  position: 'absolute',
  top: vars.space[1],
  left: vars.space[1],
  width: vars.space[4],
  height: vars.space[4],
  borderRadius: vars.radius.pill,
  background: vars.text.muted,
  transitionProperty: 'transform, background',
  transitionDuration: vars.duration.fast,
  transitionTimingFunction: vars.easing.standard,
  '@media': {
    '(prefers-reduced-motion: reduce)': { transitionProperty: 'none' },
  },
  selectors: {
    [`${root}[data-selected] &`]: {
      transform: `translateX(${vars.space[4]})`,
      background: vars.surface.canvas,
    },
  },
})
