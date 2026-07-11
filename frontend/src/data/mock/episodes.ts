/**
 * Sample episodes for the post-hike loop. These are explicitly SAMPLE data
 * about a sample subject — the outcome card discloses this and never poses them
 * as the user's real watch readings (R11). A tiny in-memory store lets
 * recordOutcome behave idempotently within a session (re-logging updates, never
 * duplicates), mirroring the real endpoint's contract.
 */
import type { EpisodeVM } from '../vm'

// Dev-gate (Phase B): the sample subjects below exist ONLY in dev builds. On a
// production build (`import.meta.env.PROD` is statically true) Vite replaces the
// ternary and dead-code-eliminates the sample literals from the bundle entirely,
// so Hawksbill/Stony Man can structurally never render as someone's real hikes —
// even if the data seam were misconfigured to reach this store.
const seed: EpisodeVM[] = import.meta.env.PROD
  ? []
  : [
      {
        id: 'ep-hawksbill',
        trailName: 'Hawksbill Summit',
        when: 'Saturday',
        distanceMiles: 2.9,
        ascentFeet: 860,
        movingTime: '2h 05m moving',
        paceNote: 'Steady pace the whole climb',
        companions: [{ kind: 'dependent', name: 'Ruby' }],
        provenance: 'sample',
      },
      {
        id: 'ep-stony',
        trailName: 'Stony Man Loop',
        when: 'Last weekend',
        distanceMiles: 3.7,
        ascentFeet: 1050,
        movingTime: '2h 20m moving',
        companions: [],
        outcome: { overall: 3, skipped: false },
        provenance: 'sample',
      },
    ]

const store = new Map<string, EpisodeVM>(seed.map((e) => [e.id, { ...e }]))

export function listEpisodes(): EpisodeVM[] {
  return Array.from(store.values()).map((e) => ({ ...e }))
}

export function findEpisode(id: string): EpisodeVM | null {
  const e = store.get(id)
  return e ? { ...e } : null
}

/** Idempotent: re-logging an episode updates its outcome rather than adding one. */
export function setOutcome(
  id: string,
  outcome: { overall: 1 | 2 | 3 | null; skipped: boolean },
  companions: EpisodeVM['companions'],
): EpisodeVM | null {
  const e = store.get(id)
  if (!e) return null
  const next: EpisodeVM = { ...e, outcome, companions }
  store.set(id, next)
  return { ...next }
}
