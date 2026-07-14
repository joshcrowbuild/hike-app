import { describe, expect, it } from 'vitest'

import { deriveDifficulty, deriveSummary, resolveDurationMinutes } from './summary'
import type { CardVM, ElevationProfile, RouteGeometry, TrailGeo } from './vm'

/** A minimal live card; override the fact-bearing bits per case. */
function card(over: Partial<CardVM> = {}): CardVM {
  return { id: 't1', name: 'Trail', distanceMi: null, conditionLines: [], warnings: [], ...over }
}

/** A live `TrailGeo` built from a plain waypoint list (GeoJSON `[lon, lat]`). */
function geo(waypoints: [number, number][] | null, over: Partial<TrailGeo> = {}): TrailGeo {
  const geometry: RouteGeometry | null = waypoints ? { type: 'LineString', coordinates: waypoints } : null
  return { geometry, trailhead: { lat: waypoints?.[0][1] ?? 0, lon: waypoints?.[0][0] ?? 0 }, quality: 'confident', elevationProfile: null, ...over }
}

const profile = (gainM: number, lossM: number): ElevationProfile => ({
  samples: [],
  totalGainMeters: gainM,
  totalLossMeters: lossM,
  maxGradePercent: 0,
  source: 'USGS 3DEP',
  resolutionMeters: 10,
})

// A short (~1.6 km) open out-and-back line and a closed (~1.6 km) loop line.
const OPEN: [number, number][] = [[-78.4, 38.5], [-78.39, 38.505], [-78.38, 38.51]]
const LOOP: [number, number][] = [[-78.4, 38.5], [-78.395, 38.508], [-78.39, 38.5], [-78.4, 38.5]]

