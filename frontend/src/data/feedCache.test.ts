import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ANON_SCOPE } from './api'
import type { ScopeContext } from './api'
import type { PlanInput } from './source'
import type { CardVM, FeedVM, WarningVM } from './vm'
import type { TuningState } from '../types'

const STORAGE_KEY = 'adventure-planner:feed-cache:anonymous'
const JOSH_STORAGE_KEY = 'adventure-planner:feed-cache:josh'

const TUNING: TuningState = {
  origin: 'frontRoyal',
  when: 'weekendMorning',
  effort: 'moderate',
  party: 'solo',
  today: 'standard',
  readinessOn: false,
  prompt: '',
}
const INPUT: PlanInput = { tuning: TUNING }

function feedWith(overrides: Partial<FeedVM> = {}): FeedVM {
  return {
    query: 'test',
    cards: [{ id: 'compton-peak', name: 'Compton Peak', distanceMi: 2.1, conditionLines: [], warnings: [] }],
    notices: [],
    setAside: [],
    heldBack: [],
    readiness: { on: false, state: 'off' },
    dataSource: 'live',
    ...overrides,
  }
}

beforeEach(() => {
  localStorage.clear()
  vi.resetModules()
  vi.unstubAllEnvs()
})

describe('feedKey (single source of truth, shared with useFeed effect dep)', () => {
  it('is stable for the same input/scope and differs on tuning, k, viewer, or grants', async () => {
    const { feedKey } = await import('./feedCache')
    const base = feedKey(INPUT, ANON_SCOPE)
    expect(feedKey(INPUT, ANON_SCOPE)).toBe(base)
    expect(feedKey({ tuning: { ...TUNING, party: 'friends' } }, ANON_SCOPE)).not.toBe(base)
    expect(feedKey({ ...INPUT, k: 5 }, ANON_SCOPE)).not.toBe(base)
    expect(feedKey(INPUT, { viewerId: 'josh', grantedIds: [] })).not.toBe(base)
    expect(feedKey(INPUT, { viewerId: 'anonymous', grantedIds: ['ruby'] })).not.toBe(base)
  })

  it('yields a distinct key when originCoords differs (a "near me" fix)', async () => {
    const { feedKey } = await import('./feedCache')
    const here: PlanInput = { tuning: { ...TUNING, originCoords: { lat: 38.9, lon: -78.2 } } }
    const there: PlanInput = { tuning: { ...TUNING, originCoords: { lat: 35.9, lon: -75.6 } } }
    expect(feedKey(here, ANON_SCOPE)).not.toBe(feedKey(INPUT, ANON_SCOPE))
    expect(feedKey(here, ANON_SCOPE)).not.toBe(feedKey(there, ANON_SCOPE))
  })
})

describe('readFeedCache / writeFeedCache (round trip, one slot per viewer, reset)', () => {
  it('returns null on an empty store', async () => {
    const { readFeedCache, feedKey } = await import('./feedCache')
    expect(readFeedCache(feedKey(INPUT, ANON_SCOPE), Date.now(), ANON_SCOPE.viewerId)).toBeNull()
  })

  it('round-trips a written feed under a matching key', async () => {
    const { readFeedCache, writeFeedCache, feedKey } = await import('./feedCache')
    const key = feedKey(INPUT, ANON_SCOPE)
    const feed = feedWith()
    writeFeedCache(key, feed, ANON_SCOPE.viewerId)
    const hit = readFeedCache(key, Date.now(), ANON_SCOPE.viewerId)
    expect(hit).not.toBeNull()
    expect(hit?.feed).toEqual(feed)
    expect(typeof hit?.savedAt).toBe('number')
  })

  it("a new write overwrites that viewer's slot rather than accumulating entries", async () => {
    const { readFeedCache, writeFeedCache, feedKey } = await import('./feedCache')
    const key1 = feedKey(INPUT, ANON_SCOPE)
    const key2 = feedKey({ tuning: { ...TUNING, party: 'friends' } }, ANON_SCOPE)
    writeFeedCache(key1, feedWith({ query: 'first' }), ANON_SCOPE.viewerId)
    writeFeedCache(key2, feedWith({ query: 'second' }), ANON_SCOPE.viewerId)
    // The first key's entry is gone — the new key's write overwrote the slot.
    expect(readFeedCache(key1, Date.now(), ANON_SCOPE.viewerId)).toBeNull()
    expect(readFeedCache(key2, Date.now(), ANON_SCOPE.viewerId)?.feed.query).toBe('second')
  })

  it('resetFeedCacheForTests clears the stored entry', async () => {
    const { readFeedCache, writeFeedCache, feedKey, resetFeedCacheForTests } = await import('./feedCache')
    const key = feedKey(INPUT, ANON_SCOPE)
    writeFeedCache(key, feedWith(), ANON_SCOPE.viewerId)
    resetFeedCacheForTests()
    expect(readFeedCache(key, Date.now(), ANON_SCOPE.viewerId)).toBeNull()
  })
})

