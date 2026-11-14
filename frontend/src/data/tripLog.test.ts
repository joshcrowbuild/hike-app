import { afterEach, describe, expect, it } from 'vitest'
import {
  findTripLog,
  isTripLoggedOn,
  localDayKey,
  manualClientEpisodeId,
  rememberTripLog,
  resetTripLogsForTests,
} from './tripLog'

afterEach(() => resetTripLogsForTests())

// The backend's CLIENT_EPISODE_ID_PATTERN (api/schemas.py).
const SERVER_ID = /^[A-Za-z0-9_-]{1,64}$/

describe('manualClientEpisodeId (Epic 042 AC-1.3 — idempotency key)', () => {
  it('is deterministic for the same trail and day, so a re-submit dedupes server-side', () => {
    expect(manualClientEpisodeId('stony-man', '2026-11-13')).toBe(manualClientEpisodeId('stony-man', '2026-11-13'))
  })

  it('differs by trail and by day', () => {
    const base = manualClientEpisodeId('stony-man', '2026-11-13')
    expect(manualClientEpisodeId('old-rag', '2026-11-13')).not.toBe(base)
    expect(manualClientEpisodeId('stony-man', '2026-11-14')).not.toBe(base)
  })

  it('always satisfies the server pattern, even for trail ids with separators or unicode', () => {
    for (const trail of ['stony-man', 'osm:way:12345', 'ct:old rag/loop', 'Sentier é', 'x'.repeat(200)]) {
      expect(manualClientEpisodeId(trail, '2026-11-13')).toMatch(SERVER_ID)
    }
  })
})

describe('localDayKey', () => {
  it('is the LOCAL calendar day, zero-padded', () => {
    expect(localDayKey(new Date(2026, 0, 5, 23, 59))).toBe('2026-01-05')
    expect(localDayKey(new Date(2026, 10, 13, 0, 1))).toBe('2026-11-13')
  })
})

describe('trip log record', () => {
  const entry = { viewerId: 'josh', episodeId: 'ep:josh:a', trailId: 'stony-man', trailName: 'Stony Man Loop', day: '2026-11-13' }

  it('is scoped to the viewer — another account on this device never inherits "Logged today"', () => {
    rememberTripLog(entry)
    expect(isTripLoggedOn('josh', 'stony-man', '2026-11-13')).toBe(true)
    expect(isTripLoggedOn('ruby', 'stony-man', '2026-11-13')).toBe(false)
    expect(findTripLog('ruby', 'ep:josh:a')).toBeNull()
  })

  it('is per trail and per day', () => {
    rememberTripLog(entry)
    expect(isTripLoggedOn('josh', 'old-rag', '2026-11-13')).toBe(false)
    expect(isTripLoggedOn('josh', 'stony-man', '2026-11-14')).toBe(false)
  })

  it('re-recording the same episode replaces, never duplicates', () => {
    rememberTripLog(entry)
    rememberTripLog({ ...entry, trailName: 'Stony Man' })
    expect(findTripLog('josh', 'ep:josh:a')?.trailName).toBe('Stony Man')
    expect(JSON.parse(localStorage.getItem('adventure-planner:trip-logs') ?? '[]')).toHaveLength(1)
  })

  it('persists to localStorage so it survives a reload', () => {
    rememberTripLog(entry)
    expect(JSON.parse(localStorage.getItem('adventure-planner:trip-logs') ?? '[]')).toEqual([entry])
  })
})
