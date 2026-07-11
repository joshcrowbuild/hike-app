/**
 * The one decision point for whether the app serves sample (mock) data.
 *
 * Dev-gate (Phase B "kill dummy messaging"): a production build may NEVER
 * serve the sample store, regardless of how `VITE_USE_MOCK` is set — a
 * misconfigured deploy must fail toward the real backend, not toward sample
 * episodes posing as someone's hikes. In dev builds the flag keeps its
 * original meaning: mock by default, HTTP when `VITE_USE_MOCK=false`.
 *
 * Both consumers (PlannerProvider, regionsCatalog) call this with
 * `import.meta.env`, so the gate stays testable as a pure function.
 */
export interface MockGateEnv {
  PROD: boolean
  VITE_USE_MOCK?: string
}

export function shouldUseMock(env: MockGateEnv): boolean {
  if (env.PROD) return false
  return env.VITE_USE_MOCK !== 'false'
}

/**
 * The gate as a build-time constant. Written as a single expression over
 * `import.meta.env` literals (not a `shouldUseMock` call) so Vite's define
 * replacement turns it into `false` on a PROD build and Rollup then
 * dead-code-eliminates every mock-only branch — including the static
 * `MockPlannerClient` import and the whole sample store behind it.
 * `shouldUseMock` above is the same rule as a pure function for tests;
 * `useMock.test.ts` asserts the two agree.
 */
export const USE_MOCK: boolean = !import.meta.env.PROD && import.meta.env.VITE_USE_MOCK !== 'false'
