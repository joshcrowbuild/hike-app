/**
 * Client-side "saved trails" list — anonymous-friendly bookmarking with no
 * backend or auth (S6-ish follow-on to the directions deep-link). Only the
 * trail id is persisted: the source of truth for a trail's data is always the
 * live/mock feed, never a copy frozen in `localStorage` at save-time (mirrors
 * source-or-silence — we never resurrect a stale name/condition from storage).
 *
 * A module-level store + `useSyncExternalStore` keeps every mounted card, the
 * Detail screen, and the Home "Saved" filter in sync the instant one of them
 * toggles a trail — without a provider, since this is deliberately outside the
 * PlannerProvider's viewer-scoped data seam (Rule #4: this is client-local
 * preference, not graph data).
 */
import { useSyncExternalStore } from 'react'

const STORAGE_KEY = 'adventure-planner:saved-trail-ids'

function readStorage(): Set<string> {
  if (typeof localStorage === 'undefined') return new Set()
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return new Set()
    const parsed: unknown = JSON.parse(raw)
    return Array.isArray(parsed) ? new Set(parsed.filter((v): v is string => typeof v === 'string')) : new Set()
  } catch {
    // Corrupt/foreign value under our key — degrade to "nothing saved" rather
    // than throwing and taking the whole feed down with it.
    return new Set()
  }
}

let savedIds = readStorage()
const listeners = new Set<() => void>()

function writeStorage(): void {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem(STORAGE_KEY, JSON.stringify([...savedIds]))
}

function notify(): void {
  for (const listener of listeners) listener()
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function snapshot(): Set<string> {
  return savedIds
}

export function isTrailSaved(id: string): boolean {
  return savedIds.has(id)
}

export function setTrailSaved(id: string, saved: boolean): void {
  if (saved === savedIds.has(id)) return
  const next = new Set(savedIds)
  if (saved) next.add(id)
  else next.delete(id)
  savedIds = next
  writeStorage()
  notify()
}

export function toggleTrailSaved(id: string): void {
  setTrailSaved(id, !savedIds.has(id))
}

/** The live saved-id set, reactive across every component that reads it. */
export function useSavedTrailIds(): Set<string> {
  return useSyncExternalStore(subscribe, snapshot, () => new Set<string>())
}

export function useIsTrailSaved(id: string): boolean {
  return useSavedTrailIds().has(id)
}

/**
 * Test-only reset of the in-memory + persisted saved set. The module keeps a
 * singleton store (by design — every mounted Save button and the Home filter
 * must see the same state without a provider), so tests that toggle a save
 * need an explicit way back to empty between cases; app code never calls this.
 */
export function resetSavedTrailsForTests(): void {
  savedIds = new Set()
  writeStorage()
  notify()
}
