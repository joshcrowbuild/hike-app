import { style } from '@vanilla-extract/css'

import { vars } from './design/theme.css'

export const page = style({
  width: 'min(100%, 29rem)',
  margin: '0 auto',
  minHeight: '100vh',
  padding: `${vars.space[6]} ${vars.space[4]} 5rem`,
  display: 'grid',
  gap: vars.space[8],
})

export const pageTitle = style({
  margin: 0,
  fontFamily: vars.font.family.mono,
  fontSize: vars.size.label,
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
  color: vars.text.muted,
})

export const section = style({
  display: 'grid',
  gap: vars.space[4],
})

export const sectionHead = style({
  display: 'grid',
  gap: vars.space[1],
})

export const sectionTitle = style({
  margin: 0,
  fontFamily: vars.font.family.mono,
  fontSize: vars.size.meta,
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
  color: vars.text.secondary,
  fontWeight: vars.font.weight.semibold,
})

export const sectionDesc = style({
  margin: 0,
  fontSize: vars.size.meta,
  color: vars.text.muted,
  lineHeight: 1.5,
})

export const demoBox = style({
  background: vars.surface.raised,
  border: `${vars.stroke.hairline} solid ${vars.border.hairline}`,
  borderRadius: vars.radius.md,
  padding: vars.space[4],
  display: 'grid',
  gap: vars.space[3],
})

export const demoRow = style({
  display: 'grid',
  gap: vars.space[2],
})

export const demoLabel = style({
  fontFamily: vars.font.family.mono,
  fontSize: vars.size.label,
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  color: vars.text.muted,
})

export const divider = style({
  height: vars.stroke.hairline,
  background: vars.border.faint,
  border: 'none',
  margin: 0,
})

export const tokenChip = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space[1],
  fontFamily: vars.font.family.mono,
  fontSize: vars.size.label,
  color: vars.text.muted,
  background: vars.surface.canvas,
  border: `${vars.stroke.hairline} solid ${vars.border.faint}`,
  borderRadius: vars.radius.sm,
  paddingBlock: '2px',
  paddingInline: vars.space[2],
})

export const tokenDot = style({
  width: vars.space[2],
  height: vars.space[2],
  borderRadius: vars.radius.pill,
  flex: 'none',
})

export const sheetTrigger = style({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: vars.space[4],
  background: vars.surface.canvas,
  border: `${vars.stroke.hairline} solid ${vars.border.hairline}`,
  borderRadius: vars.radius.sm,
  padding: `${vars.space[3]} ${vars.space[4]}`,
  fontSize: vars.size.body,
  fontWeight: vars.font.weight.medium,
  color: vars.text.primary,
  cursor: 'pointer',
  transitionProperty: 'background, border-color',
  transitionDuration: vars.duration.fast,
  transitionTimingFunction: vars.easing.standard,
  '@media': {
    '(prefers-reduced-motion: reduce)': { transitionProperty: 'none' },
  },
  selectors: {
    '&:hover': { background: vars.surface.press },
    '&:active': { background: vars.surface.press },
    '&:focus-visible': {
      outline: `${vars.stroke.path} solid ${vars.focus.ring}`,
      outlineOffset: vars.space[1],
    },
  },
})

export const arrow = style({
  fontFamily: vars.font.family.mono,
  fontSize: vars.size.label,
  color: vars.text.muted,
})

export const motionNote = style({
  margin: 0,
  fontSize: vars.size.meta,
  color: vars.text.muted,
  fontStyle: 'italic',
  lineHeight: 1.5,
})