describe('Epic 052 WP-5 — signed-in viewers are namespaced, not excluded', () => {
  it('a signed-in viewer round-trips through its OWN slot, physically separate from anonymous', async () => {
    const { readFeedCache, writeFeedCache, feedKey } = await import('./feedCache')
    const josh: ScopeContext = { viewerId: 'josh', grantedIds: [] }
    const joshKey = feedKey(INPUT, josh)
    writeFeedCache(joshKey, feedWith({ query: 'josh-feed' }), 'josh')

    expect(readFeedCache(joshKey, Date.now(), 'josh')?.feed.query).toBe('josh-feed')
    // The raw storage lands under the namespaced viewer key, not the old
    // single global slot.
    expect(localStorage.getItem(JOSH_STORAGE_KEY)).not.toBeNull()
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  it("one viewer's write never leaks into another viewer's read, even seeded under a colliding key", async () => {
    const { readFeedCache, writeFeedCache, feedKey } = await import('./feedCache')
    const josh: ScopeContext = { viewerId: 'josh', grantedIds: [] }
    // feedKey already differs by viewer (`v: scope.viewerId`), but assert the
    // storage-level isolation directly too — belt and suspenders against a
    // future feedKey change that stops encoding viewerId.
    writeFeedCache(feedKey(INPUT, ANON_SCOPE), feedWith({ query: 'anon-feed' }), 'anonymous')
    writeFeedCache(feedKey(INPUT, josh), feedWith({ query: 'josh-feed' }), 'josh')

    expect(readFeedCache(feedKey(INPUT, ANON_SCOPE), Date.now(), 'anonymous')?.feed.query).toBe('anon-feed')
    expect(readFeedCache(feedKey(INPUT, josh), Date.now(), 'josh')?.feed.query).toBe('josh-feed')
    // Reading josh's key against anonymous's slot (or vice versa) is a miss.
    expect(readFeedCache(feedKey(INPUT, josh), Date.now(), 'anonymous')).toBeNull()
    expect(readFeedCache(feedKey(INPUT, ANON_SCOPE), Date.now(), 'josh')).toBeNull()
  })

  it('resetFeedCacheForTests sweeps every namespaced viewer slot, not just one', async () => {
    const { readFeedCache, writeFeedCache, feedKey, resetFeedCacheForTests } = await import('./feedCache')
    const josh: ScopeContext = { viewerId: 'josh', grantedIds: [] }
    writeFeedCache(feedKey(INPUT, ANON_SCOPE), feedWith(), 'anonymous')
    writeFeedCache(feedKey(INPUT, josh), feedWith(), 'josh')

    resetFeedCacheForTests()

    expect(readFeedCache(feedKey(INPUT, ANON_SCOPE), Date.now(), 'anonymous')).toBeNull()
    expect(readFeedCache(feedKey(INPUT, josh), Date.now(), 'josh')).toBeNull()
  })
})

describe('evictFeedCache (Rule #5 — sign-out must not leave a readable feed behind)', () => {
  it("clears the named viewer's slot only, leaving other viewers' slots intact", async () => {
    const { readFeedCache, writeFeedCache, feedKey, evictFeedCache } = await import('./feedCache')
    const josh: ScopeContext = { viewerId: 'josh', grantedIds: [] }
    writeFeedCache(feedKey(INPUT, ANON_SCOPE), feedWith(), 'anonymous')
    writeFeedCache(feedKey(INPUT, josh), feedWith(), 'josh')

    evictFeedCache('josh')

    expect(readFeedCache(feedKey(INPUT, josh), Date.now(), 'josh')).toBeNull()
    expect(localStorage.getItem(JOSH_STORAGE_KEY)).toBeNull()
    // The anonymous slot survives — eviction is scoped to the one viewer.
    expect(readFeedCache(feedKey(INPUT, ANON_SCOPE), Date.now(), 'anonymous')?.feed).toBeDefined()
  })

  it('evicting a slot that was never written is a no-op, never throws', async () => {
    const { evictFeedCache } = await import('./feedCache')
    expect(() => evictFeedCache('never-signed-in')).not.toThrow()
  })
})

describe('AC-3.4 age cap / kill switch', () => {
  it('drops an entry older than MAX_STALE_MS (default 6h)', async () => {
    const { readFeedCache, writeFeedCache, feedKey } = await import('./feedCache')
    const key = feedKey(INPUT, ANON_SCOPE)
    writeFeedCache(key, feedWith(), ANON_SCOPE.viewerId)
    // Rewrite savedAt directly — writeFeedCache always stamps "now", so this
    // simulates a visit that happened at a known past instant.
    const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) as string)
    const savedAt = 1_000_000
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...raw, savedAt }))
    expect(readFeedCache(key, savedAt + 21_600_000, ANON_SCOPE.viewerId)).not.toBeNull()
    expect(readFeedCache(key, savedAt + 21_600_000 + 1, ANON_SCOPE.viewerId)).toBeNull()
  })

  it('VITE_ANON_FEED_STALE_MAX_MS=0 disables both read and write', async () => {
    vi.stubEnv('VITE_ANON_FEED_STALE_MAX_MS', '0')
    const { readFeedCache, writeFeedCache, feedKey } = await import('./feedCache')
    const key = feedKey(INPUT, ANON_SCOPE)
    writeFeedCache(key, feedWith(), ANON_SCOPE.viewerId)
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
    expect(readFeedCache(key, Date.now(), ANON_SCOPE.viewerId)).toBeNull()
  })

  it('an unset env value defaults to a 6h cap', async () => {
    const { readFeedCache, writeFeedCache, feedKey } = await import('./feedCache')
    const key = feedKey(INPUT, ANON_SCOPE)
    const now = Date.now()
    writeFeedCache(key, feedWith(), ANON_SCOPE.viewerId)
    expect(readFeedCache(key, now + 21_600_000 - 1, ANON_SCOPE.viewerId)).not.toBeNull()
    expect(readFeedCache(key, now + 21_600_000 + 60_000, ANON_SCOPE.viewerId)).toBeNull()
  })

  it('a blank env value counts as unset (6h cap), not the 0 kill switch', async () => {
    // Number('') === 0, so an empty-but-present env line must not disable the cache.
    vi.stubEnv('VITE_ANON_FEED_STALE_MAX_MS', '  ')
    const { readFeedCache, writeFeedCache, feedKey } = await import('./feedCache')
    const key = feedKey(INPUT, ANON_SCOPE)
    writeFeedCache(key, feedWith(), ANON_SCOPE.viewerId)
    expect(localStorage.getItem(STORAGE_KEY)).not.toBeNull()
    expect(readFeedCache(key, Date.now(), ANON_SCOPE.viewerId)).not.toBeNull()
  })
})

