import { style } from '@vanilla-extract/css'

import { vars } from '../design/theme.css'

/**
 * Detail's "Current conditions" strip + the ONE tap-to-reveal receipt line
 * below it (frame-conditions-wave Q6, mock `detail-provenance-tap.html` option
 * A). Calm by default; the source-or-silence receipt is one tap away, never a
 * popover, never an always-open ledger.
 */
export const block = style({
  marginBlock: vars.space[4],
})

export const heading = style({
  fontSize: vars.size.meta,
  fontWeight: vars.font.weight.semibold,
  color: vars.text.muted,
  marginBottom: vars.space[2],
})

export const strip = style({
  display: 'flex',
  flexWrap: 'wrap',
  gap: `${vars.space[1]} ${vars.space[2]}`,
  alignItems: 'stretch',
})

/** The single receipt line — source · age · confidence, mono meta ink. */
export const receipt = style({
  marginTop: vars.space[3],
  paddingTop: vars.space[2],
  borderTop: `${vars.stroke.hairline} solid ${vars.border.faint}`,
  display: 'flex',
  flexWrap: 'wrap',
  gap: vars.space[1],
  alignItems: 'baseline',
})

export const receiptKind = style({
  fontSize: vars.size.meta,
  fontWeight: vars.font.weight.medium,
  color: vars.text.secondary,
})

export const receiptMeta = style({
  fontFamily: vars.font.family.mono,
  fontSize: vars.size.label,
  color: vars.text.muted,
})
