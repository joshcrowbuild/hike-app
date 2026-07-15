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

describe('ConditionStates block-scope freshness stamp (Epic 046 S1 AC-1.4 — collapse when the batch agrees, expand when a row diverges)', () => {
  it('renders ONE freshness stamp and drops every per-row age when the whole batch shares it', () => {
    const { container } = render(
      <ConditionStates
        conditions={[
          { kind: 'weather', state: 'present', source: 'NWS', checkedAgo: 'just now' },
          { kind: 'air', state: 'present', source: 'EPA', checkedAgo: 'just now' },
          { kind: 'fire', state: 'no-hazard', source: 'NASA FIRMS', checkedAgo: 'just now' },
        ]}
      />,
    )
    expect(container.querySelector('.condition-states-stamp')?.textContent).toBe('Checked just now')
    // Source stays on every row (it differs and carries info) — only the
    // now-redundant per-row age is gone.
    const metas = [...container.querySelectorAll('.condition-state-meta')]
    expect(metas.length).toBe(3)
    for (const meta of metas) expect(meta.textContent).not.toMatch(/just now/)
    expect(metas.map((m) => m.textContent)).toEqual([' · NWS', ' · EPA', ' · NASA FIRMS'])
  })

  it('keeps a diverging row\'s own age while the rest of the block collapses to the shared stamp', () => {
    const { container } = render(
      <ConditionStates
        conditions={[
          { kind: 'weather', state: 'present', source: 'NWS', checkedAgo: 'just now' },
          { kind: 'air', state: 'present', source: 'EPA', checkedAgo: 'just now' },
          {
            kind: 'water',
            state: 'no-data',
            source: 'USGS',
            checkedAgo: '2h ago',
            detail: 'no gauge within 30 mi',
          },
        ]}
      />,
    )
    expect(container.querySelector('.condition-states-stamp')?.textContent).toBe('Checked just now')
    const waterRow = container.querySelector('.condition-state--no-data')
    expect(waterRow?.textContent).toContain('2h ago')
    const weatherRow = container.querySelector('.condition-state--present')
    expect(weatherRow?.textContent).not.toMatch(/just now/)
  })

  it('renders no stamp and leaves every row\'s own age in place when nothing agrees', () => {
    const { container } = render(
      <ConditionStates
        conditions={[
          { kind: 'weather', state: 'present', source: 'NWS', checkedAgo: '12m ago' },
          { kind: 'fire', state: 'no-hazard', source: 'NASA FIRMS', checkedAgo: '20m ago' },
        ]}
      />,
    )
    expect(container.querySelector('.condition-states-stamp')).not.toBeInTheDocument()
    expect(container.querySelector('.condition-state--present')?.textContent).toContain('12m ago')
    expect(container.querySelector('.condition-state--no-hazard')?.textContent).toContain('20m ago')
  })

  it('never renders a shared "time unknown" stamp when multiple rows lack an age (Epic 046 S4 AC-4.2 — meshes with the S1 stamp-agreement set)', () => {
    // The httpPlanner mapping degrades an unparseable `checked_at` to
    // `undefined` (D6), never the literal 'time unknown' — so two rows that
    // both failed to parse their timestamp must never agree on a fabricated
    // shared stamp, and the token itself must never appear anywhere.
    const { container } = render(
      <ConditionStates
        conditions={[
          { kind: 'weather', state: 'present', source: 'NWS' },
          { kind: 'air', state: 'present', source: 'EPA' },
        ]}
      />,
    )
    expect(container.querySelector('.condition-states-stamp')).not.toBeInTheDocument()
    expect(container.textContent).not.toMatch(/time unknown/)
  })

  it('never folds a stale-degraded row\'s unconditional age into the block stamp', () => {
    const { container } = render(
      <ConditionStates
        conditions={[
          { kind: 'weather', state: 'present', source: 'NWS', checkedAgo: 'just now' },
          { kind: 'air', state: 'present', source: 'EPA', checkedAgo: 'just now' },
          { kind: 'water', state: 'stale-degraded', source: 'USGS', checkedAgo: 'just now' },
        ]}
      />,
    )
    // weather/air share "just now" (2 rows) → collapses; the stale-degraded row
    // is excluded from that agreement and keeps wearing its own hedge regardless.
    expect(container.querySelector('.condition-states-stamp')?.textContent).toBe('Checked just now')
    const staleRow = container.querySelector('.condition-state--stale-degraded')
    expect(staleRow?.textContent).toContain('just now')
    expect(staleRow?.textContent).toContain('may have changed')
  })
})

describe('ConditionStates (compact card summary)', () => {
  it('groups kinds by state into one calm row each, stating a shared age once and keeping per-kind source (Epic 046 S1 AC-1.5 / A4)', () => {
    const { container } = render(
      <ConditionStates
        compact
        conditions={[
          { kind: 'fire', state: 'no-hazard', source: 'NASA FIRMS', checkedAgo: '20m ago' },
          { kind: 'closures', state: 'no-hazard', source: 'NPS', checkedAgo: '20m ago' },
          { kind: 'air', state: 'not-fetched' },
          { kind: 'permits', state: 'not-fetched' },
        ]}
      />,
    )
    const groups = container.querySelectorAll('.condition-state-group')
    expect(groups).toHaveLength(2)
    const clear = container.querySelector('.condition-state-group.condition-state--no-hazard')
    // The shared age states once for the group — never per kind (A4's finding:
    // "Fire (NASA · just now), Closures (NPS · just now)" repeated the age).
    expect(clear?.textContent).toContain('Checked — nothing to flag · 20m ago: Fire (NASA FIRMS), Closures (NPS)')
    const unchecked = container.querySelector('.condition-state-group.condition-state--not-fetched')
    expect(unchecked?.textContent).toContain('Not checked here: Air quality, Permits')
  })

  it('keeps a diverging member\'s own age while the rest of the group collapses to the shared one', () => {
    const { container } = render(
      <ConditionStates
        compact
        conditions={[
          { kind: 'fire', state: 'no-hazard', source: 'NASA FIRMS', checkedAgo: '20m ago' },
          { kind: 'closures', state: 'no-hazard', source: 'NPS', checkedAgo: '20m ago' },
          { kind: 'water', state: 'no-hazard', source: 'USGS', checkedAgo: '2h ago' },
        ]}
      />,
    )
    const clear = container.querySelector('.condition-state-group.condition-state--no-hazard')
    expect(clear?.textContent).toContain(
      'Checked — nothing to flag · 20m ago: Fire (NASA FIRMS), Closures (NPS), Streamflow (USGS · 2h ago)',
    )
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
