import { style } from '@vanilla-extract/css'

import { vars } from '../../design/theme.css'

/**
 * EmptyState — the "nothing to show" surface (design-system-v0.2.md II.B,
 * Law 4/6). Centered, generous, and never a dead end: a headline names the
 * one binding constraint, a secondary line says what still holds, and a
 * single reset/loosen `Button` is the one way forward — never a bare "x" on
 * an input (states-gallery.html §4).
 */
export const container = style({
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  textAlign: 'center',
  gap: vars.space[2],
  paddingBlock: vars.space[8],
  paddingInline: vars.space[4],
})

export const headline = style({
  color: vars.text.primary,
  // Measure cap (I.3: "Measure cap <= 66ch on all prose blocks") — a
  // narrower cap than the ceiling reads better centered in a single column;
  // still well inside the spec's upper bound.
  maxWidth: '42ch',
})

export const secondary = style({
  color: vars.text.muted,
  maxWidth: '48ch',
})

export const cta = style({
  marginTop: vars.space[2],
})
