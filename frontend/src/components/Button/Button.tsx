import { Button as RACButton } from 'react-aria-components'
import type { ButtonProps as RACButtonProps } from 'react-aria-components'

import * as styles from './Button.css'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost'
export type ButtonSize = 'sm' | 'md'

export type ButtonProps = {
  /** Filled ink (primary action) / outlined (secondary action) / bare (ghost, quiet/recovery action). */
  variant?: ButtonVariant
  size?: ButtonSize
  className?: string
} & Omit<RACButtonProps, 'className'>

/**
 * Button — the owned interactive primitive (design-system-v0.2.md II.A),
 * built on the React Aria `Button` so keyboard activation, the
 * hover/press/focus-visible state machine, and `isDisabled` are handled for
 * us rather than re-derived per call site (as `.action-chip` and
 * `.text-action` in `styles.css` each currently do by hand). Label case is
 * never transformed by this primitive — sentence case is the caller's
 * responsibility, same as every other v0.2 surface (Law 5).
 */
export function Button({ variant = 'primary', size = 'md', className, children, ...rest }: ButtonProps) {
  const cls = [styles.base, styles.variant[variant], styles.size[size], className].filter(Boolean).join(' ')
  return (
    <RACButton className={cls} {...rest}>
      {children}
    </RACButton>
  )
}