describe('deriveSummary — an honest one-line character (source-or-silence, R1)', () => {
  it('a live open line with climb → out-and-back + mileage + climb', () => {
    const c = card({ geo: geo(OPEN, { elevationProfile: profile(90, 10) }) })
    expect(deriveSummary(c)).toMatch(/^An? [\d.]+-mile out-and-back, climbing \d+ ft\.$/)
  })

  it('a closed geometry is read as a loop, from its endpoints alone', () => {
    const c = card({ geo: geo(LOOP, { elevationProfile: profile(90, 90) }) })
    expect(deriveSummary(c)).toMatch(/-mile loop, climbing/)
  })

  it('an out-and-back states the ROUND-TRIP mileage — what the hiker actually walks (Josh, 2026-07-03)', () => {
    // OPEN's mapped one-way length is ~1.28 mi; the line must show the 2.6 mi
    // round trip, never the one-way figure.
    const c = card({ geo: geo(OPEN, { elevationProfile: profile(90, 10) }) })
    expect(deriveSummary(c)).toMatch(/^An? 2\.6-mile out-and-back/)
  })

  it('a loop states its own path length, never doubled — the loop already IS the full walk', () => {
    // LOOP's mapped length is ~1.77 mi; doubling would be wrong since a loop
    // walker never retraces the line.
    const c = card({ geo: geo(LOOP, { elevationProfile: profile(90, 90) }) })
    expect(deriveSummary(c)).toMatch(/^A 1\.8-mile loop/)
  })

  it('when the shape can’t be confirmed (no geometry), the curated distance is taken at face value — never doubled blind', () => {
    const c = card({ enrichment: { provenance: 'mock', distanceMiles: 3.7, ascentFeet: 1050 } })
    expect(deriveSummary(c)).toMatch(/^An? 3\.7-mile trail/)
  })

  it('a marked summit is named — but only when a summit coordinate exists', () => {
    const withSummit = card({ geo: geo(OPEN, { elevationProfile: profile(120, 5), summit: { lat: 38.51, lon: -78.38 } }) })
    expect(deriveSummary(withSummit)).toMatch(/climbing \d+ ft to a summit\.$/)
    const noSummit = card({ geo: geo(OPEN, { elevationProfile: profile(120, 5) }) })
    expect(deriveSummary(noSummit)).not.toMatch(/summit/)
  })

  it('“flat” only when BOTH directions barely move — never on a one-way descent', () => {
    const flat = card({ geo: geo(OPEN, { elevationProfile: profile(8, 6) }) })
    expect(deriveSummary(flat)).toMatch(/^A flat .*out-and-back\.$/)
    // gain≈0 but real loss → a descent, not flat: we stay silent on grade.
    const descent = card({ geo: geo(OPEN, { elevationProfile: profile(0, 120) }) })
    const s = deriveSummary(descent)!
    expect(s).not.toMatch(/flat/)
    expect(s).not.toMatch(/climbing/)
    expect(s).toMatch(/-mile out-and-back\.$/)
  })

  it('a small climb below the floor is dropped, never stated as rounding noise', () => {
    const c = card({ geo: geo(OPEN, { elevationProfile: profile(10, 0) }) })
    expect(deriveSummary(c)).not.toMatch(/climbing/)
  })

  it('missing elevation profile → the climb clause is simply omitted (say less)', () => {
    const c = card({ geo: geo(OPEN) })
    const s = deriveSummary(c)!
    expect(s).toMatch(/-mile out-and-back\.$/)
    expect(s).not.toMatch(/climbing/)
  })

  it('no geo and no enrichment → nothing to say, returns null (never padded)', () => {
    expect(deriveSummary(card())).toBeNull()
  })

  it('prefers the curated trail length over the crow-flies distanceMi', () => {
    // distanceMi is origin→trailhead, NOT the trail — it must never leak in.
    const c = card({ distanceMi: 12.3, enrichment: { provenance: 'mock', distanceMiles: 3.7, ascentFeet: 1050 } })
    const s = deriveSummary(c)!
    expect(s).toMatch(/3\.7-mile/)
    expect(s).not.toMatch(/12/)
  })

  it('a live “good to go” gets a clear-today tail; a hazard never does', () => {
    const clearBase = { geo: geo(OPEN, { elevationProfile: profile(90, 10) }) }
    const clear = card({ ...clearBase, conditionLines: [{ text: 'Sunny 68°F', source: 'NWS', confidence: 'stated', provenance: 'live' }] })
    expect(deriveSummary(clear)).toMatch(/ — clear today\.$/)
    const hazard = card({ ...clearBase, warnings: [{ text: 'Heat Warning', source: 'NWS', observedAgo: 'now', kind: 'weather', provenance: 'live' }] })
    expect(deriveSummary(hazard)).not.toMatch(/clear today/)
  })

  it('sample (non-live) data never claims a clear day', () => {
    const c = card({
      enrichment: { provenance: 'mock', distanceMiles: 2, ascentFeet: 300, conditionValue: '54°F · clear' },
      conditionLines: [{ text: '54°F · clear', source: 'x', confidence: 'stated', provenance: 'mock' }],
    })
    expect(deriveSummary(c)).not.toMatch(/clear today/)
  })

  it('picks the article by spoken sound — “An 8-mile”, “A 1.1-mile”, “An out-and-back”', () => {
    const eight = card({ enrichment: { provenance: 'live', distanceMiles: 8, ascentFeet: 500 } })
    expect(deriveSummary(eight)).toMatch(/^An 8-mile/)
    const oneish = card({ enrichment: { provenance: 'live', distanceMiles: 1.1, ascentFeet: 500 } })
    expect(deriveSummary(oneish)).toMatch(/^A 1\.1-mile/)
    // shape-only subject (no length): an open line with no measurable data path.
    const openOnly = card({ geo: geo(OPEN) })
    expect(deriveSummary(openOnly)).toMatch(/^A [\d.]+-mile out-and-back/)
  })
})

