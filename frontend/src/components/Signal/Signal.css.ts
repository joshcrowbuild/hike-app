import { style } from '@vanilla-extract/css'

import { vars } from '../../design/theme.css'

/**
 * Signal — the verify-before-you-go honesty primitive (design-system-v0.1 §7.3).
 *
 * Every value binds to a semantic role or a scale token; there are no raw
 * literals. This is the ONLY place the accent (signal) hue is permitted to
 * appear (§7.3, §11). The treatment is an inline callout with a left rule and
 * a soft field — never a banner, modal, toast, or stoplight palette.
 */
export const signal = style({
  margin: 0,
  paddingBlock: vars.space[2],
  paddingInline: vars.space[3],
  borderLeft: `${vars.stroke.path} solid ${vars.signal.caution.fg}`,
  borderRadius: `0 ${vars.radius.sm} ${vars.radius.sm} 0`,
  background: vars.signal.caution.bg,
  color: vars.signal.caution.fg,
  fontFamily: vars.font.family.sans,
  // One tier above body, per §7.3 (size.emphasis). Promotion is typographic
  // (size + weight + the field), never chromatic alarm (§7.3, spec C4).
  fontSize: vars.size.emphasis,
  fontWeight: vars.font.weight.medium,
  lineHeight: 1.4,
})
