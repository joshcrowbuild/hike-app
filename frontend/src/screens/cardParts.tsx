/** Small presentational pieces shared by the card and the detail screen. Each
 *  is typed against the view-model, not the legacy Trail. */

export function DecisionItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="decision-item">
      <span className="decision-label">{label}</span>
      <span className="decision-value">{value}</span>
    </div>
  )
}

/** Compact at-rest elevation sparkline — the "shape of the day" (v0.3 §3). */
export function TerrainGlyph({ profilePath }: { profilePath: number[] }) {
  const points = profilePath.map((value, index) => `${index * 36},${44 - value * 0.42}`).join(' ')
  return (
    <svg className="glyph" viewBox="0 0 288 46" preserveAspectRatio="none" aria-hidden="true">
      <line x1="0" y1="45" x2="288" y2="45" className="glyph-base" />
      <polyline points={points} className="glyph-line" />
    </svg>
  )
}

/** Fuller terrain / profile preview for the detail screen. */
export function TerrainPreview({
  values,
  label,
}: {
  values: number[]
  label: string
}) {
  const points = values.map((value, index) => `${12 + index * 34},${96 - value}`).join(' ')
  return (
    <div className="terrain-preview">
      <div className="terrain-preview__label">{label}</div>
      <svg viewBox="0 0 320 120" aria-hidden="true">
        {[24, 48, 72, 96].map((line) => (
          <path
            key={line}
            d={`M 0 ${line} C 44 ${line - 7}, 94 ${line + 4}, 160 ${line - 3} S 250 ${line + 7}, 320 ${line - 1}`}
            className="terrain-contour"
          />
        ))}
        <polyline points={points} className="terrain-path" />
      </svg>
    </div>
  )
}

export const formatDrive = (minutes: number): string => `${minutes} min`
export const formatTrail = (miles: number, ascentFeet: number): string =>
  `${miles.toFixed(1)} mi · ${ascentFeet.toLocaleString()} ft`
