import type { ComponentPropsWithoutRef, ElementType, ReactNode } from 'react'

import * as styles from './Text.css'

/**
 * The v0.2 role scale (design-system-v0.2.md I.3) — a closed set of 9. Pick a
 * role, never a size (Law 5). `metric` is the only mono role (D2); `overline`
 * is the only UPPERCASE role, used rarely (the one rare kicker).
 */
export type TextRole =
  | 'display'
  | 'title'
  | 'lead'
  | 'body'
  | 'bodySm'
  | 'metric'
  | 'metricLabel'
  | 'caption'
  | 'overline'

/**
 * The semantic HTML element a role renders as when the caller doesn't pass
 * `as` — a reasonable default, not a mandate (a caption inside a `<dt>`, for
 * instance, still overrides via `as="dt"`).
 */
const DEFAULT_ELEMENT: Record<TextRole, ElementType> = {
  display: 'h1',
  title: 'h3',
  lead: 'p',
  body: 'p',
  bodySm: 'p',
  metric: 'span',
  metricLabel: 'span',
  caption: 'span',
  overline: 'span',
}

export type TextProps<E extends ElementType = 'span'> = {
  /** Which `type.*` role to apply — size + lineHeight + weight + family + case, from one place. */
  role: TextRole
  /** Override the rendered element (e.g. `as="h3"`); defaults per role, see `DEFAULT_ELEMENT`. */
  as?: E
  children: ReactNode
  className?: string
} & Omit<ComponentPropsWithoutRef<E>, 'as' | 'className' | 'children'>

/**
 * Text — the missing v0.2 primitive (design-system-v0.2.md II.A). Applies a
 * `type.*` role from ONE place, retiring the raw-rem classes Epic-019 left
 * half-migrated. It carries no colour of its own (see `Text.css.ts`) — a
 * consumer still chooses ink (`vars.text.*` / `vars.signal.*`) separately, so
 * this primitive never fights a context that already sets one.
 */
export function Text<E extends ElementType = 'span'>({
  role,
  as,
  className,
  children,
  ...rest
}: TextProps<E>) {
  const Component = (as ?? DEFAULT_ELEMENT[role]) as ElementType
  const cls = className ? `${styles.role[role]} ${className}` : styles.role[role]
  return (
    <Component className={cls} {...rest}>
      {children}
    </Component>
  )
}
