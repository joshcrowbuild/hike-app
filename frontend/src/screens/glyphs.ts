import {
  Bookmark,
  BookmarkCheck,
  CalendarClock,
  Car,
  Clock,
  Gauge,
  LocateFixed,
  MapPin,
  Mountain,
  Navigation,
  Route,
  Users,
} from 'lucide-react'

/**
 * The DD2 glyph-semantics table, resolved to Lucide components — ONE meaning per
 * glyph across the whole surface (Epic 021). Naming the mapping here, once, is
 * what keeps the invariant enforceable: a fact and a facet never quietly reach
 * for the same glyph, and Drive (`car`) stays distinct from Duration (`clock`)
 * so the two never collapse onto a bare clock (AC-21.2.1).
 *
 * Deliberately absent: `check` (reserved to verified / checked-clear ONLY —
 * never corroboration) and `triangle-alert` (the sole hazard glyph) and
 * `layers` (reserved for the corroboration cue) — none are wired in this epic.
 */
export const glyphs = {
  // Decision facts
  drive: Car,
  distance: Route,
  ascent: Mountain,
  duration: Clock,
  // Actions
  save: Bookmark,
  saved: BookmarkCheck,
  directions: Navigation,
  // Tuning facets
  when: CalendarClock,
  from: MapPin,
  party: Users,
  effort: Gauge,
  nearMe: LocateFixed,
} as const
