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

/**
 * The relief every card's glyph is scaled against (H3, ux-review-craft
 * 2026-07): auto-ranging each profile to its OWN min/max — the prior
 * behaviour — draws 13 ft of dune with the same full-frame drama as 278 ft of
 * ridge, so the glyph reads as decoration, not data. A shared reference lets
 * relief stay comparable across every card in the feed: a trail's amplitude is
 * proportional to `min(1, its own relief / this reference)`, so two cards are
 * honestly comparable — flatter really does draw flatter. ~1,000 ft (a
 * substantial day-hike climb) sits above nearly all corpus profiles, so
 * clipping (a climb maxing out the frame) is the rare case, not the norm.
 */
const REFERENCE_RELIEF_METERS = 305

export function ElevationGlyph({ profile }: { profile: ElevationProfile }) {
  const points = profilePolyline(profile.samples, GLYPH_BOX, REFERENCE_RELIEF_METERS)
  if (!points) return null
  return (
    <svg className="glyph" viewBox="0 0 288 46" preserveAspectRatio="none" aria-hidden="true">
      <line x1="0" y1="45" x2="288" y2="45" className="glyph-base" />
      <polyline points={points} className="glyph-line" />
    </svg>
  )
}
