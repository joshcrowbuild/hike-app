import { Button } from '../Button'
import { Text } from '../Text'
import * as styles from './EmptyState.css'

export type EmptyStateProps = {
  /** The one binding constraint, named plainly (e.g. `No trails named "old rug" near here.`). */
  headline: string
  /** What still holds, or what to try — the loosening path (`messages.emptySearch`/`messages.emptyFilters`). */
  secondary: string
  /** The single reset/loosen CTA's label (e.g. "Clear search & browse", "Show trails up to 3 mi"). */
  cta: string
  /** Fires the CTA's one action. There is no second action — one obvious way forward, not a menu. */
  onAction: () => void
  className?: string
}

/**
 * EmptyState — search-no-match / filters-too-tight (design-system-v0.2.md
 * II.B). Both variants share this one shape: a headline naming the binding
 * constraint, a secondary line saying what still holds, and one reset/loosen
 * `Button`. Sourced copy comes from `copy/messages.ts`'s `emptySearch` /
 * `emptyFilters` — this component only carries the layout and treatment
 * (Law 4/6: constructive, never a dead end).
 */
export function EmptyState({ headline, secondary, cta, onAction, className }: EmptyStateProps) {
  const cls = className ? `${styles.container} ${className}` : styles.container
  return (
    <div className={cls} role="status">
      <Text role="body" as="p" className={styles.headline}>
        {headline}
      </Text>
      <Text role="bodySm" as="p" className={styles.secondary}>
        {secondary}
      </Text>
      <Button variant="primary" size="md" onPress={onAction} className={styles.cta}>
        {cta}
      </Button>
    </div>
  )
}
