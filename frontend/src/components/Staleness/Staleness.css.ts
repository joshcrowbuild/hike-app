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

// Demotion is carried by italic, NOT opacity: compositing opacity over muted
// text drops effective contrast below WCAG AA on small text (§4.3). Italic keeps
// the demoted read while the colour stays at the validated muted tier.
export const stale = style({
  ...base,
  color: vars.text.muted,
  fontStyle: 'italic',
})