describe('deriveDifficulty — a transparent, derived estimate (never a rank input, R2)', () => {
  it('bands from √(2·climb·miles): easy → very-strenuous', () => {
    expect(deriveDifficulty(card({ enrichment: { provenance: 'live', distanceMiles: 1, ascentFeet: 200 } }))?.band).toBe('easy')
    expect(deriveDifficulty(card({ enrichment: { provenance: 'live', distanceMiles: 3.7, ascentFeet: 1050 } }))?.band).toBe('moderate')
    expect(deriveDifficulty(card({ enrichment: { provenance: 'live', distanceMiles: 5.2, ascentFeet: 1420 } }))?.band).toBe('strenuous')
    expect(deriveDifficulty(card({ enrichment: { provenance: 'live', distanceMiles: 9.4, ascentFeet: 2580 } }))?.band).toBe('very-strenuous')
  })

  it('exposes the numeric score so the estimate is inspectable', () => {
    const d = deriveDifficulty(card({ enrichment: { provenance: 'live', distanceMiles: 3.7, ascentFeet: 1050 } }))
    expect(d?.score).toBe(88) // round(√(2·1050·3.7))
    expect(d?.label).toBe('Moderate')
  })

  it('bands an out-and-back off the ROUND-TRIP mileage, not the one-way figure (Josh, 2026-07-03)', () => {
    // Same OPEN geometry + 762 m (2500 ft) climb: the one-way distance alone
    // (~1.28 mi) scores "moderate"; the round trip (~2.57 mi) the hiker
    // actually walks pushes it into "strenuous".
    const c = card({ geo: geo(OPEN, { elevationProfile: profile(762, 10) }) })
    const d = deriveDifficulty(c)
    expect(d?.band).toBe('strenuous')
  })

  it('never doubles a loop’s mileage when banding difficulty', () => {
    const c = card({ geo: geo(LOOP, { elevationProfile: profile(762, 762) }) })
    const d = deriveDifficulty(c)
    expect(d?.score).toBe(Math.round(Math.sqrt(2 * 2500 * 1.7713686991398496)))
  })

  it('carries provenance so a sample estimate can demote/tag (R1)', () => {
    expect(deriveDifficulty(card({ enrichment: { provenance: 'mock', distanceMiles: 3, ascentFeet: 400 } }))?.provenance).toBe('mock')
    expect(deriveDifficulty(card({ geo: geo(OPEN, { elevationProfile: profile(100, 0) }) }))?.provenance).toBe('live')
  })

  it('is null-safe: no climb OR no length → no estimate at all', () => {
    expect(deriveDifficulty(card({ geo: geo(OPEN) }))).toBeNull() // length but no profile
    expect(deriveDifficulty(card())).toBeNull()
    // crow-flies distanceMi alone is not a trail length → still no estimate.
    expect(deriveDifficulty(card({ distanceMi: 5 }))).toBeNull()
  })

  it('computes a live estimate from geometry + profile with no enrichment', () => {
    const d = deriveDifficulty(card({ geo: geo(OPEN, { elevationProfile: profile(100, 0) }) }))
    expect(d).not.toBeNull()
    expect(d?.band).toBe('easy')
    expect(d?.provenance).toBe('live')
  })
})

describe('resolveDurationMinutes — one geometry SSOT for the fact row (H4/F7, ux-review 2026-07)', () => {
  it('doubles a one-way profile duration for a confident out-and-back — matches resolveMiles’s own doubling', () => {
    // OPEN's round-trip length is the same ~2.6 mi `deriveSummary` states; 60 min
    // over 2.6 mi ≈ 2.6 mph, a plausible pace.
    const c = card({ geo: geo(OPEN, { elevationProfile: { ...profile(90, 10), estimatedDurationMin: 30 } }) })
    expect(resolveDurationMinutes(c)).toBe(60)
  })

  it('never doubles a loop’s duration — the loop already covers the full walk', () => {
    const c = card({ geo: geo(LOOP, { elevationProfile: { ...profile(90, 90), estimatedDurationMin: 40 } }) })
    expect(resolveDurationMinutes(c)).toBe(40)
  })

  it('drops the fact when the implied pace falls outside a plausible hiking band (0.5–4 mph)', () => {
    // Doubled to 10 min round-trip over ~2.6 mi ≈ 15.6 mph — not a hike.
    const c = card({ geo: geo(OPEN, { elevationProfile: { ...profile(90, 10), estimatedDurationMin: 5 } }) })
    expect(resolveDurationMinutes(c)).toBeNull()
  })

  it('keeps a plausible estimate whose pace holds together with the shown distance', () => {
    // Doubled to 104 min round-trip over ~2.6 mi ≈ 1.5 mph — comfortably inside the band.
    const c = card({ geo: geo(OPEN, { elevationProfile: { ...profile(90, 10), estimatedDurationMin: 52 } }) })
    expect(resolveDurationMinutes(c)).toBe(104)
  })

  it('skips the pace check (but still returns the raw estimate) when no distance is resolvable at all', () => {
    const c = card({
      geo: { geometry: null, trailhead: { lat: 0, lon: 0 }, quality: 'confident', elevationProfile: { ...profile(90, 10), estimatedDurationMin: 5 } },
    })
    expect(resolveDurationMinutes(c)).toBe(5)
  })

  it('returns null with no live estimate present', () => {
    expect(resolveDurationMinutes(card({ geo: geo(OPEN, { elevationProfile: profile(90, 10) }) }))).toBeNull()
    expect(resolveDurationMinutes(card())).toBeNull()
  })
})
