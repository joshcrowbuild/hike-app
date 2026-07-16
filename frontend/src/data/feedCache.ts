/**
 * Client-side stale-while-revalidate cache for the Home feed (Epic 039 S3;
 * extended to signed-in viewers by Epic 052 WP-5 / design-system-v0.2 Part
 * III.2). Mirrors `savedTrails.ts`'s storage/degrade posture: a namespaced
 * `localStorage` slot PER VIEWER, corrupt/foreign values degrade to a miss
 * rather than throwing. A cache of a DERIVED feed — same Rule-#3/#6 posture
 * as `savedTrails.ts` and the probe TTLCache: never a graph write/node.
 *
 * Honesty is the TRANSFORM, not a disclosed-around banner (Rule #1): the
 * envelope stores the TRUE fresh feed (warnings included) — neutralisation
 * happens only on read, via `toStalePaint`, so the cap and the honesty
 * presentation stay separate concerns from the write path.
 *
 * Privacy (Rule #5, private-by-default): a signed-in viewer's feed is
 * personal, so each viewer gets its OWN physically separate `localStorage`
 * slot (`storageKeyFor`) rather than sharing one global slot — two viewers on
 * the same device can never evict or read each other's cached feed. The
 * caller (`AuthProvider`'s `signOut`) evicts the signed-out viewer's slot via
 * `evictFeedCache`; nothing here ever persists a GRANTED viewer's raw
 * substrate — only the resolved caller's own derived `FeedVM` ever reaches
 * `writeFeedCache`, and it lands in that caller's own slot alone.
 */
import { relativeAge } from './age'
import type { ScopeContext } from './api'
import type { PlanInput } from './source'
import type { FeedVM } from './vm'

const STORAGE_PREFIX = 'adventure-planner:feed-cache:'

/** Every viewer's slot is physically separate (Rule #5) — `viewerId` is
 *  already constrained to `[A-Za-z0-9_:-]{1,64}` server-side
 *  (`VIEWER_ID_PATTERN`), so it's safe to interpolate directly with no
 *  delimiter collision against the fixed prefix. */
function storageKeyFor(viewerId: string): string {
  return `${STORAGE_PREFIX}${viewerId}`
}

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
 * Reads ANY viewer's slot (Epic 052 WP-5 — signed-in viewers used to be
 * excluded by an anonymous-only gate at the caller; that gate is gone, and
 * `viewerId` alone now selects which physically separate slot is read, so a
 * viewer can never read another viewer's cached feed even on a `key` clash).
 * `viewerId` defaults to `'anonymous'` — the slot every pre-WP-5 caller
 * implicitly meant — so an un-migrated call site behaves exactly as before.
 */
export function readFeedCache(
  key: string,
  nowMs: number,
  viewerId: string = 'anonymous',
): { feed: FeedVM; savedAt: number } | null {
  if (typeof localStorage === 'undefined') return null
  if (MAX_STALE_MS <= 0) return null
  let raw: string | null
  try {
    raw = localStorage.getItem(storageKeyFor(viewerId))
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
 * Persists the TRUE fresh feed (warnings, notices, everything) into THIS
 * viewer's own slot. The caller (`useFeed`) invokes this for any viewer
 * (Epic 052 WP-5 — previously anonymous-only), and only on a successful,
 * non-empty, non-error, phase-2-complete resolve — a stale "nothing holds" or
 * a stale error is never useful to repaint, so neither is ever written.
 *
 * Privacy (Rule #5): the feed is already the viewer's own DERIVED
 * recommendation (never a granted party's raw substrate — the API never
 * returns that), and it lands only in `viewerId`'s own slot, on `viewerId`'s
 * own device — never a shared or cross-viewer location. Defaults to
 * `'anonymous'` for the same un-migrated-caller reason as `readFeedCache`.
 */
export function writeFeedCache(key: string, feed: FeedVM, viewerId: string = 'anonymous'): void {
  if (typeof localStorage === 'undefined') return
  if (MAX_STALE_MS <= 0) return
  const envelope: FeedCacheEnvelope = { v: SCHEMA_VERSION, key, savedAt: Date.now(), feed }
  try {
    localStorage.setItem(storageKeyFor(viewerId), JSON.stringify(envelope))
  } catch {
    // Quota/serialization failure — the cache is a perceived-perf enrichment,
    // never a dependency (Rule #6); a failed write just means the next visit
    // gets the ordinary skeleton load instead of a stale paint.
  }
}

/**
 * Evicts one viewer's cached feed — called on sign-out (`AuthProvider`) so a
 * signed-out viewer's derived feed never lingers, readable, in `localStorage`
 * for whoever uses the device/browser next (Rule #5: private-by-default).
 * Never throws: a quota/storage failure here just means the stale slot
 * outlives the session, degrading to the normal cold-start ladder next visit
 * rather than blocking sign-out.
 */
export function evictFeedCache(viewerId: string): void {
  if (typeof localStorage === 'undefined') return
  try {
    localStorage.removeItem(storageKeyFor(viewerId))
  } catch {
    // Best-effort — see docstring.
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
 * code never calls this. Clears EVERY viewer's slot (there's no registry of
 * which viewers a test touched), so it sweeps every `localStorage` key under
 * `STORAGE_PREFIX` rather than just one — the namespaced-by-viewer analogue
 * of the old single-slot `removeItem`.
 */
export function resetFeedCacheForTests(): void {
  if (typeof localStorage === 'undefined') return
  const toRemove: string[] = []
  for (let i = 0; i < localStorage.length; i++) {
    const k = localStorage.key(i)
    if (k && k.startsWith(STORAGE_PREFIX)) toRemove.push(k)
  }
  for (const k of toRemove) localStorage.removeItem(k)
}
