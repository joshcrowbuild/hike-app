import { describe, expect, it } from 'vitest'

import { metersToFeet, routeLengthMeters } from '../geo'
import { ANON_SCOPE } from '../api'
import { trails } from './engine'
import { buildTrailGeo } from './geoFixtures'
import { MockPlannerClient } from './mockPlanner'

describe('mock trail geometry fixtures', () => {
  it('attaches a geo payload with a trailhead to every trail', () => {
    expect(trails.length).toBeGreaterThan(0)
    for (const trail of trails) {
      expect(trail.geo).toBeDefined()
      expect(trail.geo.trailhead.lat).toBeTypeOf('number')
      expect(trail.geo.trailhead.lon).toBeTypeOf('number')
    }
  })

  it('gives mapped trails a real LineString route fit for drawing', () => {
    const stony = trails.find((t) => t.id === 'stony-man')!
    expect(stony.geo.geometry?.type).toBe('LineString')
    expect((stony.geo.geometry?.coordinates.length ?? 0)).toBeGreaterThan(4)
    expect(routeLengthMeters(stony.geo.geometry!)).toBeGreaterThan(0)
  })

  it('exercises the honest states: an approximate route and an unmapped trail', () => {
    const dark = trails.find((t) => t.id === 'dark-hollow')!
    expect(dark.geo.quality).toBe('approximate')
    expect(dark.geo.geometry).not.toBeNull()

    const hawksbill = trails.find((t) => t.id === 'hawksbill')!
    expect(hawksbill.geo.geometry).toBeNull()
    expect(hawksbill.geo.elevationProfile).toBeNull()
  })

  it('scales the profile so reported gain tracks the card ascent (no faked curve)', () => {
    const stony = trails.find((t) => t.id === 'stony-man')!
    const profile = stony.geo.elevationProfile!
    expect(profile.samples.length).toBeGreaterThan(10)
    // Gain in feet should be within ~5% of the trail's stated ascent.
    const gainFeet = metersToFeet(profile.totalGainMeters)
    expect(gainFeet).toBeGreaterThan(stony.ascentFeet * 0.95)
    expect(gainFeet).toBeLessThan(stony.ascentFeet * 1.05)
    // Distance axis tracks the stated mileage.
    const lastM = profile.samples[profile.samples.length - 1].distanceMeters
    expect(lastM / 1609.344).toBeCloseTo(stony.distanceMiles, 1)
  })

  it('throws for an unknown trail rather than fabricating geometry', () => {
    expect(() => buildTrailGeo('not-a-trail', 1, 1)).toThrow()
  })
})

describe('MockPlannerClient geo threading', () => {
  it('returns the geo payload on a fetched card', async () => {
    const client = new MockPlannerClient()
    const card = await client.getCard('stony-man', ANON_SCOPE)
    expect(card?.geo?.geometry?.type).toBe('LineString')
    expect(card?.geo?.elevationProfile?.source).toContain('3DEP')
  })
})
