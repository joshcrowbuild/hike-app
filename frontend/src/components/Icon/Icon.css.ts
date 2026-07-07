import { style } from '@vanilla-extract/css'

/**
 * Icon — a Lucide glyph worn as a LEADING ACCENT beside an existing word, never
 * a replacement for it (Epic 021 · DD2). Two rules make it honest and theme-safe:
 *
 * 1. It binds NO colour of its own — the glyph strokes `currentColor`, so it
 *    inherits whatever text token its context sets (a fact label's muted ink, a
 *    chip's primary ink) and therefore reads correctly in BOTH light and dark
 *    without a single theme-specific value (AC-21.1.1).
 * 2. It sizes to `1em`, so the accent tracks the type it rides beside instead of
 *    pinning a raw pixel size that would drift as the type scale changes.
 */
export const icon = style({
  display: 'inline-flex',
  alignItems: 'center',
  flex: 'none',
})

export const glyph = style({
  width: '1em',
  height: '1em',
  // Never a colour of its own: the accent follows the inherited text token, the
  // one-directional reference rule that keeps it legible in either theme.
  color: 'currentColor',
})
