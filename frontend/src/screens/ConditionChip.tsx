import { Clock, Construction, Flame, Sun, Ticket, Waves, Wind } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

import { Icon } from '../components'
import { srOnly } from '../design/a11y.css'
import type { ConditionChipModel } from '../design/contracts'
import { conditionKindLabels } from './ConditionStates'
import * as styles from './ConditionChip.css'

/**
 * The DD2-consistent glyph per condition kind — mapping at the call site (Icon
 * stays meaning-agnostic). Streamflow uses `Waves`, deliberately NOT the
 * `Droplet` the DD2 registry reserves for a MAPPED water source (a trail fact,
 * never the live streamflow kind). An unmapped kind renders no glyph rather
 * than borrow a meaning that belongs to another kind.
 */
const KIND_GLYPH: Record<string, LucideIcon> = {
  weather: Sun,
  air: Wind,
  fire: Flame,
  water: Waves,
  closures: Construction,
  permits: Ticket,
}

const kindLabel = (kind: string): string => conditionKindLabels[kind] ?? kind

export interface ConditionChipProps {
  model: ConditionChipModel
  /**
   * Detail only (Q6): render as a disclosure button that reveals a receipt on
   * tap. `isOpen`/`onToggle` drive the single receipt line the parent renders
   * below the strip. Read-only in the This-feed card (the receipt is a
   * commitment-view act, never glanceable there).
   */
  interactive?: boolean
  isOpen?: boolean
  onToggle?: () => void
  /** The id of the receipt region a tap reveals (wires `aria-controls`). */
  receiptRegionId?: string
}

/**
 * One glyph+value chip. `pending` shimmers a placeholder (phase-2 in flight);
 * `fresh` shows the mono value; `stale` recedes to a dashed box with a gray
 * clock+age (staleness is unknown-family — no alarm colour, Law 7);
 * `unavailable` is a dashed italic "—". A warning-owned kind tints the whole
 * chip its tier accent (Q5/Q7) — the strip flags which kind, the WarningBlock
 * says what.
 */
export function ConditionChip({ model, interactive, isOpen, onToggle, receiptRegionId }: ConditionChipProps) {
  const { kind, valueText, state, tier, ageText } = model
  const Glyph = KIND_GLYPH[kind]
  const label = kindLabel(kind)
  const tinted = tier === 'headsUp' || tier === 'blocked'

  const className = [
    interactive ? styles.button : styles.chip,
    styles.state[state],
    tinted ? styles.tint[tier] : undefined,
  ]
    .filter(Boolean)
    .join(' ')

  const body =
    state === 'pending' ? (
      <>
        <span className={srOnly}>{label}: checking…</span>
        <span className={styles.pendingBar} aria-hidden="true" />
      </>
    ) : (
      <>
        {Glyph ? (
          <Icon glyph={Glyph} label={label} className={tinted ? `${styles.glyph} ${styles.tintInk}` : styles.glyph} />
        ) : (
          <span className={srOnly}>{label}: </span>
        )}
        <span
          className={[
            styles.value,
            state === 'stale' ? styles.staleValue : undefined,
            state === 'unavailable' ? styles.unavailableValue : undefined,
            tinted ? styles.tintInk : undefined,
          ]
            .filter(Boolean)
            .join(' ')}
        >
          {valueText}
        </span>
        {state === 'stale' && ageText ? (
          <span className={styles.age}>
            <Clock size={11} aria-hidden="true" focusable={false} />
            {ageText}
          </span>
        ) : null}
      </>
    )

  if (interactive) {
    return (
      <button
        type="button"
        className={className}
        onClick={onToggle}
        aria-expanded={isOpen ?? false}
        aria-controls={receiptRegionId}
      >
        {body}
      </button>
    )
  }

  return <span className={className}>{body}</span>
}
