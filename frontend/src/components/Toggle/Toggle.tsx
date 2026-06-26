import type { ReactNode } from 'react'
import { Switch } from 'react-aria-components'

import * as styles from './Toggle.css'

export type ToggleProps = {
  /** The setting name — the switch's accessible label. */
  label: ReactNode
  /** One quiet clause stating, in plain terms, what turning it on does. */
  description?: ReactNode
  isSelected: boolean
  onChange: (isSelected: boolean) => void
  className?: string
}

/**
 * An explicit, user-initiated on/off control. It never carries a default-on
 * posture in copy; the consumer states plainly what it does (outcome-card-ux
 * §3 — readiness is a filter the user *chooses* to apply, never silent).
 */
export function Toggle({ label, description, isSelected, onChange, className }: ToggleProps) {
  return (
    <Switch
      className={className ? `${styles.root} ${className}` : styles.root}
      isSelected={isSelected}
      onChange={onChange}
    >
      <span className={styles.text}>
        <span className={styles.label}>{label}</span>
        {description ? <span className={styles.description}>{description}</span> : null}
      </span>
      <span className={styles.track} aria-hidden="true">
        <span className={styles.thumb} />
      </span>
    </Switch>
  )
}
