import { style, styleVariants } from '@vanilla-extract/css'

import { vars } from '../../design/theme.css'

/**
 * Confidence — renders the confidence tier as PRESENTATION, never a number
 * (design-system-v0.1 §7.1). The tier sets colour/weight; the hedge lives in the
 * copy itself. Non-live provenance is demoted to the `sample` treatment so a
 * fabricated fact can never read as a verified one (UX plan R1).
 */
const base = {
  fontFamily: vars.font.family.sans,
  lineHeight: 1.45,
} as const

export const tier = styleVariants({
  // stated → plain ink, no chrome, no hedge.
  stated: { ...base, color: vars.text.primary },
  // hedged → quieter; the copy carries "seems to" / "likely".
  hedged: { ...base, color: vars.text.secondary },
  // flagged → the accent (verify) treatment, one weight up; the only accent use.
  flagged: { ...base, color: vars.signal.caution.fg, fontWeight: vars.font.weight.medium },
  // sample/mock → demoted, never mistakable for a verified fact.
  sample: { ...base, color: vars.text.muted },
})

/** A small, unmistakable marker that a value is not live-verified (R1). */
export const sampleTag = style({
  marginInlineStart: vars.space[2],
  fontFamily: vars.font.family.mono,
  fontSize: vars.size.label,
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
  color: vars.text.muted,
  border: `${vars.stroke.hairline} solid ${vars.border.hairline}`,
  borderRadius: vars.radius.sm,
  paddingInline: vars.space[1],
  whiteSpace: 'nowrap',
})
