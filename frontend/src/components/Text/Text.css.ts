import { styleVariants } from '@vanilla-extract/css'

import { vars } from '../../design/theme.css'

/**
 * Text — the missing v0.2 type-role primitive (design-system-v0.2.md I.3,
 * II.A). Each role binds size + lineHeight + weight + family (+ case for
 * `overline`) from ONE place, retiring the raw-rem classes Epic-019 left
 * half-migrated (Law 5 — pick a role, never a size).
 *
 * Deliberately EXCLUDES colour: the role table's `case` column names a
 * colour hint for two roles (`metricLabel`/`caption` -> muted), but colour is
 * a separate semantic decision the CALLER makes via `vars.text.*` /
 * `vars.signal.*` — Text only ever encapsulates typography (design-system-v0.2
 * Part II.A: "Applies a type.* role (size+lh+weight+family+case)"), so a
 * component can still choose its own ink without fighting this primitive.
 */
const base = { margin: 0 }

export const role = styleVariants({
  display: {
    ...base,
    fontSize: vars.type.display.size,
    lineHeight: vars.type.display.lineHeight,
    fontWeight: vars.type.display.weight,
    fontFamily: vars.font.family.sans,
  },
  title: {
    ...base,
    fontSize: vars.type.title.size,
    lineHeight: vars.type.title.lineHeight,
    fontWeight: vars.type.title.weight,
    fontFamily: vars.font.family.sans,
  },
  lead: {
    ...base,
    fontSize: vars.type.lead.size,
    lineHeight: vars.type.lead.lineHeight,
    fontWeight: vars.type.lead.weight,
    fontFamily: vars.font.family.sans,
  },
  body: {
    ...base,
    fontSize: vars.type.body.size,
    lineHeight: vars.type.body.lineHeight,
    fontWeight: vars.type.body.weight,
    fontFamily: vars.font.family.sans,
  },
  bodySm: {
    ...base,
    fontSize: vars.type.bodySm.size,
    lineHeight: vars.type.bodySm.lineHeight,
    fontWeight: vars.type.bodySm.weight,
    fontFamily: vars.font.family.sans,
  },
  // D2 — mono for metrics only; tabular-nums so numeric columns align (I.3).
  metric: {
    ...base,
    fontSize: vars.type.metric.size,
    lineHeight: vars.type.metric.lineHeight,
    fontWeight: vars.type.metric.weight,
    fontFamily: vars.type.metric.family,
    fontVariantNumeric: 'tabular-nums',
  },
  metricLabel: {
    ...base,
    fontSize: vars.type.metricLabel.size,
    lineHeight: vars.type.metricLabel.lineHeight,
    fontWeight: vars.type.metricLabel.weight,
    fontFamily: vars.font.family.sans,
  },
  caption: {
    ...base,
    fontSize: vars.type.caption.size,
    lineHeight: vars.type.caption.lineHeight,
    fontWeight: vars.type.caption.weight,
    fontFamily: vars.font.family.sans,
  },
  // The one rare kicker (Law 5): UPPERCASE is permitted nowhere else. The
  // `+.06em` tracking is a spec-literal constant (I.3) — there is no
  // `letterSpacing` scale in Contract A, so, like the sr-only recipe in
  // `a11y.css.ts`, this one value is exempt from the no-raw-token rule.
  overline: {
    ...base,
    fontSize: vars.type.overline.size,
    lineHeight: vars.type.overline.lineHeight,
    fontWeight: vars.type.overline.weight,
    fontFamily: vars.font.family.sans,
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
  },
})
