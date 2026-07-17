import { keyframes, style, styleVariants } from '@vanilla-extract/css'

import { vars } from '../design/theme.css'

/**
 * ConditionChip — the scannable glyph+value chip in the conditions strip
 * (frame-conditions-wave §3, mock `conditions-strip-states.html`). One atom,
 * two homes: the This-feed card's right-now zone (read-only) and Detail's
 * tap-to-reveal receipt strip (interactive). All colour binds a semantic token;
 * slate/forecast never appear here — a chip is a reading, never an affordance
 * or a temporal tag. Only the two hazard tiers (Q5/Q7) tint it.
 */

const shimmer = keyframes({
  '0%': { opacity: 0.5 },
  '50%': { opacity: 1 },
  '100%': { opacity: 0.5 },
})

/** The shared chip box — a compact inline flex row, glyph + mono value. */
export const chip = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space[1],
  minHeight: '30px', // thumb-safe tap target (Q15) even for the read-only chips
  paddingBlock: '5px',
  paddingInline: vars.space[2],
  border: `${vars.stroke.hairline} solid ${vars.border.faint}`,
  borderRadius: vars.radius.sm,
  background: vars.surface.raised,
  fontFamily: vars.font.family.sans,
  fontSize: vars.size.meta,
  lineHeight: vars.lineHeight.tight,
  color: vars.text.secondary,
})

/** Interactive (Detail): a real button — no hover-dependence, focus-visible ring. */
export const button = style([
  chip,
  {
    cursor: 'pointer',
    // The disclosure toggle reads its openness from aria-expanded; the box gains
    // a quiet raised outline while open so the tapped chip is visibly the source.
    selectors: {
      '&[aria-expanded="true"]': {
        borderColor: vars.text.muted,
        boxShadow: `0 0 0 ${vars.stroke.hairline} ${vars.border.hairline}`,
      },
      '&:focus-visible': {
        outline: `${vars.stroke.path} solid ${vars.focus.ring}`,
        outlineOffset: vars.space[1],
      },
    },
  },
])

/** The reading value — mono (metrics rule, D2). */
export const value = style({
  fontFamily: vars.font.family.mono,
  fontWeight: vars.font.weight.medium,
  color: vars.text.primary,
})

/** Per-ChipState treatment (frame-conditions-wave §3 chip states). */
export const state = styleVariants({
  fresh: {},
  stale: {
    background: 'transparent',
    borderStyle: 'dashed',
  },
  unavailable: {
    background: 'transparent',
    borderStyle: 'dashed',
  },
  pending: {
    background: 'transparent',
    borderStyle: 'dashed',
    animation: `${shimmer} 1.4s ease-in-out infinite`,
    '@media': {
      '(prefers-reduced-motion: reduce)': { animation: 'none' },
    },
  },
})

/** Stale value recedes; its age is unknown-family, so it spends no alarm colour
 *  (Law 7) — the age reads in muted gray, never terracotta. */
export const staleValue = style({
  color: vars.text.muted,
  fontWeight: vars.font.weight.regular,
})

export const unavailableValue = style({
  color: vars.text.muted,
  fontStyle: 'italic',
  fontWeight: vars.font.weight.regular,
})

export const age = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: '2px',
  fontFamily: vars.font.family.mono,
  fontSize: vars.size.dataMicro,
  color: vars.text.muted,
})

export const glyph = style({
  flex: 'none',
  color: vars.text.muted,
})

/**
 * Warning tint (Q5/Q7): the strip flags WHICH kind a warning owns; the value +
 * glyph borrow the tier's accent so the outlier is scannable. `clear`/`unknown`
 * stay neutral (unknown is gray-family, never alarm-toned — Law 7).
 */
export const tint = styleVariants({
  clear: {},
  unknown: {},
  headsUp: {
    background: vars.signal.headsUp.bg,
    borderColor: vars.signal.headsUp.fg,
    borderStyle: 'solid',
    color: vars.signal.headsUp.fg,
  },
  blocked: {
    background: vars.signal.blocked.bg,
    borderColor: vars.signal.blocked.fg,
    borderStyle: 'solid',
    color: vars.signal.blocked.fg,
  },
})

/** When tinted, the glyph + value inherit the tier accent (not the neutral ink). */
export const tintInk = style({ color: 'inherit' })

/** The pending placeholder bar — a muted value-shaped block, no text. */
export const pendingBar = style({
  width: '3.5ch',
  height: vars.size.meta,
  borderRadius: vars.radius.sm,
  background: vars.surface.press,
})
