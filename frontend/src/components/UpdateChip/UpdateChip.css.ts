import { keyframes, style } from '@vanilla-extract/css'

import { vars } from '../../design/theme.css'

/**
 * UpdateChip — the "Updating conditions…" pill shown during a background
 * revalidate (design-system-v0.2.md II.B, I.6). Deliberately neutral/muted
 * ink, not the amber signal hue the mock's demo swatch uses: a routine
 * cache-first revalidation is not an actionable event, and `signal.headsUp`
 * is reserved for real actionability (Law 7) — reusing it here would blur
 * that boundary. Motion is restrained (I.6: named motions are restraint-
 * first) and fully honors `prefers-reduced-motion` (mirrors `SkeletonCard`'s
 * belt-and-suspenders approach: the pulse class is only applied by the
 * component when JS-detected motion is allowed, AND the animation itself is
 * neutralized here at the CSS layer as a second guard).
 */
const pulse = keyframes({
  '0%': { opacity: 0.3 },
  '50%': { opacity: 1 },
  '100%': { opacity: 0.3 },
})

export const chip = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space[2],
  paddingBlock: vars.space[1],
  paddingInline: vars.space[3],
  borderRadius: vars.radius.pill,
  border: `${vars.stroke.hairline} solid ${vars.border.hairline}`,
  color: vars.text.muted,
})

export const dot = style({
  // No scale token means "a status dot" — like the sr-only recipe in
  // `a11y.css.ts` and Button's 44px hit target, this is a documented raw-
  // literal exemption, not a raw colour/space substitute.
  width: '7px',
  height: '7px',
  flex: 'none',
  borderRadius: vars.radius.pill,
  background: vars.text.muted,
})

export const dotPulse = style({
  animationName: pulse,
  animationDuration: '1.1s',
  animationIterationCount: 'infinite',
  animationTimingFunction: vars.easing.standard,
  '@media': {
    '(prefers-reduced-motion: reduce)': { animationName: 'none' },
  },
})
