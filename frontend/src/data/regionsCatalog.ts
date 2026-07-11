/**
 * Region + origin catalog (Phase 2: config-driven origins). The live app fetches
 * this once from `GET /regions` — sourced server-side from `regions/*.geojson` —
 * and caches it for the page's lifetime: the picker's option list, its labels, and
 * the origin→coordinates lookup `HttpPlannerClient` needs to call `/plan` all
 * derive from this one fetch. Adding a region's origins is now a `regions/*.geojson`
 * edit, never a frontend deploy.
 *
 * Mock mode has no backend to fetch from, so it resolves to a small static fixture
 * mirroring the pilot's original named origins — dev/test fixture data, kept in
 * lockstep with `mock/engine.ts`'s trail fixtures (which key `drives` by these same
 * origin keys), not the real config path.
 */
import { useEffect, useState } from 'react'

import type { Coords } from '../types'
import type { RegionsResponse } from './api'
import { haversineMeters } from './geo'
import { USE_MOCK } from './useMock'

export interface OriginOption extends Coords {
  key: string
  label: string
  /** The short display name of the region this origin anchors (e.g. "Shenandoah") —
   *  denormalized from the parent region so a card's nearest-origin region label
   *  (`resolveRegionLabel`) needs no separate lookup. */
  regionLabel: string
}

export interface RegionCatalogEntry {
  regionId: string
  label: string
  origins: OriginOption[]
}

const useMockDefault = USE_MOCK
const baseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://127.0.0.1:8000'

// Mock-mode fixture only (see module docstring) — the real app never reads this;
// `loadRegions` only falls back to it when there is no backend to ask.
const MOCK_REGIONS: RegionCatalogEntry[] = [
  {
    regionId: 'shenandoah-gwj',
    label: 'Shenandoah',
    origins: [
      { key: 'frontRoyal', label: 'Front Royal', lat: 38.918, lon: -78.194, regionLabel: 'Shenandoah' },
      { key: 'luray', label: 'Luray', lat: 38.665, lon: -78.459, regionLabel: 'Shenandoah' },
      {
        key: 'charlottesville',
        label: 'Charlottesville',
        lat: 38.029,
        lon: -78.477,
        regionLabel: 'Shenandoah',
      },
    ],
  },
  {
    regionId: 'richmond',
    label: 'Richmond',
    origins: [{ key: 'richmond', label: 'Richmond', lat: 37.5407, lon: -77.436, regionLabel: 'Richmond' }],
  },
  {
    regionId: 'outer-banks',
    label: 'Outer Banks',
    origins: [
      { key: 'duck', label: 'Duck', lat: 36.166, lon: -75.75, regionLabel: 'Outer Banks' },
      { key: 'nagsHead', label: 'Nags Head', lat: 35.957, lon: -75.624, regionLabel: 'Outer Banks' },
      { key: 'hatteras', label: 'Hatteras', lat: 35.22, lon: -75.69, regionLabel: 'Outer Banks' },
      { key: 'ocracoke', label: 'Ocracoke', lat: 35.115, lon: -75.98, regionLabel: 'Outer Banks' },
    ],
  },
]

async function fetchLiveRegions(): Promise<RegionCatalogEntry[]> {
  try {
    const resp = await fetch(`${baseUrl}/regions`)
    if (!resp.ok) return []
    const body = (await resp.json()) as RegionsResponse
    return body.regions.map((r) => ({
      regionId: r.region_id,
      label: r.label,
      origins: r.origins.map((o) => ({ ...o, regionLabel: r.label })),
    }))
  } catch {
    // Offline / unreachable API: an empty catalog degrades to no named origins
    // rather than a crash (Rule #1) — "Near me" still works.
    return []
  }
}

let cachedPromise: Promise<RegionCatalogEntry[]> | null = null
let cachedValue: RegionCatalogEntry[] | null = null

/** Fetched once per page load and cached — region config changes only on deploy,
 *  never mid-session. */
function loadRegions(): Promise<RegionCatalogEntry[]> {
  if (!cachedPromise) {
    cachedPromise = (useMockDefault ? Promise.resolve(MOCK_REGIONS) : fetchLiveRegions()).then((regions) => {
      cachedValue = regions
      return regions
    })
  }
  return cachedPromise
}

export function flattenOrigins(regions: RegionCatalogEntry[]): OriginOption[] {
  return regions.flatMap((r) => r.origins)
}

export function originCoordsMap(origins: OriginOption[]): Record<string, Coords> {
  return Object.fromEntries(origins.map((o) => [o.key, { lat: o.lat, lon: o.lon }]))
}

/** The picker's default order is alphabetical (no assumption about which named
 *  place is "closer" without a location to anchor that on). Once a live fix is
 *  available (`tuning.originCoords`, from "Near me" — see `NearMeControl`), the
 *  same list re-sorts nearest-first so switching from the exact fix to a named
 *  place doesn't mean scanning past a page of far-away regions. No location:
 *  graceful fallback to alphabetical. */
export function orderOrigins(origins: OriginOption[], location?: Coords): OriginOption[] {
  if (!location) return [...origins].sort((a, b) => a.label.localeCompare(b.label))
  const from: [number, number] = [location.lon, location.lat]
  return [...origins].sort(
    (a, b) => haversineMeters(from, [a.lon, a.lat]) - haversineMeters(from, [b.lon, b.lat]),
  )
}

/** The flattened origin list for the picker + origin→label/region lookups, loaded
 *  once and shared across every caller. Synchronous-fast once warm: a component
 *  mounting after the catalog has already resolved (the common case — the live app
 *  gates rendering on this in `PlannerProvider`) reads it with no loading flicker. */
export function useOrigins(): { origins: OriginOption[]; loading: boolean } {
  const [state, setState] = useState<{ origins: OriginOption[]; loading: boolean }>(() =>
    cachedValue ? { origins: flattenOrigins(cachedValue), loading: false } : { origins: [], loading: true },
  )

  useEffect(() => {
    if (!state.loading) return
    let live = true
    loadRegions().then((regions) => {
      if (live) setState({ origins: flattenOrigins(regions), loading: false })
    })
    return () => {
      live = false
    }
    // Runs once: `loading` only ever flips true → false for a given mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return state
}
