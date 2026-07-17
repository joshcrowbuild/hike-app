import { style, styleVariants } from '@vanilla-extract/css'

import { vars } from '../design/theme.css'

/**
 * The "This feed" boarding-pass card (frame-conditions-wave §3, mocks
 * `frame-card-typescale.html` variant 01 + `frame-card-conditions-zones.html`).
 * One card at the top of the feed: the frame as a type-scale facet stack, then
 * the forecast zone + right-now zone. Slate is interactive-only; forecast sky
 * and the two hazard tiers are the only other hues — all via tokens.
 */
export const card = style({
  background: vars.surface.raised,
  border: `${vars.stroke.hairline} solid ${vars.border.hairline}`,
  borderRadius: vars.radius.md,
  overflow: 'hidden',
})

export const header = style({
  paddingBlock: `${vars.space[3]} ${vars.space[1]}`,
  paddingInline: vars.space[4],
})

/** The one permitted uppercase role — the overline `This feed` (S1 AC-1.3). */
export const overline = style({
  color: vars.text.muted,
})

export const facets = style({
  paddingBlock: `${vars.space[1]} ${vars.space[3]}`,
  paddingInline: vars.space[4],
})

export const facetLabel = style({
  display: 'block',
  fontSize: vars.size.dataMicro,
  fontWeight: vars.font.weight.medium,
  color: vars.text.muted,
  marginBottom: '1px',
})

/** From — the headline facet (~21–23px slate, chevron). All-slate, always-on. */
export const fromButton = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space[1],
  minHeight: '30px',
  padding: 0,
  border: 0,
  background: 'none',
  cursor: 'pointer',
  fontFamily: vars.font.family.sans,
  fontSize: '22px',
  fontWeight: vars.font.weight.semibold,
  letterSpacing: '-0.015em',
  lineHeight: vars.lineHeight.tight,
  color: vars.interactive.fg,
  WebkitTapHighlightColor: 'transparent',
  selectors: {
    '&:focus-visible': {
      outline: `${vars.stroke.path} solid ${vars.focus.ring}`,
      outlineOffset: vars.space[1],
      borderRadius: vars.radius.sm,
    },
  },
})

/** When — the subline facet (slate, chevron). */
export const whenButton = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space[1],
  minHeight: '30px',
  marginTop: vars.space[2],
  padding: 0,
  border: 0,
  background: 'none',
  cursor: 'pointer',
  fontFamily: vars.font.family.sans,
  fontSize: vars.size.meta,
  fontWeight: vars.font.weight.medium,
  color: vars.interactive.fg,
  WebkitTapHighlightColor: 'transparent',
  selectors: {
    '&:focus-visible': {
      outline: `${vars.stroke.path} solid ${vars.focus.ring}`,
      outlineOffset: vars.space[1],
      borderRadius: vars.radius.sm,
    },
  },
})

export const minorRow = style({
  display: 'flex',
  flexWrap: 'wrap',
  gap: vars.space[2],
  marginTop: vars.space[3],
})

/** Party · Effort — small filled slate chips (caret). */
export const chipButton = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space[1],
  minHeight: '30px',
  paddingBlock: vars.space[1],
  paddingInline: '9px',
  border: 0,
  borderRadius: vars.radius.sm,
  background: vars.interactive.bg,
  cursor: 'pointer',
  fontFamily: vars.font.family.sans,
  fontSize: '12.5px',
  fontWeight: vars.font.weight.medium,
  color: vars.interactive.fg,
  WebkitTapHighlightColor: 'transparent',
  selectors: {
    '&:active': { background: vars.interactive.bgPress },
    '&:focus-visible': {
      outline: `${vars.stroke.path} solid ${vars.focus.ring}`,
      outlineOffset: vars.space[1],
    },
  },
})

/** The chevron/caret accent — dimmed, inherits the slate ink. */
export const caret = style({ flex: 'none', opacity: 0.55, color: 'inherit' })

// ---- condition zones -------------------------------------------------------

export const zone = style({
  paddingBlock: vars.space[3],
  paddingInline: vars.space[4],
  borderTop: `${vars.stroke.hairline} solid ${vars.border.faint}`,
})

export const zoneHead = style({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: vars.space[2],
  marginBottom: vars.space[2],
})

export const zoneLabel = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space[2],
  fontSize: vars.size.meta,
  color: vars.text.secondary,
})

export const zoneLead = style({ fontWeight: vars.font.weight.semibold, color: vars.text.primary })

export const caveat = style({ color: vars.text.muted, fontSize: vars.size.label })

/** The `forecast` temporal tag (sky) — informational, never an affordance. */
export const forecastTag = style({
  fontSize: vars.size.dataMicro,
  fontWeight: vars.font.weight.semibold,
  letterSpacing: '0.03em',
  textTransform: 'uppercase',
  color: vars.forecast.fg,
  background: vars.forecast.bg,
  borderRadius: vars.radius.sm,
  paddingBlock: '2px',
  paddingInline: vars.space[1],
})

/** The `current` / `now` tag — neutral, quieter than forecast. */
export const currentTag = style({
  fontSize: vars.size.dataMicro,
  fontWeight: vars.font.weight.semibold,
  letterSpacing: '0.03em',
  textTransform: 'uppercase',
  color: vars.text.muted,
  background: vars.surface.press,
  borderRadius: vars.radius.sm,
  paddingBlock: '2px',
  paddingInline: vars.space[1],
})

