import { style, styleVariants } from '@vanilla-extract/css'

import { focusRing } from '../../design/a11y.css'
import { vars } from '../../design/theme.css'

/**
 * Button — the owned interactive primitive (design-system-v0.2.md II.A),
 * extracted so `Verdict`/`WarningBlock`/action-chip-style controls have one
 * shared base to converge on instead of each hand-rolling focus/press/hover
 * treatment. Built on the React Aria `Button` (role="button", keyboard +
 * press/hover/focus state machine handled for us, exposed as
 * `data-hovered`/`data-pressed`/`data-focus-visible`/`data-disabled`) — the
 * same state-attribute convention `Toggle`/`OptionGroup` already use.
 *
 * Sentence case (Law 5) — unlike the legacy `.action-chip`/`.text-action`
 * mono-uppercase treatment those two primitives retire, a Button label is
 * never transformed.
 */
export const base = style({
  position: 'relative',
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  gap: vars.space[2],
  fontFamily: vars.font.family.sans,
  fontWeight: vars.font.weight.medium,
  textAlign: 'center',
  textDecoration: 'none',
  border: `${vars.stroke.hairline} solid transparent`,
  borderRadius: vars.radius.sm,
  cursor: 'pointer',
  transitionProperty: 'background, border-color, color',
  transitionDuration: vars.duration.fast,
  transitionTimingFunction: vars.easing.standard,
  '@media': {
    '(prefers-reduced-motion: reduce)': { transitionProperty: 'none' },
  },
  selectors: {
    // Apple HIG's 44px minimum hit target, applied as an invisible centered
    // hit-zone extension rather than growing the visible chrome — the exact
    // pattern the legacy `.action-chip`/`.text-action` controls already use
    // (`styles.css` "44px minimum hit area", Epic 020 AC-20.1.1). `44px` is a
    // fixed platform a11y constant, not a design choice, so — like the
    // sr-only recipe in `a11y.css.ts` — it is exempt from the no-raw-size
    // rule: there is no `space.*` step that means "the a11y minimum."
    '&::before': {
      content: '',
      position: 'absolute',
      inset: '50%',
      width: 'max(100%, 44px)',
      height: 'max(100%, 44px)',
      transform: 'translate(-50%, -50%)',
    },
    '&[data-focus-visible]': focusRing,
    '&[data-disabled]': {
      cursor: 'not-allowed',
    },
  },
})

export const size = styleVariants({
  sm: {
    paddingBlock: vars.space[2],
    paddingInline: vars.space[3],
    fontSize: vars.type.bodySm.size,
    lineHeight: vars.type.bodySm.lineHeight,
  },
  md: {
    paddingBlock: vars.space[3],
    paddingInline: vars.space[4],
    fontSize: vars.type.body.size,
    lineHeight: vars.type.body.lineHeight,
  },
})

// Hover and press collapse onto the same `surface.press` step for the two
// unfilled variants — the same convention the legacy `.action-chip` already
// established (`&[data-hovered]` and the pressed/selected treatment share one
// background token; there is no third surface step to tell them apart).
export const variant = styleVariants({
  primary: {
    background: vars.text.primary,
    color: vars.surface.canvas,
    selectors: {
      '&[data-hovered]': { background: vars.text.secondary },
      '&[data-pressed]': { background: vars.text.primary },
      '&[data-disabled]': {
        background: vars.surface.press,
        color: vars.text.muted,
      },
    },
  },
  secondary: {
    background: vars.surface.raised,
    color: vars.text.primary,
    borderColor: vars.border.hairline,
    selectors: {
      '&[data-hovered]': { background: vars.surface.press },
      '&[data-pressed]': { background: vars.surface.press, borderColor: vars.text.primary },
      '&[data-disabled]': {
        background: vars.surface.raised,
        color: vars.text.muted,
        borderColor: vars.border.faint,
      },
    },
  },
  ghost: {
    background: 'transparent',
    color: vars.text.primary,
    selectors: {
      '&[data-hovered]': { background: vars.surface.press },
      '&[data-pressed]': { background: vars.surface.press },
      '&[data-disabled]': {
        background: 'transparent',
        color: vars.text.muted,
      },
    },
  },
})
