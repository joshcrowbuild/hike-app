import { useState } from 'react'

import type { CardVM } from '../data/vm'
import { conditionKindLabels } from './ConditionStates'
import { ConditionChip } from './ConditionChip'
import { detailConditionChips } from './feedChips'
import * as styles from './DetailConditions.css'

const RECEIPT_ID = 'detail-condition-receipt'

const kindLabel = (kind: string): string => conditionKindLabels[kind] ?? kind

/**
 * Detail's per-kind conditions strip (Q6). The WarningBlock(s) above own
 * anything actionable; this is the calm reading layer. Tapping a chip that has
 * a sourced receipt reveals ONE line below the strip (source · age ·
 * confidence), swapping on each tap and collapsing again when the same chip is
 * tapped — the always-visible sourced list is retired. A chip with no receipt
 * (unavailable / not checked) is inert: there is no source to disclose.
 */
export function DetailConditions({ card }: { card: CardVM }) {
  const chips = detailConditionChips(card)
  // Keyed by chip INDEX, not kind: two chips can legitimately share a kind (a
  // claimed status + an unclaimed line), and a kind key would show the wrong
  // chip's receipt while both read aria-expanded (review fix).
  const [openIdx, setOpenIdx] = useState<number | null>(null)

  if (chips.length === 0) return null

  const open = openIdx != null && chips[openIdx]?.receipt ? chips[openIdx] : undefined
  const receipt = open?.receipt

  return (
    <div className={styles.block}>
      <p className={styles.heading}>Current conditions</p>
      <div className={styles.strip}>
        {chips.map((chip, i) => (
          <ConditionChip
            key={`${chip.kind}-${i}`}
            model={chip}
            interactive={!!chip.receipt}
            isOpen={chip.receipt ? i === openIdx : undefined}
            onToggle={chip.receipt ? () => setOpenIdx((k) => (k === i ? null : i)) : undefined}
            receiptRegionId={chip.receipt ? RECEIPT_ID : undefined}
          />
        ))}
      </div>
      <div id={RECEIPT_ID}>
        {open && receipt ? (
          <p className={styles.receipt}>
            <span className={styles.receiptKind}>{kindLabel(open.kind)}</span>
            <span className={styles.receiptMeta}>
              {[receipt.source, receipt.ageText, receipt.confidenceText].filter(Boolean).join(' · ')}
            </span>
          </p>
        ) : null}
      </div>
    </div>
  )
}
