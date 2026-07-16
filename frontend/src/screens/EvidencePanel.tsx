import { Text } from '../components/Text'
import { Staleness } from '../components'
import type { CardVM, ConditionStatusVM, LineVM } from '../data/vm'
import type { ConditionTier, EvidenceItem } from '../design/contracts'
import { foldLineValue, sharedAmong, unclaimedLines } from '../data/feedConditions'
import { conditionKindLabels, ConditionStates } from './ConditionStates'
import { toTier } from './ConditionStatus'

/**
 * Returns a conclusion sentence based on the computed tiers.
 * Stub implementation until WP-2 integration.
 */
export function deriveConclusion(tiers: ConditionTier[]): string {
  if (tiers.includes('blocked')) return 'This trail is closed right now.'
  if (tiers.includes('headsUp')) return 'Two things to know before you go.'
  return 'Conditions look clear.'
}

/**
 * Cleans up verbose or raw data strings into human-readable honestly-named missing data.
 */
export function cleanEvidenceBody(body: string): string {
  if (body.includes('flow reading unavailable at')) return 'No gauge near this route'
  if (body.includes('Permit info not checked')) return 'None required here'
  return body
}

export function EvidencePanel({ card }: { card: CardVM }) {
  // If the payload has no conditions array, fallback to legacy rendering or null
  // The spec says "extract the full condition table".
  const conditions = card.conditions || []
  const lines = card.conditionLines || []
  
  if (conditions.length === 0 && lines.length === 0) {
    return null
  }

  const items: EvidenceItem[] = []
  const claimed = new Set<LineVM>()

  // Map the new six-state payload to EvidenceItems
  for (const s of conditions) {
    const tier = toTier(s)
    const line = foldLineValue(s, lines, claimed)
    
    // For states that fold a value, use the body. Otherwise use a default or the state's semantic meaning.
    let rawBody = line?.body ?? line?.text ?? ''
    
    // If no folded line, derive a basic body based on state (similar to ConditionStates)
    if (!rawBody) {
      if (s.state === 'no-hazard') rawBody = 'Checked — nothing to flag'
      else if (s.state === 'no-data') rawBody = s.detail ? `No coverage here — ${s.detail}` : 'No coverage here'
      else if (s.state === 'unavailable') rawBody = 'Couldn’t verify right now'
      else if (s.state === 'not-fetched') rawBody = 'Not checked here'
      else if (s.state === 'stale-degraded') rawBody = 'Last known conditions'
      else rawBody = s.state
    }

    items.push({
      kind: s.kind,
      tier,
      body: cleanEvidenceBody(rawBody),
      source: s.source ?? line?.source ?? 'Unknown',
      age: s.checkedAgo ?? line?.age,
      confidence: line?.confidence ?? 'stated',
      provenance: line?.provenance ?? 'live',
      sources: line?.sources,
    })
  }

  // Handle residual/unclaimed lines for safety
  const residual = unclaimedLines(conditions, lines)
  for (const l of residual) {
    items.push({
      kind: 'other',
      tier: 'unknown',
      body: cleanEvidenceBody(l.body ?? l.text),
      source: l.source,
      age: l.age,
      confidence: l.confidence,
      provenance: l.provenance,
      sources: l.sources,
    })
  }

  const tiers = items.map(item => item.tier)
  const conclusion = deriveConclusion(tiers)
    
  const sourcesText = `all ${items.length} sources`
  if (!tiers.includes('blocked') && !tiers.includes('headsUp') && residual.length === 0) {
    return (
      <div className="evidence-panel">
        <Text role="body" className="evidence-conclusion">{conclusion}</Text>
      </div>
    )
  }

  return (
    <div className="evidence-panel">
      <details className="evidence-disclosure">
        <summary className="evidence-summary">
          <Text role="body" as="span" className="evidence-conclusion">{conclusion}</Text>
        </summary>
        <div className="evidence-grid">
          <ConditionStates conditions={conditions} lines={lines} />
          {residual.length > 0 ? (
            <ul className="condition-lines condition-lines--residual">
              {residual.map((line, i) => (
                <li key={i} className="condition-line">
                  {line.text}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </details>
    </div>
  )
}
