/**
 * USGS National Map basemap layers (D2). All public-domain, license-clean, and
 * key-free. This module carries only metadata + tile templates — NO map library
 * import — so the always-loaded map chrome (the layer switch) can read it
 * without pulling MapLibre onto the page (the map lib stays in the lazy chunk).
 */
export type MapLayerKey = 'topo' | 'imagery' | 'hillshade'

export interface LayerOption {
  key: MapLayerKey
  label: string
  /** XYZ raster tile template. ArcGIS REST serves `{z}/{y}/{x}` order. */
  tiles: string
  /** Per-basemap credit, shown in addition to the persistent OSM/ODbL line. */
  attribution: string
  maxZoom: number
}

const USGS = 'https://basemap.nationalmap.gov/arcgis/rest/services'

export const LAYER_OPTIONS: LayerOption[] = [
  {
    key: 'topo',
    label: 'Topo',
    tiles: `${USGS}/USGSTopo/MapServer/tile/{z}/{y}/{x}`,
    attribution: 'USGS The National Map: Topo',
    maxZoom: 16,
  },
  {
    key: 'imagery',
    label: 'Imagery',
    tiles: `${USGS}/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}`,
    attribution: 'USGS The National Map: Orthoimagery',
    maxZoom: 16,
  },
  {
    key: 'hillshade',
    label: 'Hillshade',
    tiles: `${USGS}/USGSShadedReliefOnly/MapServer/tile/{z}/{y}/{x}`,
    attribution: 'USGS The National Map: 3DEP Shaded Relief',
    maxZoom: 16,
  },
]

export const layerByKey = (key: MapLayerKey): LayerOption =>
  LAYER_OPTIONS.find((opt) => opt.key === key) ?? LAYER_OPTIONS[0]

/** The persistent OSM/ODbL credit — the route geometry is OSM-derived (D7/T6). */
export const OSM_ATTRIBUTION = '© OpenStreetMap contributors (ODbL)'
