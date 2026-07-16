/**
 * State-message templates (WP-6 / Epic 053).
 *
 * One function/const per system state, following design-system-v0.2.md §I.7:
 * conclusion-first, ≤1 sentence, names the one thing + the one next step.
 * Never use banned-builder nouns (see voice.test.ts baseline).
 *
 * Each message is sourced from mocks (docs/design-system/mocks/states-gallery.html)
 * and design-system-v0.2.md.
 */
import type { ConditionTier, SystemBannerKind } from '../design/contracts'

// ---- State messages (one per state) ----

/**
 * Clear state — renders nothing.
 * (Law 1: Silence is a state — a clean result shows nothing.)
 */
export const clear = () => undefined

/**
 * Heads-up state — actionable but not blocking (heat, permit, high flow).
 * Example: "Heat advisory today — start before 10am."
 */
export const headsUp = (detail: string): string => detail

/**
 * Blocked state — a genuine barrier (closure, mandatory permit).
 * Example: "Closed — footbridge out (NPS, checked 4m ago)."
 */
export const blocked = (detail: string): string => detail

/**
 * Unknown state — a source is down / not fetched (gray, calm).
 * Example: "Air-quality data is unavailable right now — everything else checked out."
 */
export const unknown = (sourceName: string): string =>
  `${sourceName} is unavailable right now — everything else checked out.`

/**
 * Empty search state — no trails match the search term.
 * Returns an object with the headline and a secondary explanation.
 */
export const emptySearch = (
  searchTerm: string,
  placeLabel: string,
  trailCount: number
): { headline: string; secondary: string; cta: string } => ({
  headline: `No trails named "${searchTerm}" near here.`,
  secondary: `Check the spelling, or browse the ${trailCount} picks for ${placeLabel}.`,
  cta: 'Clear search & browse',
})

/**
 * Empty filters state — filters are too tight, no trails match.
 * Returns an object with the headline, secondary, and an actionable CTA.
 *
 * `suggestedChange` and `ctaValue` are deliberately separate params
 * (states-gallery.html §4 "filters — too tight"): the secondary sentence
 * reads a verb phrase ("Widen the distance and 6 trails come back."), while
 * the CTA button reads the resulting value ("Show trails up to 3 mi") — the
 * same string would read wrong in one slot or the other if collapsed to one
 * param (WP-4 deviation — see epic-051's Deviations section).
 */
export const emptyFilters = (
  filterDescription: string,
  placeLabel: string,
  suggestedChange: string,
  suggestedTrailCount: number,
  ctaValue: string
): { headline: string; secondary: string; cta: string } => ({
  headline: `Nothing matches ${filterDescription} here.`,
  secondary: `${suggestedChange} and ${suggestedTrailCount} trails come back.`,
  cta: `Show trails ${ctaValue}`,
})

/**
 * Personalization degraded — signed in but personalization load failed.
 * Returns an object with the headline and secondary explanation.
 */
export const personalizationDegraded = (): {
  headline: string
  secondary: string
  cta: string
} => ({
  headline: 'Showing general picks for now.',
  secondary:
    "We couldn't reach your saved preferences just now, so these aren't tuned to you yet. Retry",
  cta: 'Retry',
})

/**
 * Live outage state — all live condition sources are down.
 * Returns an object with the banner message and a secondary explanation.
 */
export const liveOutage = (): { message: string; secondary: string } => ({
  message: 'Live conditions are unavailable right now.',
  secondary:
    "Trails, distances and terrain still work — these just aren't condition-checked. We'll re-check automatically.",
})

/**
 * Stale paint state — rendering the cached feed after revalidation begins.
 * Used with the "Updating conditions…" chip during background revalidation.
 */
export const stalePaint = (): string => 'Updating conditions…'

// ---- System banner messages (typed by kind) ----

/**
 * Messages for SystemBanner by kind (design-system-v0.2.md §II.B).
 * Use with the appropriate banner kind to render a tiered, conclusion-first message.
 */
export const systemBannerMessages: Record<
  SystemBannerKind,
  (tier: Exclude<ConditionTier, 'clear'>) => string
> = {
  'regional-alert': (tier) =>
    tier === 'blocked'
      ? 'Regional closure — check before you go.'
      : 'Regional alert — read the details.',
  'live-outage': () => 'Live conditions are unavailable right now.',
  'personalization-degraded': () =>
    "We couldn't reach your saved preferences. Showing general picks.",
}