describe('AC-3.5 invalidation / degrade matrix (conservative drop-on-any-doubt)', () => {
  it('drops on a SCHEMA_VERSION mismatch', async () => {
    const { readFeedCache, writeFeedCache, feedKey } = await import('./feedCache')
    const key = feedKey(INPUT, ANON_SCOPE)
    writeFeedCache(key, feedWith(), ANON_SCOPE.viewerId)
    const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) as string)
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...raw, v: 999 }))
    expect(readFeedCache(key, Date.now(), ANON_SCOPE.viewerId)).toBeNull()
  })

  it('drops on a changed tuning (party)', async () => {
    const { readFeedCache, writeFeedCache, feedKey } = await import('./feedCache')
    writeFeedCache(feedKey(INPUT, ANON_SCOPE), feedWith(), ANON_SCOPE.viewerId)
    const changedKey = feedKey({ tuning: { ...TUNING, party: 'friends' } }, ANON_SCOPE)
    expect(readFeedCache(changedKey, Date.now(), ANON_SCOPE.viewerId)).toBeNull()
  })

  it('drops on a changed originCoords (a moved "near me" fix)', async () => {
    const { readFeedCache, writeFeedCache, feedKey } = await import('./feedCache')
    const here: PlanInput = { tuning: { ...TUNING, originCoords: { lat: 38.9, lon: -78.2 } } }
    writeFeedCache(feedKey(here, ANON_SCOPE), feedWith(), ANON_SCOPE.viewerId)
    const there: PlanInput = { tuning: { ...TUNING, originCoords: { lat: 35.9, lon: -75.6 } } }
    expect(readFeedCache(feedKey(there, ANON_SCOPE), Date.now(), ANON_SCOPE.viewerId)).toBeNull()
  })

  it('drops on a changed k', async () => {
    const { readFeedCache, writeFeedCache, feedKey } = await import('./feedCache')
    writeFeedCache(feedKey(INPUT, ANON_SCOPE), feedWith(), ANON_SCOPE.viewerId)
    expect(readFeedCache(feedKey({ ...INPUT, k: 5 }, ANON_SCOPE), Date.now(), ANON_SCOPE.viewerId)).toBeNull()
  })

  it('drops on a changed grants (same viewer slot, different key)', async () => {
    const { readFeedCache, writeFeedCache, feedKey } = await import('./feedCache')
    writeFeedCache(feedKey(INPUT, ANON_SCOPE), feedWith(), ANON_SCOPE.viewerId)
    const differentScope = { viewerId: 'anonymous', grantedIds: ['ruby'] }
    expect(readFeedCache(feedKey(INPUT, differentScope), Date.now(), 'anonymous')).toBeNull()
  })

  it('degrades to a miss on a corrupt non-JSON value', async () => {
    localStorage.setItem(STORAGE_KEY, 'not valid json')
    const { readFeedCache, feedKey } = await import('./feedCache')
    expect(readFeedCache(feedKey(INPUT, ANON_SCOPE), Date.now(), ANON_SCOPE.viewerId)).toBeNull()
  })

  it('degrades to a miss on a shape-invalid value (feed.cards not an array)', async () => {
    const { readFeedCache, feedKey } = await import('./feedCache')
    const key = feedKey(INPUT, ANON_SCOPE)
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ v: 1, key, savedAt: Date.now(), feed: { cards: 'nope' } }),
    )
    expect(readFeedCache(key, Date.now(), ANON_SCOPE.viewerId)).toBeNull()
  })

  it('a quota-throwing setItem is swallowed by writeFeedCache, never thrown', async () => {
    const { writeFeedCache, feedKey } = await import('./feedCache')
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('QuotaExceededError')
    })
    expect(() => writeFeedCache(feedKey(INPUT, ANON_SCOPE), feedWith(), ANON_SCOPE.viewerId)).not.toThrow()
    spy.mockRestore()
  })
})

