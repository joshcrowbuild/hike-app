import type { LucideIcon } from 'lucide-react'

import { Icon } from '../Icon'
import { Text } from '../Text'
import * as styles from './MetricRow.css'

export type MetricKind = 'distance' | 'ascent' | 'duration'

export interface MetricItem {
  kind: MetricKind
  /** The visible + accessible label (e.g. "Distance"). */
  label: string
  /** A pre-formatted value (e.g. "3.2 mi"). Omit/null/empty when unknown — the
   *  row still renders a NAMED disclosure for that kind, never a bare "—". */
  value?: string | null
  glyph?: LucideIcon
}

/**
 * The honest disclosure per kind when a value is unknown (design-system-v0.2
 * II.A: "missing values render NAMED ... never '—'"). Keyed by `kind` rather
 * than derived from `label` so the copy stays exact regardless of how a
 * caller phrases the visible label.
 */
const UNAVAILABLE_TEXT: Record<MetricKind, string> = {
  distance: 'distance unavailable',
  ascent: 'ascent unavailable',
  duration: 'time unavailable',
}

export type MetricRowProps = {
  items: MetricItem[]
  className?: string
}

/**
 * MetricRow — the distance/ascent/duration decision-fact row (design-system-
 * v0.2.md II.A), re-tokened onto the v0.2 role scale: values in `type.metric`
 * (mono, tabular-nums, so a numeric column aligns) and labels in
 * `type.metric-label` (sentence case, muted — D2/Law 5). A missing value
 * never collapses to a bare "—": it names what's unavailable, so a real gap
 * reads as an honest disclosure rather than a rendering glitch (source-or-
 * silence, Rule #1).
 *
 * Renders nothing for an empty `items` list — there's no trail-shaped row to
 * disclose a gap in, mirroring `cardParts.tsx#DecisionFacts`'s same rule.
 */
export function MetricRow({ items, className }: MetricRowProps) {
  if (items.length === 0) return null
  return (
    <div className={className ? `${styles.row} ${className}` : styles.row} role="list">
      {items.map((item) => {
        const hasValue = item.value != null && item.value !== ''
        return (
          <div key={item.kind} className={styles.item} role="listitem">
            <span className={styles.label}>
              {item.glyph ? <Icon glyph={item.glyph} label={item.label} className={styles.icon} /> : null}
              {/* The icon's sr-only label already carries the word to assistive
                  tech when a glyph is present; hide the visible echo so the
                  label is announced once, not twice (mirrors DecisionItem). */}
              <Text role="metricLabel" as="span" aria-hidden={item.glyph ? 'true' : undefined}>
                {item.label}
              </Text>
            </span>
            {hasValue ? (
              <Text role="metric" as="span" className={styles.value}>
                {item.value}
              </Text>
            ) : (
              <Text role="bodySm" as="span" className={styles.unavailable}>
                {UNAVAILABLE_TEXT[item.kind]}
              </Text>
            )}
          </div>
        )
      })}
    </div>
  )
}
