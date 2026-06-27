import type { ElevationProfile } from '../../data/vm'
import { profilePolyline } from './svg'

/**
 * Static at-rest elevation sparkline (S4) — the "shape of the day" read at a
 * glance, derived from the real 3DEP profile. NO map library on the feed path
 * (D6): this is plain SVG. Decorative (`aria-hidden`); the card's ascent figure
 * is the text equivalent. A card with no profile renders no glyph (AC-4.2) —
 * never a faked curve.
 */
const GLYPH_BOX = { width: 288, height: 46, padY: 3 }

export function ElevationGlyph({ profile }: { profile: ElevationProfile }) {
  const points = profilePolyline(profile.samples, GLYPH_BOX)
  if (!points) return null
  return (
    <svg className="glyph" viewBox="0 0 288 46" preserveAspectRatio="none" aria-hidden="true">
      <line x1="0" y1="45" x2="288" y2="45" className="glyph-base" />
      <polyline points={points} className="glyph-line" />
    </svg>
  )
}
