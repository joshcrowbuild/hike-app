import { style, styleVariants } from '@vanilla-extract/css'
import { vars } from '../design/theme.css'
import type { ConditionTier } from '../design/contracts'

const baseLine = style({
  display: 'flex',
  alignItems: 'flex-start',
  gap: '6px',
  fontSize: '13.5px', // Match mock `.a-flag` font-size
  lineHeight: vars.lineHeight.normal,
  fontFamily: vars.font.family.sans,
  marginBottom: '12px',
})

export const statusLine = styleVariants<Record<Exclude<ConditionTier, 'clear'>, any>>({
  unknown: [
    baseLine,
    {
      color: vars.signal.unknown.fg,
    },
  ],
  headsUp: [
    baseLine,
    {
      color: vars.signal.headsUp.fg,
    },
  ],
  blocked: [
    baseLine,
    {
      color: vars.signal.blocked.fg,
      background: vars.signal.blocked.bg,
      padding: `${vars.space[2]} ${vars.space[3]}`,
      borderRadius: vars.radius.sm,
    },
  ],
})

export const statusLineIcon = style({
  flexShrink: 0,
})

export const statusLineText = style({
  flex: 1,
})
