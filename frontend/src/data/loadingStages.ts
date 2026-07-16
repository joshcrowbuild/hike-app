/**
 * The honest progress ladder for any long wait (D4 — perceived performance).
 * One copy of the staging thresholds and the copy itself, shared by BOTH long
 * waits the app has: `useFeed`'s /plan request (Home's skeleton state) and the
 * boot gate while /regions loads (BootShell). Before this module existed the
 * ladder lived inside Home, which the provider gate blocked from rendering —
 * so the best loading copy in the app was unreachable during the only wait
 * long enough to need it (craft review H1).
 *
 * Never a frozen line past NNG's ~10s attention threshold: the copy keeps
 * changing as the wait stretches, without pretending to know a cause it can't
 * confirm until the wait is long enough to make one likely.
 *
 * Re-tuned down for the paid Starter (Epic 052 WP-5 / design-system-v0.2 D4):
 * Render no longer spins down on idle, so a genuine multi-minute cold wake is
 * no longer the expected shape of a slow request — a warm `/plan` typically
 * resolves in ~1s (Epic 039/040's latency work). `reassure` now covers an
 * ordinary-but-slow live provider fan-out; `coldstart` still exists as a
 * belt-and-suspenders line for the rare case that IS genuinely slow (a
 * just-deployed instance mid-restart, or a real upstream outage across
 * several probes) — its copy stays honest ("this can take up to a minute")
 * rather than claiming to know the cause, since the real cause is no longer
 * reliably "waking a free-tier dyno." Both thresholds stay comfortably inside
 * the 60s `/plan` abort budget (`PLAN_TIMEOUT_MS`, httpPlanner.ts).
 */
import { useEffect, useState } from 'react'

export type LoadingStage = 'initial' | 'reassure' | 'coldstart'

export const REASSURE_MS = 5_000
export const COLDSTART_MS = 15_000

export const LOADING_COPY: Record<LoadingStage, string> = {
  initial: 'Reading conditions…',
  reassure: 'Still checking conditions…',
  coldstart: 'Waking the server — this can take up to a minute…',
}

/**
 * Elapsed-time ladder for a surface that exists only while its wait does
 * (BootShell mounts when the gate blocks and unmounts when it clears), so the
 * clock is simply time-since-mount — driven by elapsed time, not by which
 * fetch is pending (review H1's fix shape). `useFeed` keeps its own inline
 * timers because its wait outlives the component state around it (re-keys on
 * retune); both read the same thresholds above.
 */
export function useLoadingStage(): LoadingStage {
  const [stage, setStage] = useState<LoadingStage>('initial')
  useEffect(() => {
    const reassure = setTimeout(() => setStage('reassure'), REASSURE_MS)
    const coldstart = setTimeout(() => setStage('coldstart'), COLDSTART_MS)
    return () => {
      clearTimeout(reassure)
      clearTimeout(coldstart)
    }
  }, [])
  return stage
}
