import { describe, expect, it } from 'vitest'

import type { TuningState } from '../../types'
import { widenFrame } from '../widen'
import {
  mockRegionConditions,
  mockTrailConditions,
  rubyGate,
  runFeed,
  scoreTrail,
  trails,
} from './engine'

const base: TuningState = {
  origin: 'frontRoyal',
  when: 'weekendMorning',
  effort: 'moderate',
  party: 'solo',
  today: 'standard',
  readinessOn: false,
  prompt: '',
}

const stonyMan = trails.find((t) => t.id === 'stony-man')!
const oldRag = trails.find((t) => t.id === 'old-rag')!

describe('scoreTrail — readiness never penalizes rank (R2)', () => {
  it('is identical whether or not readiness is on', () => {
    for (const trail of trails) {
      const off = scoreTrail(trail, { ...base, readinessOn: false })
      const on = scoreTrail(trail, { ...base, readinessOn: true })
      expect(on).toBe(off)
    }
  })
})

describe('rubyGate — explicit hard constraint with a reason (R6)', () => {
  it('gates the scramble (Old Rag) with a stated reason', () => {
    expect(rubyGate(oldRag)).toMatch(/scramble/i)
  })

  it('lets a short ridge (Stony Man) through', () => {
    expect(rubyGate(stonyMan)).toBeNull()
  })
})

describe('runFeed — party gate is disclosed, not silent (R6)', () => {
  // A big-day frame is where Old Rag (Card C) actually enters the peer set, so
  // it is the frame that exercises the Ruby drop (v0.3 §10).
  const bigDayFrame: TuningState = { ...base, effort: 'bigDay' }

  it('sets aside Old Rag with Ruby in the party, and keeps it for solo', () => {
    const solo = runFeed({ ...bigDayFrame, party: 'solo' })
    expect(solo.kept.some(({ trail }) => trail.id === 'old-rag')).toBe(true)
    expect(solo.partySetAside).toHaveLength(0)

    const ruby = runFeed({ ...bigDayFrame, party: 'ruby' })
    expect(ruby.kept.some(({ trail }) => trail.id === 'old-rag')).toBe(false)
    expect(ruby.partySetAside.some(({ trail }) => trail.id === 'old-rag')).toBe(true)
  })

  it('does not surface a set-aside the user would not have seen anyway', () => {
    // At a moderate frame Old Rag is below the peer cut for solo, so switching
    // to Ruby should not noisily "set it aside".
    const ruby = runFeed({ ...base, effort: 'moderate', party: 'ruby' })
    expect(ruby.partySetAside.some(({ trail }) => trail.id === 'old-rag')).toBe(false)
  })

  it('caps the peer set at three', () => {
    expect(runFeed(base).kept.length).toBeLessThanOrEqual(3)
  })
})

describe('widenFrame — one proposed relaxation (R9)', () => {
  it('relaxes the today lean first, then effort', () => {
    expect(widenFrame({ ...base, today: 'seekShade' })?.next.today).toBe('standard')
    expect(widenFrame({ ...base, effort: 'easy' })?.next.effort).toBe('moderate')
    expect(widenFrame({ ...base, effort: 'bigDay' })).toBeNull()
  })
})

describe('mockRegionConditions — the This-feed card fixture (Epic 055 S6)', () => {
  it('targets Saturday for a weekend frame, with a Today/Sat/Sun toggle', () => {
    const rc = mockRegionConditions({ ...base, when: 'weekendMorning' })
    expect(rc.forecast?.targetKey).toBe('sat')
    expect(rc.forecast?.days.map((d) => d.key)).toEqual(['today', 'sat', 'sun'])
    // A hot today vs a mild Saturday — the temporal split the card exists for.
    expect(rc.forecast?.days.find((d) => d.key === 'today')?.highF).toBe(88)
    expect(rc.forecast?.days.find((d) => d.key === 'sat')?.highF).toBe(68)
  })

  it('targets today for a full-day frame, and tomorrow for a tomorrow-morning frame', () => {
    expect(mockRegionConditions({ ...base, when: 'fullDay' }).forecast?.targetKey).toBe('today')
    expect(mockRegionConditions({ ...base, when: 'tomorrowMorning' }).forecast?.targetKey).toBe('tomorrow')
  })

  it('carries the recent-rain reveal and a hedged, inferred mud read', () => {
    const rc = mockRegionConditions(base)
    expect(rc.recentPrecip?.total48hIn).toBe(1.2)
    expect(rc.mud?.provenance).toBe('inferred')
    expect(rc.mud?.statement.toLowerCase()).toContain('may') // always hedged (Rule #7)
  })
})

describe('mockTrailConditions — the strip exercises every state (Epic 055 S6)', () => {
  it('spreads all-fresh, one-stale, one-unavailable, amber, and terracotta across the set', () => {
    const flat = Object.values(mockTrailConditions)
    const states = new Set(flat.flatMap((t) => t.conditions.map((c) => c.state)))
    expect(states.has('present')).toBe(true)
    expect(states.has('no-hazard')).toBe(true)
    expect(states.has('stale-degraded')).toBe(true)
    expect(states.has('unavailable')).toBe(true)

    const severities = new Set(flat.flatMap((t) => t.warnings.map((w) => w.severity)))
    expect(severities.has('headsUp')).toBe(true) // amber
    expect(severities.has('blocked')).toBe(true) // terracotta

    // Old Rag's closure is a genuine barrier owning the closures kind (Q7).
    const oldRagWarn = mockTrailConditions['old-rag'].warnings[0]
    expect(oldRagWarn.kind).toBe('closures')
    expect(oldRagWarn.severity).toBe('blocked')
  })
})
