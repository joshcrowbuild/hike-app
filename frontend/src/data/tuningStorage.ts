/**
 * Device-local persistence for the tuning frame (craft review M4 — "tuning
 * amnesia"): the feed cache was already keyed by the tuning, but the tuning
 * itself was React state only, so every reload reset to the default and the
 * one dial the app has developed amnesia. Mirrors `savedTrails.ts` /
 * `feedCache.ts`'s storage posture: one namespaced `localStorage` slot, a
 * schema version, and corrupt/foreign/incompatible values degrading to a miss
 * (the built-in default) rather than throwing.
 *
 * Privacy posture: this is device-local UI state — the user's own chosen
 * dials, same class as the saved-trail ids (Rule #4 note in savedTrails.ts).
 * Nothing derived from the personal overlay is ever written here. The one
 * location-shaped field, `originCoords` (a live "Near me" device fix), is
 * deliberately NOT persisted: a stored fix is a stale location assertion
 * (source-or-silence applies to the user's position too) — on the next visit
 * the app falls back to the named origin and the user can re-request a fresh
 * fix with one tap.
 */
import type { EffortKey, PartyKey, TodayKey, TuningState, WhenKey } from '../types'

const STORAGE_KEY = 'adventure-planner:tuning'
/** Bump on ANY persisted-shape change — a stale reader must self-identify. */
const SCHEMA_VERSION = 1

const WHEN_KEYS: ReadonlySet<string> = new Set<WhenKey>([
  'tomorrowMorning',
  'weekendMorning',
  'weekendAfternoon',
  'fullDay',
])
const EFFORT_KEYS: ReadonlySet<string> = new Set<EffortKey>(['easy', 'moderate', 'bigDay'])
const PARTY_KEYS: ReadonlySet<string> = new Set<PartyKey>(['solo', 'ruby', 'friends'])
const TODAY_KEYS: ReadonlySet<string> = new Set<TodayKey>(['standard', 'seekShade', 'bigViews', 'quieter'])

interface TuningEnvelope {
  v: number
  tuning: TuningState
}

/**
 * Field-by-field validation, rebuilding the object rather than spreading
 * unknown JSON into app state: `origin` is an open key (config-driven catalog
 * — types.ts), so it only needs to be a non-empty string here; App.tsx
 * re-validates it against the loaded catalog and falls back if the region was
 * removed. The enum facets must be known values or the whole entry is a miss.
 */
function parseTuning(value: unknown): TuningState | null {
  if (!value || typeof value !== 'object') return null
  const t = value as Record<string, unknown>
  if (typeof t.origin !== 'string' || t.origin === '') return null
  if (typeof t.when !== 'string' || !WHEN_KEYS.has(t.when)) return null
  if (typeof t.effort !== 'string' || !EFFORT_KEYS.has(t.effort)) return null
  if (typeof t.party !== 'string' || !PARTY_KEYS.has(t.party)) return null
  if (typeof t.today !== 'string' || !TODAY_KEYS.has(t.today)) return null
  if (typeof t.readinessOn !== 'boolean') return null
  if (typeof t.prompt !== 'string') return null
  return {
    origin: t.origin,
    when: t.when as WhenKey,
    effort: t.effort as EffortKey,
    party: t.party as PartyKey,
    today: t.today as TodayKey,
    readinessOn: t.readinessOn,
    prompt: t.prompt,
  }
}

/** Drop-on-any-doubt read: null (the caller's built-in default) unless every
 *  guard passes — never a thrown error, never a partially-valid frame. */
export function readStoredTuning(): TuningState | null {
  if (typeof localStorage === 'undefined') return null
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
    return null
  }
  if (!entry || typeof entry !== 'object') return null
  const envelope = entry as Partial<TuningEnvelope>
  if (envelope.v !== SCHEMA_VERSION) return null
  return parseTuning(envelope.tuning)
}

export function writeStoredTuning(tuning: TuningState): void {
  if (typeof localStorage === 'undefined') return
  // Rebuild explicitly (no spread) so `originCoords` — and any future
  // transient field — can never ride along into storage by accident.
  const persisted: TuningState = {
    origin: tuning.origin,
    when: tuning.when,
    effort: tuning.effort,
    party: tuning.party,
    today: tuning.today,
    readinessOn: tuning.readinessOn,
    prompt: tuning.prompt,
  }
  const envelope: TuningEnvelope = { v: SCHEMA_VERSION, tuning: persisted }
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(envelope))
  } catch {
    // Quota/serialization failure — persistence is a convenience, never a
    // dependency (Rule #6 posture): the session keeps working from state.
  }
}

/** Test-only reset, mirrors `resetFeedCacheForTests`. App code never calls this. */
export function resetStoredTuningForTests(): void {
  if (typeof localStorage === 'undefined') return
  localStorage.removeItem(STORAGE_KEY)
}
