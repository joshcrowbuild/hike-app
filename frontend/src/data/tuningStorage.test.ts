import { afterEach, describe, expect, it } from 'vitest'

import type { TuningState } from '../types'
import { readStoredTuning, resetStoredTuningForTests, writeStoredTuning } from './tuningStorage'

const STORAGE_KEY = 'adventure-planner:tuning'

const TUNING: TuningState = {
  origin: 'ocracoke',
  when: 'fullDay',
  effort: 'bigDay',
  party: 'friends',
  today: 'bigViews',
  readinessOn: true,
  prompt: 'quieter',
}

afterEach(() => resetStoredTuningForTests())

describe('tuningStorage (craft review M4 — the frame survives a reload)', () => {
  it('round-trips the full tuning frame', () => {
    writeStoredTuning(TUNING)
    expect(readStoredTuning()).toEqual(TUNING)
  })

  it('returns null when nothing was ever stored', () => {
    expect(readStoredTuning()).toBeNull()
  })

  it('never persists a live "Near me" fix — a stored location would be a stale assertion', () => {
    writeStoredTuning({ ...TUNING, originCoords: { lat: 38.9, lon: -78.2 } })
    const raw = localStorage.getItem(STORAGE_KEY)!
    expect(raw).not.toContain('originCoords')
    expect(readStoredTuning()).toEqual(TUNING)
  })

  it('degrades corrupt JSON to a miss, never a throw', () => {
    localStorage.setItem(STORAGE_KEY, '{not json')
    expect(readStoredTuning()).toBeNull()
  })

  it('drops an entry from a different schema version', () => {
    writeStoredTuning(TUNING)
    const entry = JSON.parse(localStorage.getItem(STORAGE_KEY)!)
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...entry, v: 999 }))
    expect(readStoredTuning()).toBeNull()
  })

  it('drops an entry whose enum facet is not a known value (drop-on-any-doubt)', () => {
    writeStoredTuning(TUNING)
    const entry = JSON.parse(localStorage.getItem(STORAGE_KEY)!)
    entry.tuning.effort = 'ultramarathon'
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entry))
    expect(readStoredTuning()).toBeNull()
  })

  it('drops an entry with a missing or empty origin', () => {
    writeStoredTuning(TUNING)
    const entry = JSON.parse(localStorage.getItem(STORAGE_KEY)!)
    entry.tuning.origin = ''
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entry))
    expect(readStoredTuning()).toBeNull()
  })

  it('rebuilds the object on read — foreign extra keys never leak into app state', () => {
    writeStoredTuning(TUNING)
    const entry = JSON.parse(localStorage.getItem(STORAGE_KEY)!)
    entry.tuning.injected = 'junk'
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entry))
    expect(readStoredTuning()).toEqual(TUNING)
  })
})
