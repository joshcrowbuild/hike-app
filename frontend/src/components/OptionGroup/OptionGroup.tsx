import type { ReactNode } from 'react'
import { Radio, RadioGroup } from 'react-aria-components'

import * as styles from './OptionGroup.css'

export type OptionGroupProps<T extends string> = {
  /** Accessible name for the group (the sheet title usually carries it visually). */
  label: string
  value: T
  onChange: (value: T) => void
  children: ReactNode
  className?: string
}

export function OptionGroup<T extends string>({
  label,
  value,
  onChange,
  children,
  className,
}: OptionGroupProps<T>) {
  return (
    <RadioGroup
      aria-label={label}
      className={className ? `${styles.group} ${className}` : styles.group}
      value={value}
      onChange={(next) => onChange(next as T)}
    >
      {children}
    </RadioGroup>
  )
}

/**
 * `value` is a plain string by design: a child cannot inherit its parent
 * OptionGroup's generic `T` through JSX, so option-key type-safety relies on
 * callers mapping from a typed key array (as App does — `originOptions`, etc.),
 * which is checked at the array. A future caller hand-writing literal values
 * would not get that check; prefer driving the group from a typed array.
 */
export type OptionButtonProps = {
  value: string
  children: ReactNode
  /** Optional accessible-name override for when the visible label alone lacks
   *  context (e.g. the region-grouped origin picker, whose visual group
   *  headers never reach the accessibility tree). Must CONTAIN the visible
   *  label (WCAG 2.5.3 label-in-name). */
  'aria-label'?: string
}

export function OptionButton({ value, children, 'aria-label': ariaLabel }: OptionButtonProps) {
  return (
    <Radio value={value} className={styles.option} aria-label={ariaLabel}>
      {children}
    </Radio>
  )
}
