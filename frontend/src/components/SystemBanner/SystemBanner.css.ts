import { style, styleVariants } from '@vanilla-extract/css'

import { vars } from '../../design/theme.css'

/**
 * SystemBanner — regional-alert / live-outage / personalization-degraded
 * (design-system-v0.2.md II.B, D1). Tiered like everything else in the
 * 4-tier signal system, but a banner is a bounded region (not an inline
 * status line), so each tier additionally carries a bounding treatment:
 * `unknown` stays a plain, calm box (no colour beyond the muted ink — Law 7:
 * "unknown is gray, never red", and never dressed up to look like an event);
 * `headsUp`/`blocked` get the accent left rule + soft field the spec calls
 * "an optional soft field" (I.2), mirroring `Signal.css.ts`'s established
 * verify-before-you-go treatment.
 */
export const base = style({
  display: 'flex',
  flexDirection: 'column',
  gap: vars.space[1],
  paddingBlock: vars.space[3],
  paddingInline: vars.space[3],
  borderRadius: vars.radius.sm,
  borderLeftStyle: 'solid',
})

export const tier = styleVariants({
  unknown: {
    borderLeftWidth: vars.stroke.hairline,
    borderLeftColor: vars.border.hairline,
    background: 'transparent',
  },
  headsUp: {
    borderLeftWidth: vars.stroke.path,
    borderLeftColor: vars.signal.headsUp.fg,
    background: vars.signal.headsUp.bg,
  },
  blocked: {
    borderLeftWidth: vars.stroke.path,
    borderLeftColor: vars.signal.blocked.fg,
    background: vars.signal.blocked.bg,
  },
})

export const row = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space[2],
})

// The message row's ink follows the tier (Law 7 — colour encodes
// actionability): `unknown` is muted gray, never alarm-toned; `headsUp`/
// `blocked` carry their accent fg. Applied on the row so the `Icon`'s
// `currentColor` stroke and the `Text` child both inherit it without either
// primitive needing to know about signal tiers itself.
export const rowTier = styleVariants({
  unknown: { color: vars.signal.unknown.fg },
  headsUp: { color: vars.signal.headsUp.fg },
  blocked: { color: vars.signal.blocked.fg },
})

export const message = style({
  fontWeight: vars.font.weight.medium,
})

// The secondary detail line ("Trails, distances and terrain still work…")
// stays muted regardless of tier (states-gallery.html §6) — it is
// explanatory context, not the flagged fact, so it never borrows the accent.
export const secondary = style({
  color: vars.text.muted,
})

export const icon = style({
  flex: 'none',
})
