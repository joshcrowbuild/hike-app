import { style } from '@vanilla-extract/css'

import { vars } from '../../design/theme.css'

/**
 * Staleness — age as a relative-time WORD, never a raw datetime
 * (design-system-v0.1 §7.2). Past a threshold the presentation is *demoted*
 * (lighter), but it NEVER reorders or buries by rank — staleness demotes
 * presentation, never position (Rule #2). The relative-time string is supplied
 * by the caller; this component only carries the treatment.
 */
const base = {
  fontFamily: vars.font.family.mono,
  fontSize: vars.size.label,
  letterSpacing: '0.04em',
} as const

export const fresh = style({ ...base, color: vars.text.muted })

export const stale = style({
  ...base,
  color: vars.text.muted,
  opacity: 0.7,
  fontStyle: 'italic',
})
