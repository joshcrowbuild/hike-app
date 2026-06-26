/**
 * The map control cluster (S6): base-layer switch, fullscreen, locate-me, and a
 * directions-to-trailhead deep link. All controls are React-Aria primitives —
 * real buttons/links, labelled, keyboard-operable, with text (not icon-only)
 * affordances. Rendered in the always-loaded chrome (no map library here), so
 * the controls work and are testable whether the GL map or the static fallback
 * is mounted.
 */
import { Button, ToggleButton } from 'react-aria-components'

import { LAYER_OPTIONS, type MapLayerKey } from './layers'

export interface MapControlsProps {
  layer: MapLayerKey
  onLayerChange: (key: MapLayerKey) => void
  fullscreen: boolean
  onToggleFullscreen: () => void
  onLocate: () => void
  locating: boolean
  directionsUrl: string
}

export function MapControls({
  layer,
  onLayerChange,
  fullscreen,
  onToggleFullscreen,
  onLocate,
  locating,
  directionsUrl,
}: MapControlsProps) {
  return (
    <div className="map-controls">
      <div className="map-layers" role="group" aria-label="Base map layer">
        {LAYER_OPTIONS.map((opt) => (
          <ToggleButton
            key={opt.key}
            className="map-chip"
            isSelected={layer === opt.key}
            onChange={() => onLayerChange(opt.key)}
          >
            {opt.label}
          </ToggleButton>
        ))}
      </div>

      <div className="map-actions">
        <Button className="map-chip" onPress={onLocate} isDisabled={locating}>
          {locating ? 'Locating…' : 'Locate me'}
        </Button>
        <ToggleButton className="map-chip" isSelected={fullscreen} onChange={onToggleFullscreen}>
          {fullscreen ? 'Exit fullscreen' : 'Fullscreen'}
        </ToggleButton>
        <a className="map-chip map-chip--link" href={directionsUrl} target="_blank" rel="noreferrer">
          Directions
        </a>
      </div>
    </div>
  )
}
