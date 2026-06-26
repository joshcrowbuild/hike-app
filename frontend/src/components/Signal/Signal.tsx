import type { ComponentPropsWithoutRef, ReactNode } from 'react'

import { srOnly } from '../../design/a11y.css'
import * as styles from './Signal.css'

export type SignalProps = {
  /** The caution message — one human clause (e.g. "Verify creek crossings — running high"). */
  children: ReactNode
  /**
   * Visually-hidden lead-in so assistive tech gets the same "this is a
   * verify-before-you-go caution" framing that sighted users read from the
   * accent treatment. Colour is never the only cue (design-system-v0.1 §4.3).
   */
  label?: string
  className?: string
} & Omit<ComponentPropsWithoutRef<'p'>, 'children' | 'className'>

/**
 * Signal is the reference owned component: behaviour-free, token-bound, and the
 * sole carrier of the accent hue. Its presence on a surface *is* the verify
 * state (§8) — there is no severity scale and no dismiss.
 *
 * Layout (outer margin / placement) is the consumer's concern: on a card it
 * rides the card's flow gap; on Detail it composes inside fuller context. Pass
 * `className` to position it.
 */
export function Signal({ children, label = 'Caution', className, ...rest }: SignalProps) {
  return (
    <p className={className ? `${styles.signal} ${className}` : styles.signal} {...rest}>
      <span className={srOnly}>{label}: </span>
      {children}
    </p>
  )
}
