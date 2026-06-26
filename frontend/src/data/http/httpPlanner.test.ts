import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { HttpPlannerClient } from './httpPlanner'
import { ANON_SCOPE, type ScopeContext, type FeedResponse, type OutcomeResponse } from '../api'
import type { PlanInput } from '../source'
import type { TuningState } from '../../types'

const JOSH: ScopeContext = { viewerId: 'josh', grantedIds: [] }

const TUNING: TuningState = {
  origin: 'frontRoyal',
  when: 'weekendMorning',
  effort: 'moderate',
  party: 'solo',
  today: 'standard',
  readinessOn: false,
  prompt: '',
}
const PLAN_INPUT: PlanInput = { tuning: TUNING }

const FEED: FeedResponse = { query: '', cards: [], card_count: 0, notices: [] }
const OUTCOME: OutcomeResponse = { outcome_id: 'o1', episode_id: 'e1', skipped: false, overall: 2 }

function headersOf(call: unknown): Record<string, string> {
  const init = (call as [string, RequestInit])[1]
  return init.headers as Record<string, string>
}

describe('HttpPlannerClient auth headers', () => {
  const SECRET = 'dev-secret-value'
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.stubEnv('VITE_DEV_VIEWER_SECRET', SECRET)
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
  })

  function ok(json: unknown) {
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(json) } as Response)
  }

  it('sends the dev-viewer secret on /plan for a non-anonymous viewer', async () => {
    fetchMock.mockReturnValue(ok(FEED))
    await new HttpPlannerClient('http://api').plan(PLAN_INPUT, JOSH)
    expect(headersOf(fetchMock.mock.calls[0])['X-Dev-Viewer-Secret']).toBe(SECRET)
  })

  it('omits the secret on /plan for an anonymous viewer', async () => {
    fetchMock.mockReturnValue(ok(FEED))
    await new HttpPlannerClient('http://api').plan(PLAN_INPUT, ANON_SCOPE)
    expect(headersOf(fetchMock.mock.calls[0])).not.toHaveProperty('X-Dev-Viewer-Secret')
  })

  it('sends the dev-viewer secret on /outcome for a non-anonymous viewer', async () => {
    fetchMock.mockReturnValue(ok(OUTCOME))
    await new HttpPlannerClient('http://api').recordOutcome(
      'e1',
      { overall: 2, skipped: false },
      [],
      JOSH,
    )
    expect(headersOf(fetchMock.mock.calls[0])['X-Dev-Viewer-Secret']).toBe(SECRET)
  })

  it('omits the secret on /outcome for an anonymous viewer', async () => {
    fetchMock.mockReturnValue(ok(OUTCOME))
    await new HttpPlannerClient('http://api').recordOutcome(
      'e1',
      { overall: 2, skipped: false },
      [],
      ANON_SCOPE,
    )
    expect(headersOf(fetchMock.mock.calls[0])).not.toHaveProperty('X-Dev-Viewer-Secret')
  })
})