describe('toStalePaint (AC-3.3 — honesty is the transform, not a banner)', () => {
  it('strips every live/ephemeral fact per card and at feed level, preserving structural fields + card count/order', async () => {
    const { toStalePaint } = await import('./feedCache')
    const warning: WarningVM = {
      text: 'flash flood warning',
      source: 'NWS',
      observedAgo: '2h ago',
      kind: 'weather',
      provenance: 'live',
    }
    const cardA: CardVM = {
      id: 'a',
      name: 'A',
      distanceMi: 2.1,
      conditionLines: [{ text: 'Clear', source: 'NWS', confidence: 'stated', provenance: 'live' }],
      warnings: [warning],
      enrichment: { conditionValue: 'Clear', provenance: 'live' },
      geo: { geometry: null, trailhead: { lat: 1, lon: 2 }, quality: 'confident', elevationProfile: null },
    }
    const cardB: CardVM = { id: 'b', name: 'B', distanceMi: 3, conditionLines: [], warnings: [] }
    const feed = feedWith({
      cards: [cardA, cardB],
      notices: ['Drive times unavailable this run'],
      setAside: [{ id: 'x', name: 'X', reason: 'party gate', kind: 'party', restorable: true }],
      heldBack: [{ id: 'y', name: 'Y', reasons: [{ text: 't', source: 's', kind: 'weather' }] }],
      readiness: { on: true, state: 'applied', rationale: 'because' },
    })

    const painted = toStalePaint(feed, '3h ago')

    expect(painted.cards.map((c) => c.id)).toEqual(['a', 'b']) // count/order preserved
    for (const card of painted.cards) {
      expect(card.warnings).toEqual([])
      expect(card.conditionLines).toEqual([])
      expect(card.enrichment).toBeUndefined()
      expect(card.conditionSilence).toEqual({ state: 'stale-degraded', detail: '3h ago' })
    }
    // Structural fields preserved.
    expect(painted.cards[0].name).toBe('A')
    expect(painted.cards[0].distanceMi).toBe(2.1)
    expect(painted.cards[0].geo).toEqual(cardA.geo)

    expect(painted.notices).toEqual([])
    expect(painted.setAside).toEqual([])
    expect(painted.heldBack).toEqual([])
    expect(painted.readiness).toEqual({ on: false, state: 'off' })
    expect(painted.query).toBe(feed.query)
    expect(painted.dataSource).toBe('live')
  })

  it('strips the per-kind conditions — a frozen checked-clear must never repaint as current (Epic 018 S4f)', async () => {
    const { toStalePaint } = await import('./feedCache')
    const card: CardVM = {
      id: 'a',
      name: 'A',
      distanceMi: 2.1,
      conditionLines: [],
      warnings: [],
      // A cached "checked — nothing to flag · 20m ago" on a safety kind: hours
      // later this would be a false-fresh sourced all-clear (its checkedAgo is
      // a pre-humanised string no reader can re-age), and the screens give
      // `conditions` precedence over the injected silence below.
      conditions: [{ kind: 'fire', state: 'no-hazard', source: 'NASA FIRMS', checkedAgo: '20m ago' }],
    }
    const painted = toStalePaint(feedWith({ cards: [card] }), '5h ago')
    expect(painted.cards[0].conditions).toBeUndefined()
    expect(painted.cards[0].conditionSilence).toEqual({ state: 'stale-degraded', detail: '5h ago' })
  })
})

describe('staleAgeLabel (honest — derived from the real fetch timestamp)', () => {
  it('reuses relativeAge on the stored savedAt', async () => {
    const { staleAgeLabel } = await import('./feedCache')
    const savedAt = Date.now() - 2 * 60 * 60 * 1000
    expect(staleAgeLabel(savedAt)).toBe('2h ago')
  })
})
