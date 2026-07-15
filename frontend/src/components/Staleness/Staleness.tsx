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
  // A missing/blank age (Epic 046 S4 AC-4.2, e.g. a caller degrading an
  // unparseable timestamp to "no stamp") renders NOTHING — never an empty tag
  // standing in for a stamp that doesn't exist. The caller's own guard is the
  // primary defence; this is the primitive's own last line of it.
  if (children == null || children === '') return null
  const tier = stale ? styles.stale : styles.fresh
  const cls = className ? `${tier} ${className}` : tier
  return <span className={cls}>{children}</span>
}
