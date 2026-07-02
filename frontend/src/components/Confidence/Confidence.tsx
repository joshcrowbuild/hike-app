import type { ReactNode } from 'react'

import { srOnly } from '../../design/a11y.css'
import type { ConfidenceLevel } from '../../data/api'
import type { Provenance } from '../../data/vm'
import * as styles from './Confidence.css'

/**
 * Confidence is an honesty primitive (design-system-v0.1 §7.1): it presents how
 * sure a fact is *without ever showing a number*, and it refuses to dress
 * non-live data as verified (UX plan R1) — mock/sample values render demoted and
 * carry a visible "sample" tag. Meaning is carried by copy + treatment + an
 * sr-only lead-in, never by colour alone (§4.3, colour-blind safe).
 */
const leadIn: Record<ConfidenceLevel, string> = {
  stated: 'Verified',
  hedged: 'Likely',
  flagged: 'Unverified, verify before you go',
}

export type ConfidenceProps = {
  level: ConfidenceLevel
  /** Where the value came from; non-live demotes the treatment (R1). */
  provenance: Provenance
  children: ReactNode
  className?: string
}

export function Confidence({ level, provenance, children, className }: ConfidenceProps) {
  const live = provenance === 'live'
  // A flagged safety line keeps its accent even when sampled; everything else
  // non-live drops to the muted sample treatment.
  const tierKey = live ? level : level === 'flagged' ? 'flagged' : 'sample'
  // The sr-only lead-in must follow PROVENANCE, not just the tier: announcing
  // "Verified" over mock data would conceal the very thing the visual "sample"
  // tag discloses (R1, §4.3 — colour/visual is never the only cue).
  const announced = live ? leadIn[level] : level === 'flagged' ? leadIn.flagged : 'Sample, not verified'
  const cls = className ? `${styles.tier[tierKey]} ${className}` : styles.tier[tierKey]
  // "Verified" is the app's strongest trust cue, but it lived only in the
  // sr-only lead-in — invisible to sighted users (report #4/#7). A live,
  // stated fact gets a plain visible mark instead; every other tier keeps the
  // sr-only lead-in (their copy already hedges visibly: "seems to", "verify
  // before you go").
  const verified = live && level === 'stated'
  return (
    <span className={cls}>
      {verified ? (
        <span className={styles.verifiedMark} aria-hidden="true">
          ✓{' '}
        </span>
      ) : null}
      <span className={srOnly}>{announced}: </span>
      {children}
      {!live ? (
        <span className={styles.sampleTag} aria-hidden="true">
          sample
        </span>
      ) : null}
    </span>
  )
}
