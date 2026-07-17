import { style, styleVariants } from '@vanilla-extract/css'

import { vars } from '../design/theme.css'

/**
 * Verified-hazard warning treatment, tinted by the curator's graded severity
 * (frame-conditions-wave Q7): `blocked` = a genuine barrier (terracotta),
 * `headsUp` = elevated but passable (amber). Same inline-callout shape the
 * `Signal` primitive established — a left rule + a soft field — but here the
 * hue is chosen by severity rather than fixed. Colour encodes actionability
 * (Law 7): both hazard tiers are warm accents, told apart by hue + copy.
 */
const base = style({
  margin: 0,
  paddingBlock: vars.space[2],
  paddingInline: vars.space[3],
  borderLeftStyle: 'solid',
  borderLeftWidth: vars.stroke.path,
  borderRadius: `0 ${vars.radius.sm} ${vars.radius.sm} 0`,
  fontFamily: vars.font.family.sans,
  fontSize: vars.size.emphasis,
  fontWeight: vars.font.weight.medium,
  lineHeight: 1.4,
})

export const item = styleVariants({
  headsUp: [base, { borderLeftColor: vars.signal.headsUp.fg, background: vars.signal.headsUp.bg, color: vars.signal.headsUp.fg }],
  blocked: [base, { borderLeftColor: vars.signal.blocked.fg, background: vars.signal.blocked.bg, color: vars.signal.blocked.fg }],
})
