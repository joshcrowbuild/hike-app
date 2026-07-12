/**
 * Client-side stale-while-revalidate cache for the anonymous Home feed (Epic
 * 039 S3). Mirrors `savedTrails.ts`'s storage/degrade posture: a single
 * namespaced `localStorage` slot, corrupt/foreign values degrade to a miss
 * rather than throwing. A cache of a DERIVED feed — same Rule-#3/#6 posture
 * as `savedTrails.ts` and the probe TTLCache: never a graph write/node.
 *
 * Honesty is the TRANSFORM, not a disclosed-around banner (Rule #1): the
 * envelope stores the TRUE fresh feed (warnings included) — neutralisation
 * happens only on read, via `toStalePaint`, so the cap and the honesty
 * presentation stay separate concerns from the write path.
 */
import { relativeAge } from './age'
import type { ScopeContext } from './api'
import type { PlanInput } from './source'
import type { FeedVM } from './vm'

const STORAGE_KEY = 'adventure-planner:anon-feed-cache'
/** Bump on ANY FeedVM shape change — there is no build-hash to detect drift
 *  another way, so a stale reader must self-identify via this number. */
const SCHEMA_VERSION = 2 // v2: CardVM grew per-kind `conditions` (Epic 018 S4f)

/**
 * Age cap / kill switch, build-time baked (Vite), like `VITE_USE_MOCK` — a
 * changed value needs a rebuild. `0` disables both read and write (S2's
 * 0-disables convention).
 *
 * This is NOT the safety mechanism — `toStalePaint` is (it strips every
 * live/ephemeral fact on read, so the cap can't be defeated by extending it).
 * The cap instead bounds RELEVANCE: it exists to catch a same-day return
 * visit, not to bound hazard staleness, so 6h is defensible on that basis
 * alone.
 */
const MAX_STALE_MS = ((): number => {
  const raw = import.meta.env.VITE_ANON_FEED_STALE_MAX_MS
  // Blank counts as unset: Number('') is 0, so an empty-but-present env line
  // would otherwise silently engage the 0-disables kill switch.
  if (raw === undefined || raw.trim() === '') return 21_600_000 // 6h default
  const parsed = Number(raw)
  return Number.isFinite(parsed) ? parsed : 21_600_000
})()

interface FeedCacheEnvelope {
  v: number
  key: string
  savedAt: number
  feed: FeedVM
}

/**
 * The single source of truth for the cache key, shared with `useFeed`'s
 * effect dependency so the cache key and the fetch-triggering key can never
 * diverge — if they did, a cached feed could repaint under the wrong frame.
 * `input.tuning` already carries `originCoords`, so a "near me" fix yields a
 * distinct key and never repaints for a different geolocation.
 */
export function feedKey(input: PlanInput, scope: ScopeContext): string {
  return JSON.stringify({ t: input.tuning, k: input.k, v: scope.viewerId, g: scope.grantedIds })
}

function isEnvelope(value: unknown): value is FeedCacheEnvelope {
  if (!value || typeof value !== 'object') return false
  const v = value as Record<string, unknown>
  if (typeof v.v !== 'number' || typeof v.key !== 'string' || typeof v.savedAt !== 'number') return false
  const feed = v.feed as FeedVM | undefined
  return !!feed && typeof feed === 'object' && Array.isArray(feed.cards)
}

/**
 * Conservative drop-on-any-doubt read: returns non-null only when EVERY guard
 * passes (kill switch, parse, schema version, exact key match, age cap, shape
 * sanity) — any failure degrades silently to a cache miss (the normal
 * skeleton load), never a thrown error or a stale/incompatible paint.
 *
 * The anonymous-only gate lives at the CALLER (`useFeed`), not here — this is
 * a pure key match so it stays trivially testable on its own.
 */
export function readFeedCache(key: string, nowMs: number): { feed: FeedVM; savedAt: number } | null {
  if (typeof localStorage === 'undefined') return null
  if (MAX_STALE_MS <= 0) return null
  let raw: string | null
  try {
    raw = localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
  if (!raw) return null
  let entry: unknown
  try {
    entry = JSON.parse(raw)
  } catch {
    // Corrupt/foreign value under our key — degrade to a miss.
    return null
  }
  if (!isEnvelope(entry)) return null
  if (entry.v !== SCHEMA_VERSION) return null
  if (entry.key !== key) return null
  if (nowMs - entry.savedAt > MAX_STALE_MS) return null
  return { feed: entry.feed, savedAt: entry.savedAt }
}

/**
 * Persists the TRUE fresh feed (warnings, notices, everything). The caller
 * (`useFeed`) invokes this only for an anonymous viewer, and only on a
 * successful, non-empty, non-error resolve — a stale "nothing holds" or a
 * stale error is never useful to repaint, so neither is ever written.
 */
export function writeFeedCache(key: string, feed: FeedVM): void {
  if (typeof localStorage === 'undefined') return
  if (MAX_STALE_MS <= 0) return
  const envelope: FeedCacheEnvelope = { v: SCHEMA_VERSION, key, savedAt: Date.now(), feed }
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(envelope))
  } catch {
    // Quota/serialization failure — the cache is a perceived-perf enrichment,
    // never a dependency (Rule #6); a failed write just means the next visit
    // gets the ordinary skeleton load instead of a stale paint.
  }
}

/**
 * Pure, on-read neutraliser — the honesty mechanism itself, not a disclosure
 * layered on top (Rule #1). Strips every live/ephemeral assertion so a
 * repainted card can never wear a frozen hazard or a frozen per-fact age:
 * `relativeAge` buckets to min/hour/day and the wire drops raw `observed_at`,
 * so a repainted age would be unfixable, and a since-cleared hazard would
 * otherwise render as a current-looking warning. Every card instead carries
 * the disclosed `stale-degraded` silence, dated with the one honest age this
 * module knows: `staleAsOf`, derived from the real fetch timestamp.
 *
 * Keeps slow/structural fields (id/name/distanceMi/geo) — legitimately
 * Rule-#3 graph-class data, safe to repaint. Card count/order is preserved so
 * the fresh feed can swap in without a layout jump.
 */
export function toStalePaint(feed: FeedVM, staleAsOf: string): FeedVM {
  return {
    ...feed,
    cards: feed.cards.map((card) => ({
      ...card,
      conditionLines: [],
      warnings: [],
      enrichment: undefined,
      // The per-kind dispositions are live/ephemeral assertions too: a frozen
      // "checked — nothing to flag · 20m ago" repainted hours later would be a
      // false-fresh all-clear on a safety kind (Rule #1), and its `checkedAgo`
      // is a pre-humanised string this module cannot re-age. Stripped, so the
      // injected stale-degraded silence below is what actually renders (the
      // screens give `conditions` precedence whenever it is present).
      conditions: undefined,
      conditionSilence: { state: 'stale-degraded', detail: staleAsOf },
    })),
    notices: [],
    setAside: [],
    heldBack: [],
    readiness: { on: false, state: 'off' },
  }
}

/** Honest because `savedAt` is a real fetch timestamp — never the dropped
 *  per-fact `observed_at` — reusing the existing relative-age humaniser. */
export function staleAgeLabel(savedAt: number, nowMs: number = Date.now()): string {
  return relativeAge(new Date(savedAt).toISOString(), nowMs)
}

/**
 * Test-only reset, mirrors `resetSavedTrailsForTests` (savedTrails.ts). App
 * code never calls this.
 */
export function resetFeedCacheForTests(): void {
  if (typeof localStorage === 'undefined') return
  localStorage.removeItem(STORAGE_KEY)
}
