import {
  Bookmark,
  BookmarkCheck,
  CalendarClock,
  Car,
  Check,
  CircleHelp,
  CircleSlash,
  Clock,
  Download,
  Droplet,
  Gauge,
  History,
  Layers,
  LocateFixed,
  MapPin,
  Mountain,
  Navigation,
  Route,
  TriangleAlert,
  Users,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

import type { ConditionTier } from '../design/contracts'

/**
 * The DD2 glyph-semantics table, resolved to Lucide components — ONE meaning per
 * glyph across the whole surface (Epic 021). Naming the mapping here, once, is
 * what keeps the invariant enforceable: a fact and a facet never quietly reach
 * for the same glyph, and Drive (`car`) stays distinct from Duration (`clock`)
 * so the two never collapse onto a bare clock (AC-21.2.1).
 *
 * `check`, `triangle-alert`, and `layers` were reserved (unwired) at Epic 021
 * and are wired here (design-system-v0.2 I.5, WP-1): `check` stays reserved to
 * verified / checked-clear ONLY (never corroboration); `triangle-alert` is the
 * sole hazard glyph, shared by the `headsUp` and `blocked` tiers — severity is
 * read from colour + copy, not a second glyph (Law 7); `layers` is the map
 * corroboration cue (MapControls, WP-3).
 */
export const glyphs = {
  // Decision facts
  drive: Car,
  distance: Route,
  ascent: Mountain,
  duration: Clock,
  // Trail fact (Epic 041): a MAPPED water source — never streamflow (the live
  // condition kind confusingly also named "water"), never a potability cue.
  water: Droplet,
  // Actions
  save: Bookmark,
  saved: BookmarkCheck,
  directions: Navigation,
  download: Download,
  // Silence state (Epic 020) — stale-degraded ONLY, never the hazard glyph.
  history: History,
  // Tuning facets
  when: CalendarClock,
  from: MapPin,
  party: Users,
  effort: Gauge,
  nearMe: LocateFixed,
  // Reserved glyphs, wired at design-system-v0.2 WP-1 (I.5).
  check: Check,
  'triangle-alert': TriangleAlert,
  layers: Layers,
} as const

/**
 * The 4-tier signal system's glyph mapping (design-system-v0.2 I.5, D1):
 * `unknown -> CircleHelp`, `headsUp -> TriangleAlert`, `blocked -> CircleSlash`.
 * `clear` is deliberately absent — it renders nothing (Law 1, `ConditionTier`
 * in `design/contracts.ts`). WP-2's ConditionStatus engine and WP-3's
 * EvidencePanel are the intended callers, so the tier -> glyph decision has
 * exactly one home instead of each re-deriving it.
 */
export const tierGlyphs: Record<Exclude<ConditionTier, 'clear'>, LucideIcon> = {
  unknown: CircleHelp,
  headsUp: TriangleAlert,
  blocked: CircleSlash,
}
