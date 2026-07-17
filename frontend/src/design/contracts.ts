/**
 * FROZEN CONTRACT (WP-0). Changes go through the merge desk.
 *
 * Contract B — component APIs (design-system-v0.2.md Part IV.1). The shared,
 * stable prop/data-shape types WP-2..WP-7 code against in isolated worktrees,
 * so parallel component work forks with zero merge conflict. Sits alongside
 * Contract A (`theme.css.ts`, the token contract).
 *
 * Types here ALIAS or narrow the existing `vm.ts` view-model shapes where
 * they already fit — this file is not a second, divergent source of truth
 * for data the backend/mock adapters already produce (`CardVM`, `LineVM`,
 * `ConditionStatusVM`, …). It only adds the v0.2 *presentation* vocabulary —
 * severity tiers, evidence rows, banners — that `vm.ts` (a wire/mock-shape
 * mirror) has no reason to know about.
 */
import type { CardVM, ConditionStateVM, ConditionStatusVM, LineVM, Provenance } from '../data/vm'

// ---- The 4-tier signal system (design-system-v0.2 D1, I.2) ---------------

/**
 * The rendered severity tier. `clear` renders NOTHING (Law 1 — silence is a
 * state); the other three bind `vars.signal.{unknown,headsUp,blocked}` from
 * Contract A. Never a 5th tier, never a raw color — color encodes
 * actionability, not confidence (Law 7): `unknown` is gray, never red.
 */
export type ConditionTier = 'clear' | 'unknown' | 'headsUp' | 'blocked'

/**
 * The six wire/VM coverage states a condition kind can be in — `vm.ts`'s
 * `ConditionStateVM`, the shape `screens/ConditionStates.tsx` already
 * renders. Re-exported under the v0.2 name so WP-2/WP-3 read one vocabulary
 * for "what the backend said" (coverage) vs. "how we render it" (tier).
 */
export type ConditionCoverage = ConditionStateVM

/**
 * The coverage -> tier mapping WP-2 implements (the ConditionStatus engine,
 * design-system-v0.2.md II.B): a pure function, the SINGLE source of the
 * tier/color decision. Signature only here — frozen so WP-2's Home/Detail
 * callers and WP-3's EvidencePanel can both import the TYPE before the
 * implementation exists, and so no second copy of this decision can drift
 * in downstream.
 *
 *   no-hazard                                     -> clear    (silent)
 *   present (actionable, kind- and value-specific) -> headsUp | blocked
 *   stale-degraded | no-data | unavailable |
 *     not-fetched                                  -> unknown  (gray, never red)
 *
 * `present`'s split into headsUp vs. blocked is kind- and value-specific (a
 * closure is `blocked`; high water/heat/permit is `headsUp`) — WP-2 owns
 * that judgment; this signature only fixes the function's shape so every
 * caller agrees on it.
 */
export type ConditionTierMapper = (status: ConditionStatusVM) => ConditionTier

// ---- TrailCard (design-system-v0.2 II.B) ----------------------------------

/**
 * The restyled TrailCard's render model: name leads, status silent when
 * `clear`, one action zone (tap-card-opens-Detail — no separate "OPEN
 * DETAIL"), no per-card weather (an area fact belongs at area level, Law 3),
 * mono metrics. Aliases `CardVM` (the existing view-model every screen
 * already consumes) and adds the one derived field the restyle needs: each
 * condition's rendered tier, precomputed by a `ConditionTierMapper` so the
 * card component itself never re-derives severity.
 */
export interface TrailCardModel extends CardVM {
  /** `conditions` (VM coverage) paired 1:1 with its mapped tier. */
  conditionTiers: { kind: string; tier: ConditionTier }[]
}

// ---- EvidencePanel (design-system-v0.2 II.B) -------------------------------

/**
 * One disclosed, sourced row inside the EvidencePanel's `<details>`
 * (progressive disclosure: a conclusion line up top, every source still one
 * tap away — Rule #1/#2, Law 2, "keep the receipt"). Picks the provenance
 * fields straight off `LineVM` rather than inventing a parallel shape;
 * `body`/`kind`/`tier` are the v0.2-only additions.
 */
export interface EvidenceItem extends Pick<LineVM, 'source' | 'age' | 'confidence' | 'provenance' | 'sources'> {
  /** The condition kind this row answers, e.g. "weather" | "water" | "closures". */
  kind: string
  tier: ConditionTier
  /** The stated/hedged fact alone (Epic 046 S1's `body`) — no source/age welded in. */
  body: string
}

// ---- SystemBanner (design-system-v0.2 II.B) --------------------------------

export type SystemBannerKind = 'regional-alert' | 'live-outage' | 'personalization-degraded'

/**
 * Regional alert / live-outage / personalization-degraded — calm, one
 * sentence, constructive (Law 6, I.7 voice rules). Tiered color like
 * everything else; `clear` is never valid here — a banner only exists to
 * disclose something, so it always carries at least `unknown`.
 */
export interface SystemBannerModel {
  kind: SystemBannerKind
  tier: Exclude<ConditionTier, 'clear'>
  /** Conclusion-first, <=1 sentence, names the one thing + the one next step (I.7). */
  message: string
}

// ---- Condition chips (frame-conditions-wave §3, Q3/Q5/Q9) ------------------

/**
 * The scannable strip's per-chip render state (frame-conditions-wave Q3/Q9).
 * Orthogonal to `ConditionTier`: `state` says how the READING renders
 * (skeleton / value / dashed), `tier` says whether a WARNING tints it
 * (Q5 — amber headsUp / terracotta blocked; `clear` = neutral).
 *
 * - `pending`     — phase 2 in flight: skeleton shimmer, muted placeholder.
 * - `fresh`       — a sourced value within its per-kind horizon.
 * - `stale`       — past its horizon: dashed border, muted value, clock + age
 *                   in GRAY (staleness is unknown-family; it spends no alarm
 *                   color — Law 7).
 * - `unavailable` — probed, no source answered: dashed border, italic "—".
 */
export type ChipState = 'pending' | 'fresh' | 'stale' | 'unavailable'

/** One glyph+value chip in the conditions strip (This-feed card + Detail). */
export interface ConditionChipModel {
  /** Condition kind: "weather" | "air" | "fire" | "water" | "closures" | "permits". */
  kind: string
  /** The mono value text ("68°F", "AQI 54", "closed", "—"). */
  valueText: string
  state: ChipState
  /** Warning tint (Q5/Q7): max severity of this kind's warnings; 'clear' = neutral. */
  tier: ConditionTier
  /** Humanised age, shown only when `state === 'stale'`. */
  ageText?: string
  /** The tap-to-reveal receipt (Q6) — present only where a sourced reading exists. */
  receipt?: ReceiptModel
}

/**
 * The one quiet receipt line below the Detail strip (Q6): revealed by tapping
 * a chip, swapped on each tap, collapsed by default. Never a popover.
 */
export interface ReceiptModel {
  source: string
  /** Humanised relative age — never a raw datetime (§7.2). */
  ageText?: string
  /** e.g. "single source" | "2 sources agree" — corroboration in plain words. */
  confidenceText?: string
}

// Re-exported so WP-2/WP-3 have one import for the provenance vocabulary
// alongside the tier/coverage/model types above, without reaching into vm.ts
// directly for it.
export type { Provenance }
