import { stalePaint } from '../../copy/messages'
import { prefersReducedMotion } from '../../data/motion'
import { Text } from '../Text'
import * as styles from './UpdateChip.css'

export type UpdateChipProps = {
  /** The pill's label; defaults to `messages.stalePaint()` ("Updating conditions…"). */
  label?: string
  className?: string
}

/**
 * UpdateChip — the small "Updating conditions…" pill shown during a
 * background revalidate (design-system-v0.2.md II.B), the quiet chip that
 * replaces the cold-every-time skeleton on reload (states-gallery.html §5:
 * "Paint the last feed instantly; revalidate quietly behind a small chip").
 * The pulse dot honors `prefers-reduced-motion` the same way `SkeletonCard`
 * does: the animating class is only applied when JS-detected motion is
 * allowed (testable via `matchMedia`, unlike a CSS-only media query), with a
 * CSS `@media` guard as a second, belt-and-suspenders line of defense.
 */
export function UpdateChip({ label = stalePaint(), className }: UpdateChipProps) {
  const cls = className ? `${styles.chip} ${className}` : styles.chip
  const dotCls = prefersReducedMotion() ? styles.dot : `${styles.dot} ${styles.dotPulse}`
  return (
    <span className={cls} role="status">
      <span className={dotCls} aria-hidden="true" />
      <Text role="caption" as="span">
        {label}
      </Text>
    </span>
  )
}
