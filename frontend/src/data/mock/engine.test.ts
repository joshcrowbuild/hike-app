import { describe, expect, it } from 'vitest'

import type { TuningState } from '../../types'
import { widenFrame } from '../widen'
import { rubyGate, runFeed, scoreTrail, trails } from './engine'

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
