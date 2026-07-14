import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { ConditionStatusVM, LineVM } from '../data/vm'
import { ConditionStates } from './ConditionStates'

/**
 * The six per-kind condition states (Epic 018 S4f / CDP-02). The load-bearing
 * honesty properties: every state renders visibly distinct (glyph + copy, never
 * colour alone); checked-clear is calm sourced silence, never a loud
 * "0 detections"; and an outage (unavailable) can never be mistaken for a kind
 * that was simply not checked (not-fetched).
 */

const ALL_SIX: ConditionStatusVM[] = [
  { kind: 'weather', state: 'present', source: 'NWS', checkedAgo: '12m ago' },
  { kind: 'air', state: 'stale-degraded', source: 'EPA AirNow', checkedAgo: '3h ago' },
  { kind: 'fire', state: 'no-hazard', source: 'NASA FIRMS', checkedAgo: '20m ago' },
  { kind: 'water', state: 'no-data', source: 'USGS', checkedAgo: '15m ago', detail: 'no gauge within 30 mi' },
  { kind: 'closures', state: 'unavailable' },
  { kind: 'permits', state: 'not-fetched' },
]

describe('ConditionStates (full coverage list)', () => {
  it('renders one row per kind with its human label and a state-distinct class', () => {
    const { container } = render(<ConditionStates conditions={ALL_SIX} />)
    const rows = container.querySelectorAll('.condition-state')
    expect(rows).toHaveLength(6)
    for (const s of ALL_SIX) {
      expect(container.querySelector(`.condition-state--${s.state}`)).toBeInTheDocument()
    }
    expect(screen.getByText('Air quality')).toBeInTheDocument()
    expect(screen.getByText('Streamflow')).toBeInTheDocument()
  })

  it('gives the states pairwise-distinct visible copy — never the same gray twice (AC-4f.1)', () => {
    const { container } = render(<ConditionStates conditions={ALL_SIX} />)
    const bodies = [...container.querySelectorAll('.condition-state-body')].map((el) => el.textContent?.trim() ?? '')
    expect(bodies).toHaveLength(6)
    expect(new Set(bodies).size).toBe(bodies.length)
  })

  it('renders checked-clear as CALM sourced silence — source + age kept, no "0 detections" noise', () => {
    const { container } = render(
      <ConditionStates conditions={[{ kind: 'fire', state: 'no-hazard', source: 'NASA FIRMS', checkedAgo: '20m ago' }]} />,
    )
    const row = container.querySelector('.condition-state--no-hazard')
    expect(row?.textContent).toContain('checked — nothing to flag')
    expect(row?.textContent).toContain('NASA FIRMS')
    expect(row?.textContent).toContain('20m ago')
    expect(row?.textContent).not.toMatch(/0 detections|0 hotspots|zero/i)
  })

  it('renders an outage visibly different from not-fetched — copy, treatment, and announcement all differ', () => {
    const { container } = render(
      <ConditionStates
        conditions={[
          { kind: 'closures', state: 'unavailable' },
          { kind: 'permits', state: 'not-fetched' },
        ]}
      />,
    )
    const outage = container.querySelector('.condition-state--unavailable')
    const unchecked = container.querySelector('.condition-state--not-fetched')
    // The outage routes through flagged <Confidence>: the verify accent AND the
    // "Unverified, verify before you go" sr-only lead-in.
    expect(outage?.textContent).toContain('couldn’t be verified right now')
    expect(outage?.textContent).toContain('Unverified, verify before you go')
    expect(unchecked?.textContent).toContain('not checked here')
    expect(unchecked?.textContent).not.toContain('verify before you go')
    // Not-fetched keeps its own quiet glyph; the outage carries none of its own.
    expect(unchecked?.querySelector('.condition-state-glyph')?.textContent).toBe('○')
  })

  it('wears stale-degraded age through <Staleness stale> with the may-have-changed hedge', () => {
    const { container } = render(
      <ConditionStates conditions={[{ kind: 'water', state: 'stale-degraded', source: 'USGS', checkedAgo: '3h ago' }]} />,
    )
    const row = container.querySelector('.condition-state--stale-degraded')
    expect(row?.textContent).toContain('last known')
    expect(row?.textContent).toContain('3h ago')
    expect(row?.textContent).toContain('may have changed')
    // The real Lucide History mark, never a text glyph (AC-20.3.1).
    expect(row?.querySelector('.condition-state-glyph svg')).toBeInTheDocument()
  })

  it('keeps the may-have-changed hedge on a stale row even without an age — never a bare current-looking value', () => {
    const { container } = render(
      <ConditionStates conditions={[{ kind: 'water', state: 'stale-degraded', source: 'USGS' }]} />,
    )
    expect(container.querySelector('.condition-state--stale-degraded')?.textContent).toContain('may have changed')
  })

  it('carries the adapter disclosure on a no-data row', () => {
    render(
      <ConditionStates
        conditions={[{ kind: 'water', state: 'no-data', source: 'USGS', detail: 'no gauge within 30 mi' }]}
      />,
    )
    expect(screen.getByText(/no coverage here — no gauge within 30 mi/)).toBeInTheDocument()
  })

  it('falls back to the raw wire kind for an unknown kind — disclosed, never dropped', () => {
    render(<ConditionStates conditions={[{ kind: 'avalanche', state: 'not-fetched' }]} />)
    expect(screen.getByText('avalanche')).toBeInTheDocument()
  })

  it('renders nothing for an empty payload', () => {
    const { container } = render(<ConditionStates conditions={[]} />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe('ConditionStates folds a matching line\'s value into its row (ux-review 2026-07 Finding 4/7)', () => {
  const lines: LineVM[] = [
    { text: 'Sunny 90°F', source: 'NWS', confidence: 'stated', provenance: 'live' },
    { text: 'AQI 45 (Good)', source: 'EPA', confidence: 'hedged', provenance: 'live' },
  ]

  it('folds a present row\'s matching line by source, ahead of the disposition label', () => {
    const { container } = render(
      <ConditionStates conditions={[{ kind: 'weather', state: 'present', source: 'NWS', checkedAgo: '4m ago' }]} lines={lines} />,
    )
    const row = container.querySelector('.condition-state--present')
    expect(row?.querySelector('.condition-state-value')?.textContent).toBe('Sunny 90°F · ')
    expect(row?.textContent).toContain('reported')
  })

  it('folds a stale-degraded row\'s matching line too', () => {
    const { container } = render(
      <ConditionStates
        conditions={[{ kind: 'weather', state: 'stale-degraded', source: 'NWS', checkedAgo: '3h ago' }]}
        lines={lines}
      />,
    )
    expect(container.querySelector('.condition-state-value')?.textContent).toBe('Sunny 90°F · ')
  })

  it('never folds a value into a no-hazard/no-data/unavailable/not-fetched row — only present/stale-degraded carry a value', () => {
    const { container } = render(
      <ConditionStates conditions={[{ kind: 'fire', state: 'no-hazard', source: 'NASA FIRMS', checkedAgo: '20m ago' }]} lines={lines} />,
    )
    expect(container.querySelector('.condition-state-value')).not.toBeInTheDocument()
  })

  it('a repeated source is consumed by only the FIRST matching row — never fanned to every row sharing it', () => {
    const twoNWS: ConditionStatusVM[] = [
      { kind: 'weather', state: 'present', source: 'NWS', checkedAgo: '4m ago' },
      { kind: 'fire', state: 'present', source: 'NWS', checkedAgo: '4m ago' },
    ]
    const oneLine: LineVM[] = [{ text: 'Sunny 90°F', source: 'NWS', confidence: 'stated', provenance: 'live' }]
    const { container } = render(<ConditionStates conditions={twoNWS} lines={oneLine} />)
    const values = [...container.querySelectorAll('.condition-state-value')]
    expect(values).toHaveLength(1)
    expect(values[0].textContent).toBe('Sunny 90°F · ')
  })

  it('a row with no matching source folds no value (never fabricates one)', () => {
    const { container } = render(
      <ConditionStates conditions={[{ kind: 'weather', state: 'present', source: 'NWS', checkedAgo: '4m ago' }]} lines={[]} />,
    )
    expect(container.querySelector('.condition-state-value')).not.toBeInTheDocument()
  })
})

describe('ConditionStates (compact card summary)', () => {
  it('groups kinds by state into one calm row each, keeping per-kind source + age', () => {
    const { container } = render(
      <ConditionStates
        compact
        conditions={[
          { kind: 'fire', state: 'no-hazard', source: 'NASA FIRMS', checkedAgo: '20m ago' },
          { kind: 'closures', state: 'no-hazard', source: 'NPS', checkedAgo: '1h ago' },
          { kind: 'air', state: 'not-fetched' },
          { kind: 'permits', state: 'not-fetched' },
        ]}
      />,
    )
    const groups = container.querySelectorAll('.condition-state-group')
    expect(groups).toHaveLength(2)
    const clear = container.querySelector('.condition-state-group.condition-state--no-hazard')
    expect(clear?.textContent).toContain('Checked — nothing to flag: Fire (NASA FIRMS · 20m ago), Closures (NPS · 1h ago)')
    const unchecked = container.querySelector('.condition-state-group.condition-state--not-fetched')
    expect(unchecked?.textContent).toContain('Not checked here: Air quality, Permits')
  })

  it('routes a compact outage row through the flagged couldn’t-verify treatment', () => {
    const { container } = render(
      <ConditionStates compact conditions={[{ kind: 'weather', state: 'unavailable' }]} />,
    )
    const row = container.querySelector('.condition-state-group.condition-state--unavailable')
    expect(row?.textContent).toContain('Couldn’t verify: Weather')
    expect(row?.textContent).toContain('Unverified, verify before you go')
  })

  it('never renders a present kind in the compact summary’s state groups', () => {
    const { container } = render(
      <ConditionStates compact conditions={[{ kind: 'weather', state: 'present', source: 'NWS' }]} />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})