export const headActions = style({
  display: 'flex',
  alignItems: 'center',
  gap: vars.space[2],
})

/** The day toggle — a segmented control (React-Aria pattern). */
export const dayToggle = style({
  display: 'inline-flex',
  border: `${vars.stroke.hairline} solid ${vars.border.hairline}`,
  borderRadius: vars.radius.sm,
  overflow: 'hidden',
  background: vars.surface.raised,
})

export const dayButton = style({
  border: 0,
  borderRight: `${vars.stroke.hairline} solid ${vars.border.faint}`,
  background: 'none',
  cursor: 'pointer',
  fontFamily: vars.font.family.sans,
  fontSize: vars.size.label,
  color: vars.text.muted,
  paddingBlock: vars.space[1],
  paddingInline: '9px',
  minHeight: '28px',
  selectors: {
    '&:last-child': { borderRight: 0 },
    '&[aria-pressed="true"]': { background: vars.text.primary, color: vars.surface.raised },
    '&:focus-visible': { outline: `${vars.stroke.path} solid ${vars.focus.ring}`, outlineOffset: `-${vars.stroke.path}` },
  },
})

export const chips = style({
  display: 'flex',
  flexWrap: 'wrap',
  gap: vars.space[1],
})

/** A quiet Refresh action (S3 AC-3.3) — slate text affordance, not a hazard. */
export const refresh = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: '4px',
  border: 0,
  background: 'none',
  cursor: 'pointer',
  padding: vars.space[1],
  fontFamily: vars.font.family.sans,
  fontSize: vars.size.label,
  color: vars.interactive.fg,
  selectors: {
    '&:focus-visible': { outline: `${vars.stroke.path} solid ${vars.focus.ring}`, outlineOffset: vars.space[1], borderRadius: vars.radius.sm },
  },
})

/** Degraded / empty forecast disclosure (S2 AC-2.3) — one muted line, no fake value. */
export const degradedLine = style({
  fontSize: vars.size.meta,
  color: vars.text.muted,
})

// ---- past 3 days reveal + mud (S4) ----------------------------------------

export const recentToggle = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: vars.space[1],
  marginTop: vars.space[2],
  border: 0,
  background: 'none',
  cursor: 'pointer',
  padding: `${vars.space[1]} 0`,
  minHeight: '28px',
  fontFamily: vars.font.family.sans,
  fontSize: vars.size.label,
  color: vars.text.muted,
  selectors: {
    '&[aria-expanded="true"]': { color: vars.text.secondary, fontWeight: vars.font.weight.medium },
    '&:focus-visible': { outline: `${vars.stroke.path} solid ${vars.focus.ring}`, outlineOffset: vars.space[1], borderRadius: vars.radius.sm },
  },
})

export const recentBox = style({
  marginTop: vars.space[2],
  border: `${vars.stroke.hairline} solid ${vars.border.faint}`,
  borderRadius: vars.radius.sm,
  background: vars.surface.raised,
  padding: `${vars.space[2]} 11px`,
})

export const recentHead = style({
  fontSize: vars.size.label,
  color: vars.text.muted,
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
  marginBottom: vars.space[2],
})

export const days = style({ display: 'flex', gap: vars.space[4] })

export const day = style({
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  gap: '3px',
  flex: 1,
})

export const dayLabel = style({ fontSize: vars.size.label, color: vars.text.muted })

export const dayAmount = styleVariants({
  wet: { fontFamily: vars.font.family.mono, fontSize: vars.size.meta, fontWeight: vars.font.weight.medium, color: vars.forecast.fg },
  dry: { fontFamily: vars.font.family.mono, fontSize: vars.size.meta, fontWeight: vars.font.weight.medium, color: vars.text.muted },
})

export const dayGlyph = styleVariants({
  wet: { color: vars.forecast.fg },
  dry: { color: vars.text.muted },
})

/** The mud read — a hedged inference (Q19): amber, DASHED, tagged `inferred`. */
export const mud = style({
  marginTop: vars.space[2],
  display: 'flex',
  gap: vars.space[2],
  alignItems: 'flex-start',
  border: `${vars.stroke.hairline} dashed ${vars.signal.headsUp.fg}`,
  background: vars.signal.headsUp.bg,
  borderRadius: vars.radius.sm,
  padding: `${vars.space[2]} 11px`,
})

export const mudGlyph = style({ flex: 'none', color: vars.signal.headsUp.fg, marginTop: '1px' })

export const mudText = style({
  fontSize: vars.size.meta,
  color: vars.signal.headsUp.fg,
  lineHeight: vars.lineHeight.snug,
})

export const mudStatement = style({ fontWeight: vars.font.weight.semibold })

export const mudTag = style({
  display: 'inline-block',
  fontSize: '9px',
  fontWeight: vars.font.weight.semibold,
  letterSpacing: '0.03em',
  textTransform: 'uppercase',
  color: vars.signal.headsUp.fg,
  border: `${vars.stroke.hairline} solid ${vars.signal.headsUp.fg}`,
  borderRadius: '4px',
  paddingBlock: '1px',
  paddingInline: '5px',
  marginLeft: vars.space[1],
  verticalAlign: '1px',
})

export const mudEvidence = style({
  display: 'block',
  marginTop: '2px',
  fontSize: vars.size.label,
  color: vars.text.muted,
})
