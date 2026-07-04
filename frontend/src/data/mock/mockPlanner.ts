/**
 * MockPlannerClient — the data source that runs tonight. It produces the VM
 * directly from the quarantined engine, shaped EXACTLY like what the HTTP
 * adapter will produce, so screens are written once. The only difference a
 * screen can observe is `dataSource: 'mock'` and `provenance` on each field —
 * which is the point: the surface discloses that this is sample data rather than
 * dressing it as verified (R1).
 */
import type { OriginKey, TuningState } from '../../types'
import type { OutcomeBody, ScopeContext } from '../api'
import type { PlanInput, PlannerClient } from '../source'
import type { CardVM, EpisodeVM, FeedVM, OutcomeVM, ReadinessVM, SetAside } from '../vm'
import { buildFitLine, runFeed, trails } from './engine'
import { findEpisode, listEpisodes, setOutcome } from './episodes'
import type { Trail } from '../../types'

const isAnonymous = (scope: ScopeContext): boolean => scope.viewerId === 'anonymous'

/** A neutral frame for anonymous: no personal lean, so the taste re-rank is a no-op (R7). */
function neutralize(tuning: TuningState): TuningState {
  return { ...tuning, party: 'solo', today: 'standard', readinessOn: false, prompt: '' }
}

function toCardVM(trail: Trail, tuning: TuningState, origin: OriginKey | undefined, anon: boolean): CardVM {
  return {
    id: trail.id,
    name: trail.name,
    // The mock has no crow-flies measure; declaring null is honest (the rich
    // decision row uses enrichment.distanceMiles/driveMinutes instead).
    distanceMi: null,
    conditionLines: [
      {
        text: trail.conditionValue,
        source: trail.sources[0] ?? 'NWS point forecast',
        confidence: 'stated',
        provenance: 'mock',
      },
    ],
    warnings: [],
    enrichment: {
      placeCue: trail.placeCue,
      area: trail.area,
      routeShape: trail.routeShape,
      distanceMiles: trail.distanceMiles,
      ascentFeet: trail.ascentFeet,
      durationHours: trail.durationHours,
      driveMinutes: origin ? trail.drives[origin] : undefined,
      effort: trail.effort,
      tags: trail.tags,
      // Omit the fit line entirely for anonymous — there is no "you" to fit (R7).
      fitLine: anon ? undefined : buildFitLine(trail, tuning),
      conditionValue: trail.conditionValue,
      freshness: trail.freshness,
      caution: trail.caution,
      // The card's "Character" line is now DERIVED from verified figures
      // (`deriveSummary`), not this hand-written prose — the fabricated texture
      // ("exposed rock", "clean summit reward") is exactly what can't scale
      // honestly (R1). The fixture field is left unused rather than propagated.
      practicalNote: trail.practicalNote,
      sources: trail.sources,
      provenance: 'mock',
    },
    // Sample route + elevation profile (AC-1.4); the map + glyph read this.
    geo: trail.geo,
  }
}

function readinessDisclosure(tuning: TuningState, anon: boolean): ReadinessVM {
  // Anonymous has no watch and no "you"; readiness is simply absent (R7).
  if (anon || !tuning.readinessOn) return { on: tuning.readinessOn && !anon, state: 'off' }
  // There is no real reading in the mock, so the filter fails OPEN and says so
  // (R2 / degrade-and-disclose). We never fake a recovery score.
  return {
    on: true,
    state: 'open',
    staleReason: 'No fresh reading yet — no watch is connected. Showing the full feed, nothing filtered.',
  }
}

export class MockPlannerClient implements PlannerClient {
  async plan(input: PlanInput, scope: ScopeContext): Promise<FeedVM> {
    const anon = isAnonymous(scope)
    const tuning = anon ? neutralize(input.tuning) : input.tuning
    const origin = anon ? undefined : tuning.origin

    const { kept, partySetAside } = runFeed(tuning)

    const cards = kept.map(({ trail }) => toCardVM(trail, tuning, origin, anon))
    const setAside: SetAside[] = partySetAside.map(({ trail, reason }) => ({
      id: trail.id,
      name: trail.name,
      reason,
      kind: 'party',
      restorable: true,
    }))

    return {
      query: input.tuning.prompt,
      cards,
      notices: [],
      setAside,
      // The mock engine has no live guardrail path; an honest empty, never faked.
      heldBack: [],
      readiness: readinessDisclosure(input.tuning, anon),
      dataSource: 'mock',
    }
  }

  async getCard(id: string, scope: ScopeContext, tuning?: TuningState): Promise<CardVM | null> {
    const trail = trails.find((t) => t.id === id)
    if (!trail) return null
    const anon = isAnonymous(scope)
    const origin = tuning?.origin
    // Frame-agnostic: drive is computed only when an origin is supplied; a cold
    // deep-link / anonymous viewer sees distance-only (R7).
    return toCardVM(trail, neutralize(tuning ?? defaultFrame), origin, anon)
  }

  async recentEpisodes(scope: ScopeContext): Promise<EpisodeVM[]> {
    // Episodes are personal; the anonymous world-browser has none (R7).
    if (isAnonymous(scope)) return []
    return listEpisodes()
  }

  async getEpisode(id: string, scope: ScopeContext): Promise<EpisodeVM | null> {
    if (isAnonymous(scope)) return null
    return findEpisode(id)
  }

  async recordOutcome(
    episodeId: string,
    body: OutcomeBody,
    companions: EpisodeVM['companions'],
    _scope: ScopeContext,
  ): Promise<OutcomeVM> {
    const updated = setOutcome(
      episodeId,
      { overall: body.overall, skipped: body.skipped },
      companions,
    )
    if (!updated) throw new Error('episode not found')
    return {
      outcomeId: `outcome-${episodeId}`,
      episodeId,
      overall: body.overall,
      skipped: body.skipped,
      companions,
    }
  }
}

// A minimal frame used only to satisfy buildFitLine for getCard (which is anon-
// safe and omits the fit line anyway); kept local so the mock owns its defaults.
const defaultFrame: TuningState = {
  origin: 'frontRoyal',
  when: 'weekendMorning',
  effort: 'moderate',
  party: 'solo',
  today: 'standard',
  readinessOn: false,
  prompt: '',
}
