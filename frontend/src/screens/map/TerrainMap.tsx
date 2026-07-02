/**
 * The Detail "map / terrain" block (Epic 016 §B) — the orchestrator that owns
 * the shared cursor, the chosen layer, fullscreen, and locate-me, and chooses
 * between the interactive GL map (lazy, WebGL-gated) and the static route
 * fallback. It renders the honest states (S3), the persistent attribution (D7),
 * the controls (S6), and the elevation profile (S5b) around whichever map is up.
 */
import { lazy, Suspense, useEffect, useRef, useState } from 'react'

import { isDrawableRoute, trailheadDirectionsUrl } from '../../data/geo'
import type { GeoPosition, TrailGeo } from '../../data/vm'
import { ElevationProfile } from './ElevationProfile'
import { layerByKey, OSM_ATTRIBUTION, type MapLayerKey } from './layers'
import { MapControls } from './MapControls'
import { StaticRoute } from './StaticRoute'
import { supportsWebGL } from './webgl'

// Code-split (D6/AC-2.1): the only static import of the map library lives behind
// this dynamic import, so it lands in its own chunk, off the feed path.
const MapPanel = lazy(() => import('./MapPanel'))

export function TerrainMap({ geo, trailName }: { geo: TrailGeo; trailName: string }) {
  const [interactive] = useState(supportsWebGL)
  const [layer, setLayer] = useState<MapLayerKey>('topo')
  const [cursor, setCursor] = useState<number | null>(null)
  const [fullscreen, setFullscreen] = useState(false)
  const [userLocation, setUserLocation] = useState<GeoPosition | null>(null)
  const [locating, setLocating] = useState(false)
  const [locateNote, setLocateNote] = useState<string | null>(null)
  const [tileError, setTileError] = useState(false)
  const dialogRef = useRef<HTMLElement>(null)
  const restoreFocusRef = useRef<HTMLElement | null>(null)

  // Fullscreen is a modal overlay: Escape exits (the back/close affordance,
  // mirroring the sheet pattern — it's component state, not a route, so it never
  // surprises browser Back, R12); on enter we move focus into the overlay and on
  // exit restore it, and the section is `role=dialog aria-modal` so assistive
  // tech treats the page behind it as inert (WCAG 2.4.3 / 4.1.2).
  useEffect(() => {
    if (!fullscreen) return
    restoreFocusRef.current = document.activeElement as HTMLElement | null
    dialogRef.current?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setFullscreen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      restoreFocusRef.current?.focus?.()
    }
  }, [fullscreen])

  const locate = () => {
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      setLocateNote('Location isn’t available on this device.')
      return
    }
    setLocating(true)
    setLocateNote(null)
    // Permission is requested ONLY here, on tap, and lazily (AC-6.3).
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setUserLocation({ lat: pos.coords.latitude, lon: pos.coords.longitude })
        setLocating(false)
      },
      () => {
        setLocating(false)
        setLocateNote('Location off — the map still shows the route to the trailhead.')
      },
      { enableHighAccuracy: true, timeout: 10_000 },
    )
  }

  const unmapped = !isDrawableRoute(geo.geometry)
  const approximate = geo.quality === 'approximate' && !unmapped
  // Source-or-silence (Rule #1 / D7): the start marker is a derived, approximate access
  // point when the trail has no surveyed trailhead — disclose it, never pass it off as
  // a real trailhead.
  const derivedStart = geo.trailhead.derived === true
  const layerCredit = layerByKey(layer).attribution

  return (
    <section
      ref={dialogRef}
      className={`detail-block terrain-block${fullscreen ? ' terrain-block--full' : ''}`}
      aria-label="Map and terrain"
      role={fullscreen ? 'dialog' : undefined}
      aria-modal={fullscreen || undefined}
      tabIndex={fullscreen ? -1 : undefined}
    >
      <p className="kicker">Map &amp; terrain</p>

      <div className="map-panel">
        {interactive && !unmapped ? (
          <Suspense fallback={<div className="map-loading" aria-hidden="true" />}>
            <MapPanel
              geo={geo}
              layer={layer}
              cursorFraction={cursor}
              onRouteClick={setCursor}
              onTileError={() => setTileError(true)}
              userLocation={userLocation}
            />
          </Suspense>
        ) : (
          <StaticRoute geo={geo} cursorFraction={cursor} />
        )}

        {/* Persistent, non-dismissable credit, in the map chrome (D7/AC-2.4). */}
        <p className="map-attribution">
          {layerCredit} · {OSM_ATTRIBUTION}
        </p>
      </div>

      <MapControls
        layer={layer}
        onLayerChange={setLayer}
        fullscreen={fullscreen}
        onToggleFullscreen={() => setFullscreen((v) => !v)}
        onLocate={locate}
        locating={locating}
        directionsUrl={trailheadDirectionsUrl(geo.trailhead)}
      />

      {(unmapped ||
        approximate ||
        derivedStart ||
        tileError ||
        (!interactive && !unmapped) ||
        locateNote) && (
        <div className="map-notes" role="status">
          {unmapped ? <p className="map-note">Route not mapped — trailhead only.</p> : null}
          {approximate ? <p className="map-note">Approximate route — low source agreement.</p> : null}
          {derivedStart ? (
            <p className="map-note">Approximate start — nearest access point, no surveyed trailhead.</p>
          ) : null}
          {tileError ? (
            <p className="map-note">Map imagery is having trouble — showing the route over a neutral map.</p>
          ) : null}
          {!interactive && !unmapped && !tileError ? (
            <p className="map-note">Static map view — showing the route over a neutral map.</p>
          ) : null}
          {locateNote ? <p className="map-note">{locateNote}</p> : null}
        </div>
      )}

      {geo.elevationProfile ? (
        <ElevationProfile profile={geo.elevationProfile} cursorFraction={cursor} onScrub={setCursor} />
      ) : (
        <p className="elev-soon">Detailed elevation profile coming soon for {trailName}.</p>
      )}
    </section>
  )
}
