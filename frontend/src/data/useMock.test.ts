/**
 * Dev-gate for the sample store (Phase B "kill dummy messaging"): sample
 * episodes must be structurally unreachable on a production build, and
 * unreachable through the data seam whenever `VITE_USE_MOCK=false`.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import { shouldUseMock } from './useMock'

describe('shouldUseMock (the one mock/HTTP decision point)', () => {
  it('never serves mock on a production build, whatever VITE_USE_MOCK says', () => {
    expect(shouldUseMock({ PROD: true, VITE_USE_MOCK: 'false' })).toBe(false)
    expect(shouldUseMock({ PROD: true, VITE_USE_MOCK: 'true' })).toBe(false)
    expect(shouldUseMock({ PROD: true, VITE_USE_MOCK: undefined })).toBe(false)
  })

  it('VITE_USE_MOCK=false selects HTTP in dev builds too', () => {
    expect(shouldUseMock({ PROD: false, VITE_USE_MOCK: 'false' })).toBe(false)
  })

  it('dev builds default to mock when the flag is unset or true', () => {
    expect(shouldUseMock({ PROD: false, VITE_USE_MOCK: undefined })).toBe(true)
    expect(shouldUseMock({ PROD: false, VITE_USE_MOCK: 'true' })).toBe(true)
  })
})

describe('sample episode store is empty on a production build', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
  })

  it('a PROD build yields zero sample episodes (Hawksbill/Stony Man gone)', async () => {
    vi.stubEnv('PROD', true)
    vi.resetModules()
    const episodes = await import('./mock/episodes')
    expect(episodes.listEpisodes()).toEqual([])
    expect(episodes.findEpisode('ep-hawksbill')).toBeNull()
    expect(episodes.findEpisode('ep-stony')).toBeNull()
  })

  it('a PROD build yields zero sample trails from the mock engine', async () => {
    vi.stubEnv('PROD', true)
    vi.resetModules()
    const engine = await import('./mock/engine')
    expect(engine.trails).toEqual([])
  })

  it('a dev build keeps the disclosed sample subjects for the post-hike loop', async () => {
    vi.stubEnv('PROD', false)
    vi.resetModules()
    const episodes = await import('./mock/episodes')
    const names = episodes.listEpisodes().map((e) => e.trailName)
    expect(names).toContain('Hawksbill Summit')
    expect(names).toContain('Stony Man Loop')
  })
})

describe('the data seam with the deployed config (VITE_USE_MOCK=false)', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
  })

  it('resolves the HTTP client, so sample data is unreachable through the seam', async () => {
    vi.stubEnv('VITE_USE_MOCK', 'false')
    vi.resetModules()
    // The provider captures the decision at module load, so import fresh.
    const { shouldUseMock: fresh } = await import('./useMock')
    expect(fresh(import.meta.env)).toBe(false)
  })
})
