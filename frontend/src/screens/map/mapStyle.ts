/**
 * Builds the MapLibre raster style for a chosen USGS basemap. Only `MapPanel`
 * (the lazy chunk) imports this, so the `maplibre-gl` type import never reaches
 * the always-loaded bundle. The route + markers are added as react-map-gl
 * children, not baked into the style.
 */
import type { StyleSpecification } from 'maplibre-gl'

import { layerByKey, OSM_ATTRIBUTION, type MapLayerKey } from './layers'

export function basemapStyle(layer: MapLayerKey): StyleSpecification {
  const opt = layerByKey(layer)
  return {
    version: 8,
    sources: {
      basemap: {
        type: 'raster',
        tiles: [opt.tiles],
        tileSize: 256,
        maxzoom: opt.maxZoom,
        // MapLibre folds this into its AttributionControl; we also render a
        // persistent, non-dismissable credit in the chrome (D7) so it survives
        // a tile failure.
        attribution: `${opt.attribution} — ${OSM_ATTRIBUTION}`,
      },
    },
    layers: [
      // A neutral backdrop beneath the tiles: if tiles fail to load, the panel
      // shows this calm parchment (not black/void) with the route still drawn
      // on top (AC-3.3), rather than a blank hole.
      { id: 'backdrop', type: 'background', paint: { 'background-color': '#ece9e1' } },
      { id: 'basemap', type: 'raster', source: 'basemap' },
    ],
  }
}
