/**
 * The Detail elevation profile (S5b): distance × elevation, with total gain /
 * loss / max grade labelled in text that doubles as the accessibility fallback
 * (E). It is an accessible slider — keyboard arrows and pointer drag scrub a
 * cursor that the parent keeps in sync with a marker on the route (AC-5.3). No
 * map library; plain SVG.
 */
import {
  useId,
  useRef,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react'

import { elevationAtFraction, metersToFeet, metersToMiles } from '../../data/geo'
import type { ElevationProfile as ElevationProfileData } from '../../data/vm'
import { fractionToX, profilePolyline, profileScale, xToFraction, type Box } from './svg'

const BOX: Box = { width: 320, height: 132, padX: 8, padY: 12 }
const KEY_STEP = 0.02

const feet = (m: number): string => `${Math.round(metersToFeet(m)).toLocaleString()} ft`
const miles = (m: number): string => `${metersToMiles(m).toFixed(1)} mi`
// One decimal (F6, ux-review-conditions 2026-07): the backend's grade is a raw
// float off a 10m DEM slope calc — displaying it verbatim reads as fourteen
// decimals of precision the estimate never had (`max 20.35806406360465%`).
const grade = (pct: number): string => `${pct.toFixed(1)}%`

export interface ElevationProfileProps {
  profile: ElevationProfileData
  cursorFraction: number | null
  onScrub: (fraction: number | null) => void
}

export function ElevationProfile({ profile, cursorFraction, onScrub }: ElevationProfileProps) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const labelId = useId()
  const scale = profileScale(profile.samples, BOX)
  const polyline = profilePolyline(profile.samples, BOX)
  const area = `${polyline} ${scale.x(scale.maxD)},${scale.bottom} ${scale.x(0)},${scale.bottom}`

  const summary = `Climbs ${feet(profile.totalGainMeters)}, descends ${feet(
    profile.totalLossMeters,
  )}, steepest grade ${grade(profile.maxGradePercent)}.`

  const cursorElev = cursorFraction != null ? elevationAtFraction(profile, cursorFraction) : null
  const cursorX = cursorFraction != null ? fractionToX(cursorFraction, BOX) : null
  const cursorDistM = cursorFraction != null ? cursorFraction * scale.maxD : null
  const valueText =
    cursorFraction != null && cursorElev != null
      ? `${miles(cursorDistM ?? 0)}, ${feet(cursorElev)}`
      : summary

  const scrubToClientX = (clientX: number) => {
    const rect = wrapRef.current?.getBoundingClientRect()
    if (!rect || rect.width === 0) return
    const x = ((clientX - rect.left) / rect.width) * BOX.width
    onScrub(xToFraction(x, BOX))
  }

  const onPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId)
    scrubToClientX(event.clientX)
  }
  const onPointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) scrubToClientX(event.clientX)
  }

  const onKeyDown = (event: ReactKeyboardEvent) => {
    const current = cursorFraction ?? 0
    let next: number | null = null
    if (event.key === 'ArrowRight' || event.key === 'ArrowUp') next = Math.min(1, current + KEY_STEP)
    else if (event.key === 'ArrowLeft' || event.key === 'ArrowDown') next = Math.max(0, current - KEY_STEP)
    else if (event.key === 'Home') next = 0
    else if (event.key === 'End') next = 1
    else if (event.key === 'Escape') {
      onScrub(null)
      return
    } else return
    event.preventDefault()
    onScrub(next)
  }

  return (
    <figure className="elev">
      <figcaption className="elev-summary">
        <span id={labelId} className="elev-summary-label">
          Elevation
        </span>
        <span className="elev-stats">
          <span>↑ {feet(profile.totalGainMeters)}</span>
          <span>↓ {feet(profile.totalLossMeters)}</span>
          <span>max {grade(profile.maxGradePercent)}</span>
        </span>
      </figcaption>

      {/* The slider semantics live on this host element, not the SVG (inline-SVG
          ARIA widget roles are exposed unreliably by some AT); the SVG is purely
          presentational, and the sr-only summary below is the text equivalent. */}
      <div
        ref={wrapRef}
        className="elev-chart-wrap"
        role="slider"
        tabIndex={0}
        aria-labelledby={labelId}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round((cursorFraction ?? 0) * 100)}
        aria-valuetext={valueText}
        onKeyDown={onKeyDown}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
      >
        <svg
          className="elev-chart"
          viewBox={`0 0 ${BOX.width} ${BOX.height}`}
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <line x1={0} y1={scale.bottom} x2={BOX.width} y2={scale.bottom} className="elev-base" />
          <polygon points={area} className="elev-fill" />
          <polyline points={polyline} className="elev-line" />
          {cursorX != null ? (
            <g className="elev-cursor">
              <line x1={cursorX} y1={BOX.padY ?? 0} x2={cursorX} y2={scale.bottom} className="elev-cursor-line" />
              {cursorElev != null ? (
                <circle cx={cursorX} cy={scale.y(cursorElev)} r={4} className="elev-cursor-dot" />
              ) : null}
            </g>
          ) : null}
        </svg>
      </div>

      <p className="elev-readout" aria-hidden="true">
        {cursorFraction != null && cursorElev != null ? (
          <>
            {miles(cursorDistM ?? 0)} · {feet(cursorElev)}
          </>
        ) : (
          <span className="elev-source">{profile.source}</span>
        )}
      </p>

      {/* The always-present text equivalent of the chart (E / a11y). */}
      <p className="sr-only">{summary}</p>
    </figure>
  )
}
