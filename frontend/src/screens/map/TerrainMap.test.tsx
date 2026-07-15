import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { summarizeProfile } from '../../data/geo'
import type { RouteGeometry, TrailGeo } from '../../data/vm'
import { TerrainMap } from './TerrainMap'
import * as webgl from './webgl'

// jsdom has no WebGL → TerrainMap always renders the static fallback here, so
// the honest states, attribution, controls, and scrub sync are all verifiable
// without a GL context (the GL path is exercised on the Vercel preview).

const LINE: RouteGeometry = {
  type: 'LineString',
  coordinates: [
    [-78.4, 38.5],
    [-78.39, 38.51],
    [-78.38, 38.52],
    [-78.37, 38.53],
  ],
}

const profile = summarizeProfile(
  [
    { distanceMeters: 0, elevationMeters: 1000 },
    { distanceMeters: 800, elevationMeters: 1180 },
    { distanceMeters: 1600, elevationMeters: 1320 },
  ],
  'USGS 3DEP (sample)',
  10,
)

const mapped: TrailGeo = {
  geometry: LINE,
  trailhead: { lat: 38.5, lon: -78.4 },
  summit: { lat: 38.53, lon: -78.37 },
  quality: 'confident',
  elevationProfile: profile,
}

const approximate: TrailGeo = { ...mapped, quality: 'approximate' }

// A trail with no surveyed trailhead: the start is a derived, approximate access point.
const derivedStart: TrailGeo = {
  ...mapped,
  trailhead: { lat: 38.5, lon: -78.4, derived: true },
}

const unmapped: TrailGeo = {
  geometry: null,
  trailhead: { lat: 38.556, lon: -78.387 },
  quality: 'confident',
  elevationProfile: null,
}

afterEach(() => vi.restoreAllMocks())

describe('TerrainMap — attribution + honest states (S2/S3)', () => {
  it('shows persistent USGS + OpenStreetMap/ODbL attribution (AC-2.4)', () => {
    render(<TerrainMap geo={mapped} trailName="Stony Man Loop" />)
    const credit = screen.getByText(/OpenStreetMap contributors \(ODbL\)/i)
    expect(credit).toBeInTheDocument()
    expect(credit.textContent).toMatch(/USGS/i)
  })

  it('draws the route over a neutral background when GL is unavailable (AC-3.3)', () => {
    const { container } = render(<TerrainMap geo={mapped} trailName="Stony Man Loop" />)
    expect(container.querySelector('.map-static-route')).toBeInTheDocument()
    expect(container.querySelector('.map-static-route--dashed')).not.toBeInTheDocument()
  })

  it('discloses a trailhead-only state for null geometry (AC-3.1)', () => {
    const { container } = render(<TerrainMap geo={unmapped} trailName="Hawksbill Summit" />)
    expect(screen.getByText(/route not mapped — trailhead only/i)).toBeInTheDocument()
    expect(container.querySelector('.map-static-route')).not.toBeInTheDocument()
    // The trailhead marker still anchors the map.
    expect(container.querySelector('.map-static-trailhead')).toBeInTheDocument()
  })

  it('draws an approximate route dashed and says so (AC-3.2)', () => {
    const { container } = render(<TerrainMap geo={approximate} trailName="Dark Hollow Falls" />)
    expect(screen.getByText(/approximate route — low source agreement/i)).toBeInTheDocument()
    expect(container.querySelector('.map-static-route--dashed')).toBeInTheDocument()
  })

  it('discloses a derived, approximate start when there is no surveyed trailhead (D7)', () => {
    render(<TerrainMap geo={derivedStart} trailName="Duck Boardwalk" />)
    expect(
      screen.getByText(/approximate start — nearest access point, no surveyed trailhead/i),
    ).toBeInTheDocument()
  })

  it('does not disclose an approximate start for a surveyed trailhead (Shenandoah unchanged)', () => {
    render(<TerrainMap geo={mapped} trailName="Stony Man Loop" />)
    expect(screen.queryByText(/approximate start/i)).not.toBeInTheDocument()
  })

  it('degrades the elevation strip honestly when there is no profile (AC-5.2)', () => {
    render(<TerrainMap geo={unmapped} trailName="Hawksbill Summit" />)
    expect(screen.getByText(/detailed elevation profile coming soon/i)).toBeInTheDocument()
  })
})

