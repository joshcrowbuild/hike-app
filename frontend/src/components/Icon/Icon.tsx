import type { LucideIcon } from 'lucide-react'

import { srOnly } from '../../design/a11y.css'
import * as styles from './Icon.css'

export type IconProps = {
  /**
   * The Lucide glyph to render, passed as the component itself (e.g. `Car`).
   * One meaning per glyph across the whole surface (DD2) — the mapping lives at
   * the call site so this wrapper stays meaning-agnostic.
   */
  glyph: LucideIcon
  /**
   * A REQUIRED visually-hidden label. An icon is never a naked, unlabeled glyph:
   * the glyph itself is `aria-hidden` decoration, and this sr-only text is what
   * assistive tech actually reads (AC-21.1.1 / AC-21.3.1). When the icon rides a
   * control that already owns an `aria-label` (Save, Directions), that label
   * overrides this one — belt-and-suspenders, never a conflicting second name.
   */
  label: string
  className?: string
}

/**
 * Icon renders a Lucide glyph as a leading accent + its required sr-only label.
 * It carries no behaviour and no colour of its own (see Icon.css): the glyph
 * inherits `currentColor` and sizes to `1em`, so it tracks the text it sits
 * beside in both themes. Placement (the gap to the following word) is the
 * consumer's concern — pass `className` to position it.
 */
export function Icon({ glyph: Glyph, label, className }: IconProps) {
  return (
    <span className={className ? `${styles.icon} ${className}` : styles.icon}>
      <Glyph className={styles.glyph} aria-hidden="true" focusable={false} />
      <span className={srOnly}>{label}</span>
    </span>
  )
}
