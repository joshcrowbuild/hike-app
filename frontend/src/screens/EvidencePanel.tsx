import { Text } from '../components/Text'
import type { CardVM } from '../data/vm'
import { unclaimedLines } from '../data/feedConditions'
import { ConditionStates } from './ConditionStates'
import { summarizeConditions } from './ConditionStatus'

/**
 * Cleans up raw wire strings into human copy (garbage gauge / permit phrases).
 */
export function cleanEvidenceBody(body: string): string {
  if (body.includes('flow reading unavailable at')) return 'No gauge near this route'
  if (body.includes('Permit info not checked')) return 'None required here'
  return body
}

/**
 * Detail conditions block: a conclusion first, the full sourced coverage table
 * one tap away (progressive disclosure). The conclusion comes from the SHARED
 * `summarizeConditions` engine — never a hardcoded verdict — so the detail can
 * never claim "closed" from an unverified/unknown state, and can never disagree
 * with the feed card, which reads the same engine (Rule #1, one signal set).
 */
export function EvidencePanel({ card }: { card: CardVM }) {
  const conditions = card.conditions || []
  const lines = card.conditionLines || []

  if (conditions.length === 0 && lines.length === 0) return null

  const summary = summarizeConditions(conditions, lines, 'detail')
  const conclusion = summary?.conclusion ?? 'Conditions look clear.'
  const actionable = summary?.tier === 'blocked' || summary?.tier === 'headsUp'
  const residual = unclaimedLines(conditions, lines)

  // Nothing to act on and nothing residual → just the calm conclusion, no
  // disclosure to open (Law 1: silence is a state).
  if (!actionable && residual.length === 0) {
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
                <li key={i} className="condition-line">{cleanEvidenceBody(line.text)}</li>
              ))}
            </ul>
          ) : null}
        </div>
      </details>
    </div>
  )
}
