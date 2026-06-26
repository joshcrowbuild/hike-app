import type { ReactNode } from 'react'

import * as styles from './Staleness.css'

/**
 * Staleness is an honesty primitive (design-system-v0.1 §7.2): it shows a fact's
 * age as a relative-time string and demotes (never reorders) once stale. The
 * caller passes the already-formatted relative time ("48m old", "from a hike
 * last fall"); raw datetimes are forbidden.
 */
export type StalenessProps = {
  children: ReactNode
  /** Past the rate-of-change threshold → demoted treatment (still never reordered). */
  stale?: boolean
  className?: string
}

export function Staleness({ children, stale = false, className }: StalenessProps) {
  const tier = stale ? styles.stale : styles.fresh
  const cls = className ? `${tier} ${className}` : tier
  return <span className={cls}>{children}</span>
}
