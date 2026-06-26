import { style } from '@vanilla-extract/css'

import { focusRing } from '../../design/a11y.css'
import { vars } from '../../design/theme.css'

/**
 * OptionGroup / OptionButton — pick exactly one from a small set, rendered as
 * full-width rows. Built on the React Aria `RadioGroup` / `Radio` (role
 * radiogroup/radio, roving arrow-key selection, single-select semantics), so
 * "choose one" is honest in the accessibility tree rather than a pile of
 * look-alike buttons.
 */
export const group = style({
  display: 'grid',
  gap: vars.space[2],
})

export const option = style({
  textAlign: 'left',
  background: vars.surface.raised,
  border: `${vars.stroke.hairline} solid ${vars.border.hairline}`,
  borderRadius: vars.radius.sm,
  padding: `${vars.space[3]} ${vars.space[4]}`,
  color: vars.text.secondary,
  fontSize: vars.size.body,
  cursor: 'pointer',
  transitionProperty: 'background, border-color, color',
  transitionDuration: vars.duration.fast,
  '@media': {
    '(prefers-reduced-motion: reduce)': { transitionProperty: 'none' },
  },
  selectors: {
    '&[data-pressed]': { background: vars.surface.press },
    // Selection is structural (ink border + ink text + weight), not chromatic —
    // the accent hue stays reserved for the verify signal (§4.2, §11).
    '&[data-selected]': {
      color: vars.text.primary,
      borderColor: vars.text.primary,
      fontWeight: vars.font.weight.medium,
    },
    '&[data-focus-visible]': focusRing,
  },
})