describe('TerrainMap — controls (S6)', () => {
  it('switches base layers and updates the attribution credit (AC-6.1)', async () => {
    const user = userEvent.setup()
    render(<TerrainMap geo={mapped} trailName="Stony Man Loop" />)
    const group = screen.getByRole('group', { name: /base map layer/i })
    const imagery = within(group).getByRole('button', { name: 'Imagery' })
    expect(within(group).getByRole('button', { name: 'Topo' })).toHaveAttribute('aria-pressed', 'true')
    await user.click(imagery)
    expect(imagery).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText(/Orthoimagery/i)).toBeInTheDocument()
  })

  it('deep-links driving directions to the trailhead (AC-6.4)', () => {
    render(<TerrainMap geo={mapped} trailName="Stony Man Loop" />)
    const link = screen.getByRole('link', { name: /directions/i })
    expect(link).toHaveAttribute('href', expect.stringContaining('google.com/maps/dir/'))
    expect(link).toHaveAttribute('href', expect.stringContaining('travelmode=driving'))
    expect(link.getAttribute('href')).toContain(encodeURIComponent('38.5,-78.4'))
  })

  it('toggles fullscreen as a focus-contained dialog and exits on Escape (AC-6.2)', async () => {
    const user = userEvent.setup()
    const { container } = render(<TerrainMap geo={mapped} trailName="Stony Man Loop" />)
    const block = container.querySelector('.terrain-block')!
    expect(block).not.toHaveClass('terrain-block--full')
    expect(block).not.toHaveAttribute('role')
    await user.click(screen.getByRole('button', { name: /^fullscreen$/i }))
    expect(block).toHaveClass('terrain-block--full')
    // Modal semantics so AT treats the page behind it as inert, and focus moves in.
    expect(block).toHaveAttribute('role', 'dialog')
    expect(block).toHaveAttribute('aria-modal', 'true')
    expect(block).toHaveFocus()
    await user.keyboard('{Escape}')
    expect(block).not.toHaveClass('terrain-block--full')
    expect(block).not.toHaveAttribute('aria-modal')
  })

  it('requests geolocation only on tap and discloses denial (AC-6.3)', async () => {
    const getCurrentPosition = vi.fn((_ok, err) => err({ code: 1, message: 'denied' }))
    Object.defineProperty(navigator, 'geolocation', {
      value: { getCurrentPosition },
      configurable: true,
    })
    const user = userEvent.setup()
    render(<TerrainMap geo={mapped} trailName="Stony Man Loop" />)
    // Not requested until the user taps.
    expect(getCurrentPosition).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: /locate me/i }))
    expect(getCurrentPosition).toHaveBeenCalledTimes(1)
    expect(await screen.findByText(/location off/i)).toBeInTheDocument()
  })

  it('accepts a granted fix without surfacing an error note (AC-6.3)', async () => {
    const getCurrentPosition = vi.fn((ok) => ok({ coords: { latitude: 37.5, longitude: -77.4 } }))
    Object.defineProperty(navigator, 'geolocation', {
      value: { getCurrentPosition },
      configurable: true,
    })
    const user = userEvent.setup()
    render(<TerrainMap geo={mapped} trailName="Stony Man Loop" />)
    await user.click(screen.getByRole('button', { name: /locate me/i }))
    expect(getCurrentPosition).toHaveBeenCalledTimes(1)
    // A successful fix is silent — no "location off"/unavailable disclosure, and
    // the control returns from its "Locating…" state rather than getting stuck.
    expect(screen.queryByText(/location off|isn’t available/i)).not.toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /locate me/i })).toBeInTheDocument()
  })
})

describe('TerrainMap — elevation scrub sync (S5b)', () => {
  it('moves a synced route cursor when the profile is scrubbed by keyboard (AC-5.3)', async () => {
    const user = userEvent.setup()
    const { container } = render(<TerrainMap geo={mapped} trailName="Stony Man Loop" />)
    const slider = screen.getByRole('slider', { name: /elevation/i })
    expect(container.querySelector('.map-static-cursor')).not.toBeInTheDocument()
    slider.focus()
    await user.keyboard('{ArrowRight}{ArrowRight}')
    expect(Number(slider.getAttribute('aria-valuenow'))).toBeGreaterThan(0)
    // The scrub dropped a synced marker on the route.
    expect(container.querySelector('.map-static-cursor')).toBeInTheDocument()
  })
})

describe('TerrainMap — zoom hint pointer gate (S5 / E1)', () => {
  beforeEach(() => {
    vi.spyOn(webgl, 'supportsWebGL').mockReturnValue(true)
  })

  it('hides the ⌘+scroll hint on coarse pointer (touch) devices (AC-5.1)', () => {
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: true }))
    render(<TerrainMap geo={mapped} trailName="Stony Man Loop" />)
    expect(screen.queryByText(/Use ⌘ \+ scroll/i)).not.toBeInTheDocument()
  })

  it('shows the ⌘+scroll hint on fine pointer (mouse/trackpad) devices (AC-5.1)', () => {
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: false }))
    render(<TerrainMap geo={mapped} trailName="Stony Man Loop" />)
    expect(screen.getByText(/Use ⌘ \+ scroll/i)).toBeInTheDocument()
  })

  it('shows the hint by default when matchMedia is unavailable (defensive default)', () => {
    vi.stubGlobal('matchMedia', undefined)
    render(<TerrainMap geo={mapped} trailName="Stony Man Loop" />)
    expect(screen.getByText(/Use ⌘ \+ scroll/i)).toBeInTheDocument()
  })
})
