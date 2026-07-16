import { style } from '@vanilla-extract/css'

import { vars } from '../../design/theme.css'

/**
 * MetricRow — distance / ascent / duration, re-tokened onto `type.metric`
 * (mono, tabular-nums) + `type.metric-label` (sentence, muted) per
 * design-system-v0.2.md II.A. Colour lives HERE, not on `<Text>` (Text
 * encapsulates typography only) — the metric-label ramp step (`text.muted`)
 * is this component's own semantic choice, same as `type.metric`'s value
 * getting the stronger `text.primary` ink.
 */
export const row = style({
  display: 'flex',
  flexWrap: 'wrap',
  columnGap: vars.space[6],
  rowGap: vars.space[3],
})

export const item = style({
  display: 'grid',
  gap: vars.space[1],
  justifyItems: 'start',
})

export const label = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space[1],
  color: vars.text.muted,
})

export const icon = style({
  fontSize: '0.85em',
})

export const value = style({
  color: vars.text.primary,
})

/**
 * The named-disclosure treatment ("time unavailable") — never a bare "—"
 * (design-system-v0.2 II.A). Italicised, mirroring the existing
 * `.decision-value--unavailable` convention in `styles.css`, so a disclosed
 * gap reads as an honest, calm absence rather than a missing render.
 */
export const unavailable = style({
  color: vars.text.muted,
  fontStyle: 'italic',
})
