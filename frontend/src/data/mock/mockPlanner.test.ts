import { describe, expect, it } from 'vitest'

import { ANON_SCOPE } from '../api'
import type { ScopeContext } from '../api'
import type { TuningState } from '../../types'
import { MockPlannerClient } from './mockPlanner'

const JOSH: ScopeContext = { viewerId: 'josh', grantedIds: [] }

const frame: TuningState = {
  origin: 'frontRoyal',
  when: 'weekendMorning',
  effort: 'moderate',
  party: 'solo',
  today: 'standard',
  readinessOn: false,
  prompt: '',
}

const client = new MockPlannerClient()

describe('MockPlannerClient — provenance is disclosed (R1)', () => {
  it('marks every card and the feed as mock, never live', async () => {
    const feed = await client.plan({ tuning: frame }, JOSH)
    expect(feed.dataSource).toBe('mock')
    for (const card of feed.cards) {
      expect(card.enrichment?.provenance).toBe('mock')
      for (const line of card.conditionLines) expect(line.provenance).toBe('mock')
    }
  })

  it('never populates a mock line’s per-fact sources from the card-level enrichment list (Epic 026a AC-26.1.2)', async () => {
    // `enrichment.sources` is the illustrative card-level list (often 2-3 entries);
    // a mock condition line carries no per-fact `sources` at all — filling it from
    // that list would fabricate live corroboration on a non-live line.
    const feed = await client.plan({ tuning: frame }, JOSH)
    for (const card of feed.cards) {
      expect(card.enrichment?.sources?.length).toBeGreaterThan(0)
      for (const line of card.conditionLines) expect(line.sources).toBeUndefined()
    }
  })
})

describe('MockPlannerClient — readiness fails open, never reorders (R2)', () => {
  it('returns the same ordered set whether readiness is on or off', async () => {
    const off = await client.plan({ tuning: { ...frame, readinessOn: false } }, JOSH)
    const on = await client.plan({ tuning: { ...frame, readinessOn: true } }, JOSH)
    expect(on.cards.map((c) => c.id)).toEqual(off.cards.map((c) => c.id))
  })

  it('discloses the open (no-reading) state rather than faking a score', async () => {
    const on = await client.plan({ tuning: { ...frame, readinessOn: true } }, JOSH)
    expect(on.readiness.state).toBe('open')
    expect(on.readiness.staleReason).toMatch(/no fresh reading/i)
  })
})

describe('MockPlannerClient — Ruby gate disclosed (R6)', () => {
  it('exposes the set-aside option with a reason when Ruby is along', async () => {
    // big-day frame is where Old Rag enters the set, so Ruby visibly drops it.
    const feed = await client.plan({ tuning: { ...frame, effort: 'bigDay', party: 'ruby' } }, JOSH)
    const setAside = feed.setAside.find((s) => s.id === 'old-rag')
    expect(setAside).toBeDefined()
    expect(setAside?.kind).toBe('party')
    expect(setAside?.restorable).toBe(true)
  })
})

describe('MockPlannerClient — anonymous degrades honestly (R7)', () => {
  it('omits the personal fit line and shows no readiness', async () => {
    const feed = await client.plan({ tuning: frame }, ANON_SCOPE)
    expect(feed.readiness.on).toBe(false)
    for (const card of feed.cards) expect(card.enrichment?.fitLine).toBeUndefined()
  })
})

describe('MockPlannerClient — post-hike loop', () => {
  it('lists episodes for a viewer but none for anonymous (R7)', async () => {
    expect((await client.recentEpisodes(JOSH)).length).toBeGreaterThan(0)
    expect(await client.recentEpisodes(ANON_SCOPE)).toEqual([])
  })

  it('records an outcome idempotently (re-log updates, never duplicates)', async () => {
    const before = (await client.recentEpisodes(JOSH)).length
    await client.recordOutcome('ep-hawksbill', { overall: 3, skipped: false }, [], JOSH)
    const after = await client.recentEpisodes(JOSH)
    expect(after.length).toBe(before)
    expect(after.find((e) => e.id === 'ep-hawksbill')?.outcome?.overall).toBe(3)
  })

  it('throws for an unknown episode', async () => {
    await expect(
      client.recordOutcome('no-such-ep', { overall: 2, skipped: false }, [], JOSH),
    ).rejects.toThrow()
  })
})

describe('MockPlannerClient — search (Epic 038/B001, frontend half — mock parity)', () => {
  it('fuzzy/substring-matches a trail name, case-insensitively', async () => {
    const feed = await client.search('stony', JOSH)
    expect(feed.cards.length).toBeGreaterThan(0)
    expect(feed.cards.every((c) => c.name.toLowerCase().includes('stony'))).toBe(true)
  })

  it('returns an honest empty FeedVM for a query matching nothing — never fabricated', async () => {
    const feed = await client.search('zzz-no-such-trail-zzz', JOSH)
    expect(feed.cards).toEqual([])
    expect(feed.error).toBeUndefined()
  })

  it('caps results at k', async () => {
    // Every mock trail name contains a vowel; 'a' matches broadly enough to
    // exercise the cap without depending on the exact fixture count.
    const feed = await client.search('a', JOSH, 1)
    expect(feed.cards.length).toBeLessThanOrEqual(1)
  })

  it('marks results as mock provenance, same as plan()', async () => {
    const feed = await client.search('stony', JOSH)
    expect(feed.dataSource).toBe('mock')
  })
})

describe('MockPlannerClient — getCard resolves independent of the feed', () => {
  it('resolves a known id and returns null for an unknown one', async () => {
    expect(await client.getCard('stony-man', JOSH, frame)).not.toBeNull()
    expect(await client.getCard('no-such-trail', JOSH)).toBeNull()
  })

  it('includes drive only when a tuning frame is supplied (R7 cold deep-link)', async () => {
    const withOrigin = await client.getCard('stony-man', JOSH, frame)
    const without = await client.getCard('stony-man', ANON_SCOPE)
    expect(withOrigin?.enrichment?.driveMinutes).toBeGreaterThan(0)
    expect(without?.enrichment?.driveMinutes).toBeUndefined()
  })
})
