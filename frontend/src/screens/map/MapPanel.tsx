/**
 * The interactive MapLibre panel (S2) — the ONLY module that imports the map
 * library, loaded lazily and on Detail alone (D6/AC-2.1). It draws the USGS
 * topo basemap, the route (solid or dashed), and the trailhead/summit markers,
 * fit to bounds, with a cursor marker kept in sync with the elevation profile.
 *
 * Geolocation and tile-error notices are owned by the parent (TerrainMap) so
 * they stay testable without a GL context; this component only renders the
 * resulting user-location marker and reports errors upward.
 */
import { useCallback, useEffect, useRef } from 'react'
import Map, {
  Layer,
  Marker,
  ScaleControl,
  Source,
  type ErrorEvent,
  type LayerProps,
  type MapMouseEvent,
  type MapRef,
} from 'react-map-gl/maplibre'
import type { FeatureCollection } from 'geojson'
import 'maplibre-gl/dist/maplibre-gl.css'

import { boundsOf, expandBounds, nearestFractionToPoint, pointAtFraction } from '../../data/geo'
import type { Bounds } from '../../data/geo'
import type { GeoPosition, TrailGeo } from '../../data/vm'
import { basemapStyle } from './mapStyle'
import type { MapLayerKey } from './layers'

export interface MapPanelProps {
  geo: TrailGeo
  layer: MapLayerKey
  /** Profile cursor (0..1 of route length) → a synced marker on the route. */
  cursorFraction: number | null
  /** Tapping the route → the nearest fraction, to move the profile cursor. */
  onRouteClick: (fraction: number) => void
  /** A tile/source error → a non-blocking notice (the GL map stays up). */
  onTileError: () => void
  /** Device location (from the parent's permission-gated request), or null. */
  userLocation: GeoPosition | null
}

const ROUTE_INK = '#23211c'

export default function MapPanel({
  geo,
  layer,
  cursorFraction,
  onRouteClick,
  onTileError,
  userLocation,
}: MapPanelProps) {
  const ref = useRef<MapRef>(null)

  const fitToBounds = useCallback((bounds: Bounds, duration: number) => {
    const map = ref.current
    if (!map) return
    const [[w, s], [e, n]] = bounds
    if (w === e && s === n) {
      map.flyTo({ center: [w, s], zoom: 13, duration })
    } else {
      map.fitBounds(
        [
          [w, s],
          [e, n],
        ],
        { padding: 44, duration, maxZoom: 15 },
      )
    }
  }, [])

  // Initial framing (on GL load): the route + trailhead, no animation.
  const fit = useCallback(() => fitToBounds(boundsOf(geo), 0), [fitToBounds, geo])

  // When a "Locate me" fix lands, reframe to include the viewer's position so
  // the marker is always on-screen — otherwise a fix taken far from the trail
  // (planning from home) is placed outside the route bounds and the button
  // appears to do nothing. Animated, so the move is legible as feedback.
  useEffect(() => {
    if (!userLocation) return
    fitToBounds(expandBounds(boundsOf(geo), userLocation), 600)
  }, [userLocation, geo, fitToBounds])

  const handleClick = useCallback(
    (event: MapMouseEvent) => {
      if (!geo.geometry) return
      onRouteClick(nearestFractionToPoint(geo.geometry, [event.lngLat.lng, event.lngLat.lat]))
    },
    [geo.geometry, onRouteClick],
  )

  const handleError = useCallback((_event: ErrorEvent) => onTileError(), [onTileError])

  const routeData: FeatureCollection | null = geo.geometry
    ? { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: geo.geometry, properties: {} }] }
    : null

  const dash = geo.quality === 'approximate' ? { 'line-dasharray': [1.4, 1.3] as [number, number] } : {}
  const casing: LayerProps = {
    id: 'route-casing',
    type: 'line',
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': '#fbfaf7', 'line-width': 7, 'line-opacity': 0.9, ...dash },
  }
  const line: LayerProps = {
    id: 'route-line',
    type: 'line',
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': ROUTE_INK, 'line-width': 3.5, ...dash },
  }

  const cursor =
    geo.geometry && cursorFraction != null ? pointAtFraction(geo.geometry, cursorFraction) : null

  return (
    <Map
      ref={ref}
      initialViewState={{ longitude: geo.trailhead.lon, latitude: geo.trailhead.lat, zoom: 12 }}
      mapStyle={basemapStyle(layer)}
      attributionControl={false}
      cooperativeGestures
      dragRotate={false}
      onLoad={fit}
      onClick={handleClick}
      onError={handleError}
      style={{ width: '100%', height: '100%' }}
    >
      {routeData ? (
        <Source id="route" type="geojson" data={routeData}>
          <Layer {...casing} />
          <Layer {...line} />
        </Source>
      ) : null}

      <Marker longitude={geo.trailhead.lon} latitude={geo.trailhead.lat} anchor="bottom">
        <span className="map-marker map-marker--trailhead" aria-hidden="true" />
      </Marker>

      {geo.summit ? (
        <Marker longitude={geo.summit.lon} latitude={geo.summit.lat} anchor="center">
          <span className="map-marker map-marker--summit" aria-hidden="true" />
        </Marker>
      ) : null}

      {cursor ? (
        <Marker longitude={cursor[0]} latitude={cursor[1]} anchor="center">
          <span className="map-marker map-marker--cursor" aria-hidden="true" />
        </Marker>
      ) : null}

      {userLocation ? (
        <Marker longitude={userLocation.lon} latitude={userLocation.lat} anchor="center">
          <span className="map-marker map-marker--me" aria-hidden="true" />
        </Marker>
      ) : null}

      <ScaleControl position="bottom-left" unit="imperial" />
    </Map>
  )
}
