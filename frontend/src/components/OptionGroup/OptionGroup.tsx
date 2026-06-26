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

export type OptionButtonProps = {
  value: string
  children: ReactNode
}

export function OptionButton({ value, children }: OptionButtonProps) {
  return (
    <Radio value={value} className={styles.option}>
      {children}
    </Radio>
  )
}
