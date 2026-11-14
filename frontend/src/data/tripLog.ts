/**
 * Manual trip log (Epic 042) — the client half of "I did this".
 *
 * Two jobs, both deliberately small:
 *
 * 1. `manualClientEpisodeId` derives the `client_episode_id` the backend dedupes on.
 *    It is a pure function of trail + local calendar day, so a re-submit — a double
 *    tap, a retry after a dropped response, a second device — addresses the SAME
 *    server Episode (`ep:{sub}:{client_episode_id}` is an idempotent MERGE) and can
 *    never create a second one. That is the real idempotency guarantee.
 *
 * 2. A device-local record of what this viewer logged, keyed by viewer. The server has
 *    no episode read yet (the live adapter's `recentEpisodes`/`getEpisode` are empty),
 *    so this record is what lets the Detail action read "Logged today" after a reload,
 *    and what lets the Outcome screen resolve a manual Episode's trail name. It stores
 *    only what the user themselves entered (trail, day) — no measured value is ever
 *    invented here (Rule #6 / source-or-silence). Losing it (cleared site data, a new
 *    device) is safe: the button simply offers the action again and the deterministic
 *    id makes a repeat a no-op server-side.
 *
 * Like `savedTrails`, a module-level store behind `useSyncExternalStore`, so every
 * mounted Detail sees a log the instant it lands, without a provider.
 */
import { useSyncExternalStore } from 'react'

const STORAGE_KEY = 'adventure-planner:trip-logs'

export interface TripLogEntry {
  viewerId: string
  episodeId: string
  trailId: string
  trailName: string
  /** Local calendar day, `YYYY-MM-DD`. */
  day: string
}

/** The viewer's LOCAL calendar day as `YYYY-MM-DD` — "today" is the user's day, not UTC's. */
export function localDayKey(now: Date = new Date()): string {
  const y = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  const d = String(now.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

// cyrb53: a small, well-distributed 53-bit string hash. Not cryptographic — it only
// has to keep two different trail ids from sharing a client id on the same day.
function hash53(input: string): string {
  let h1 = 0xdeadbeef
  let h2 = 0x41c6ce57
  for (let i = 0; i < input.length; i++) {
    const ch = input.charCodeAt(i)
    h1 = Math.imul(h1 ^ ch, 2654435761)
    h2 = Math.imul(h2 ^ ch, 1597334677)
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909)
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909)
  const n = 4294967296 * (2097151 & h2) + (h1 >>> 0)
  return n.toString(36)
}

/**
 * The deterministic `client_episode_id` for logging `trailId` on `day`. Matches the
 * backend's `^[A-Za-z0-9_-]{1,64}$` (trail ids may hold characters it rejects, so the
 * id is hashed rather than embedded) and is at most ~30 characters.
 */
export function manualClientEpisodeId(trailId: string, day: string): string {
  return `manual-${day.replace(/-/g, '')}-${hash53(trailId)}`
}

function isEntry(v: unknown): v is TripLogEntry {
  if (typeof v !== 'object' || v === null) return false
  const e = v as Record<string, unknown>
  return (
    typeof e.viewerId === 'string' &&
    typeof e.episodeId === 'string' &&
    typeof e.trailId === 'string' &&
    typeof e.trailName === 'string' &&
    typeof e.day === 'string'
  )
}

function readStorage(): TripLogEntry[] {
  if (typeof localStorage === 'undefined') return []
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.filter(isEntry) : []
  } catch {
    // Corrupt/foreign value, or storage blocked — degrade to "nothing logged here".
    return []
  }
}

let entries: TripLogEntry[] = readStorage()
const listeners = new Set<() => void>()

function writeStorage(): void {
  try {
    if (typeof localStorage !== 'undefined') localStorage.setItem(STORAGE_KEY, JSON.stringify(entries))
  } catch {
    // Storage full/blocked: the in-memory record still serves this session.
  }
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function snapshot(): TripLogEntry[] {
  return entries
}

/** Remember a log. Idempotent on (viewer, episode): re-recording replaces, never duplicates. */
export function rememberTripLog(entry: TripLogEntry): void {
  entries = [
    ...entries.filter((e) => !(e.viewerId === entry.viewerId && e.episodeId === entry.episodeId)),
    entry,
  ]
  writeStorage()
  for (const listener of listeners) listener()
}

export function findTripLog(viewerId: string, episodeId: string): TripLogEntry | null {
  return entries.find((e) => e.viewerId === viewerId && e.episodeId === episodeId) ?? null
}

export function isTripLoggedOn(viewerId: string, trailId: string, day: string): boolean {
  return entries.some((e) => e.viewerId === viewerId && e.trailId === trailId && e.day === day)
}

/** Reactive "has this viewer logged this trail today?" — today = the local day at render. */
export function useTripLoggedToday(viewerId: string, trailId: string): boolean {
  const all = useSyncExternalStore(subscribe, snapshot, () => [])
  const day = localDayKey()
  return all.some((e) => e.viewerId === viewerId && e.trailId === trailId && e.day === day)
}

/** Test-only reset (module-level singleton store, like `resetSavedTrailsForTests`). */
export function resetTripLogsForTests(): void {
  entries = []
  writeStorage()
  for (const listener of listeners) listener()
}
