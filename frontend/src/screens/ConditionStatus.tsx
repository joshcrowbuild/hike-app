import { Icon } from '../components'
import type { ConditionStatusVM, LineVM } from '../data/vm'
import type { ConditionTier, ConditionTierMapper } from '../design/contracts'
import { blocked, headsUp, unknown } from '../copy/messages'
import { tierGlyphs } from './glyphs'
import { conditionKindLabels } from './ConditionStates'
import * as styles from './ConditionStatus.css'

/**
 * 1. Pure function mapping the six coverage states to the 4-tier signal system.
 */
export const toTier: ConditionTierMapper = (status: ConditionStatusVM): ConditionTier => {
  if (status.state === 'no-hazard') return 'clear'
  if (status.state === 'present') {
    // Actionability split: closure/permit-hard-stop -> blocked; heat/flow/advisory -> headsUp
    if (status.kind === 'closures' || status.kind === 'permits') {
      return 'blocked'
    }
    return 'headsUp'
  }
  // no-data | unavailable | not-fetched | stale-degraded -> unknown
  return 'unknown'
}

/**
 * 2. Renders the condition status line. Renders nothing for 'clear'.
 */
export function ConditionStatusLine({
  tier,
  copy,
  source,
}: {
  tier: ConditionTier
  copy: string
  source?: string
}) {
  if (tier === 'clear') return null

  const Glyph = tierGlyphs[tier as Exclude<ConditionTier, 'clear'>]

  return (
    <div className={styles.statusLine[tier as Exclude<ConditionTier, 'clear'>]}>
      {Glyph ? <Icon glyph={Glyph} label={tier} className={styles.statusLineIcon} /> : null}
      <span className={styles.statusLineText}>
        {copy}
        {source ? ` (${source})` : null}
      </span>
    </div>
  )
}

/**
 * 3. Card-level summarizer: given a card's conditions, return the single
 * most-severe tier + a conclusion string.
 */
export function summarizeConditions(
  conditions: ConditionStatusVM[],
  lines: LineVM[],
  mode: 'card' | 'detail' = 'card'
): { tier: ConditionTier; conclusion: string } | null {
  if (!conditions || conditions.length === 0) return null

  const mapped = conditions.map((c) => ({ status: c, tier: toTier(c) }))
  
  const hasBlocked = mapped.filter((m) => m.tier === 'blocked')
  const hasHeadsUp = mapped.filter((m) => m.tier === 'headsUp')
  const hasUnknown = mapped.filter((m) => m.tier === 'unknown')

  const severe = hasBlocked.length > 0 ? hasBlocked :
                 hasHeadsUp.length > 0 ? hasHeadsUp :
                 hasUnknown.length > 0 ? hasUnknown : []

  if (severe.length === 0) {
    return { tier: 'clear', conclusion: 'Conditions look clear.' }
  }

  const mostSevereTier = severe[0].tier

  if (mode === 'detail' && (hasBlocked.length + hasHeadsUp.length + hasUnknown.length) > 1) {
    const total = hasBlocked.length + hasHeadsUp.length + hasUnknown.length
    const numberWords = ['Zero', 'One', 'Two', 'Three', 'Four', 'Five', 'Six']
    const word = numberWords[total] || total.toString()
    return { tier: mostSevereTier, conclusion: `${word} things to know` }
  }

  const first = severe[0].status
  if (mostSevereTier === 'unknown') {
    return {
      tier: 'unknown',
      conclusion: unknown(conditionKindLabels[first.kind] || first.kind),
    }
  }

  // Get detail string from the primary line
  const detailStr = lines.length > 0 ? (lines[0].body ?? lines[0].text) : 'Action required'

  return {
    tier: mostSevereTier,
    conclusion: mostSevereTier === 'blocked' ? blocked(detailStr) : headsUp(detailStr),
  }
}
