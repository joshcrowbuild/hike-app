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
    // Actionability split: closure/permit-hard-stop -> blocked; heat/flow/advisory -> headsUp.
    // NOTE (open): `present` conflates a benign reading (73°F) with a hazard
    // (heat advisory) because ConditionStatusVM carries no severity — this is
    // what oversells the detail "N things to know". Fixing it honestly needs a
    // severity signal from the engine; not hackable in the frontend alone.
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

  const actionable = hasBlocked.length + hasHeadsUp.length

  // Nothing to act on: clear, or — honestly — unverified. An all-unknown trail
  // must NEVER read "closed" or "N things to know"; it reads as what it is: not
  // yet checked (Rule #1, source-or-silence). This is the fix for the false
  // "This trail is closed right now." the old EvidencePanel stub could emit.
  if (actionable === 0) {
    if (hasUnknown.length === 0) return { tier: 'clear', conclusion: 'Conditions look clear.' }
    if (hasUnknown.length === 1) {
      const k = hasUnknown[0].status.kind
      return { tier: 'unknown', conclusion: unknown(conditionKindLabels[k] || k) }
    }
    return { tier: 'unknown', conclusion: 'Conditions couldn’t be verified right now.' }
  }

  const mostSevereTier: ConditionTier = hasBlocked.length > 0 ? 'blocked' : 'headsUp'

  // Detail with several things to actually act on — count ONLY the actionable
  // ones (an unknown is not a "thing to know", it's a thing we couldn't check).
  if (mode === 'detail' && actionable > 1) {
    const numberWords = ['Zero', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven']
    const word = numberWords[actionable] ?? String(actionable)
    return { tier: mostSevereTier, conclusion: `${word} things to know before you go.` }
  }

  const primary = (hasBlocked.length > 0 ? hasBlocked : hasHeadsUp)[0].status
  const detailStr =
    lines.length > 0 ? (lines[0].body ?? lines[0].text) : conditionKindLabels[primary.kind] || primary.kind

  return {
    tier: mostSevereTier,
    conclusion: mostSevereTier === 'blocked' ? blocked(detailStr) : headsUp(detailStr),
  }
}
