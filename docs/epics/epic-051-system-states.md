# Epic 051 — System states (WP-4: EmptyState, SystemBanner, UpdateChip)

**Status:** DONE ✅
**Phase:** 1 (look-and-feel layer; depends on WP-0, WP-1; parallel to WP-2/WP-3)
**Spec refs:** `docs/design-system/spec-v0.2.md` Part II.B (the composite
table's EmptyState/SystemBanner/Skeleton+UpdateChip rows), I.2 (the 4-tier
signal system), I.6 (motion + `prefers-reduced-motion`), I.7 (voice & content
templates), IV.3 (WP sequencing)

---

## Capability statement

Three new, standalone, tested, Storybook-documented composites now exist for
the three "past the happy path" states a source-or-silence app must speak
calmly about: **EmptyState** (nothing matched — search or filters, always
with one reset/loosen CTA), **SystemBanner** (a regional alert, a live-data
outage, or degraded personalization — tiered, never alarm-toned for
`unknown`), and **UpdateChip** (the quiet "Updating conditions…" pill that
replaces a cold-every-time skeleton on reload). All three consume WP-1's
`Text`/`Button`/`Icon` primitives, WP-6's `messages.ts` copy, and Contract A/B
(`vars`, `SystemBannerModel`, `ConditionTier`) — no new tokens, no contract
edits.

## Architectural context

**Builds on:** WP-0's frozen contracts (`theme.css.ts` Contract A,
`contracts.ts` Contract B) and WP-1's primitives (`Text`, `Button`, `Icon`,
the `tierGlyphs` map in `screens/glyphs.ts`) and WP-6's `copy/messages.ts`
state-message templates.

**Enables:** WP-7 (Assembly + audit) — wiring these three into `Home.tsx`
(replacing the inline `EmptyState`/`SavedEmptyState` functions and the
`feed-alert-banner`/`WarningBlock` pattern) and `PlannerProvider`'s
stale-while-revalidate repaint (Part III) is explicitly WP-7's job, not this
epic's.

**Does NOT include:**
- **No existing screen is restyled or rewired.** `Home.tsx`,
  `RecommendationCard.tsx`, `Detail.tsx`, `FeedConditions.tsx`,
  `ConditionStates.tsx`, `SkeletonCard.tsx` are all untouched — wiring these
  three composites into them is WP-7's job.
- **No token or contract changes.** `frontend/tokens/**`, `theme.css.ts`,
  `contracts.ts` are untouched (frozen, WP-0 owns them).
- **No `docs/epics/README.md` edit.** The PO owns the index; this epic's row
  is added at merge-desk time (WP-7), same convention epic-047/048
  documented for themselves.

---

## Stories

### S1 — `EmptyState`

**Given** "the search X has no clear reset" (states-gallery.html §4) and no
owned component exists for it (only an inline, ungeneralized `EmptyState`
function local to `Home.tsx`)
**When** `frontend/src/components/EmptyState/` is added
**Then** a headline + secondary + one reset/loosen `Button` renders for both
the search-no-match and filters-too-tight variants, sourced from
`messages.emptySearch`/`messages.emptyFilters`.

**AC-1.1:** Props are `{ headline, secondary, cta, onAction, className? }` —
the exact shape `messages.emptySearch`/`messages.emptyFilters` already
return (plus the callback), so a caller spreads the message function's
output directly with no adapter.
**AC-1.2:** Exactly one CTA (`Button` variant `primary`) — never a bare "x"
or a second action, matching the mock's "answers your 'no clear reset'"
framing.
**AC-1.3:** `role="status"` so assistive tech is told the result set changed,
mirroring the existing `state-note`/`role="status"` convention elsewhere in
the app.
**AC-1.4:** Unit tests (renders copy, CTA press + keyboard-activate, status
role, className forwarding, both message-function outputs rendered verbatim)
+ Storybook stories (`SearchNoMatch`, `FiltersTooTight`) sourced from the
real `messages.ts` functions; axe-clean (see Deviations — verified ad hoc,
not added to the standing gate).

### S2 — `SystemBanner`

**Given** `SystemBannerModel` (`kind`, `tier`, `message`) is frozen in
Contract B but has no renderer, and the existing `feed-alert-banner` +
`WarningBlock` pattern predates the 4-tier signal system
**When** `frontend/src/components/SystemBanner/` is added
**Then** `regional-alert`/`live-outage`/`personalization-degraded` all
render through one component, coloured by `tier` (`unknown` gray/calm,
`headsUp` amber, `blocked` terracotta — never red, never alarm-toned for a
non-event).

**AC-2.1:** Props are `SystemBannerModel` (`kind`, `tier`, `message`) plus an
additive, optional `secondary` line and `className` — not a divergent shape.
**AC-2.2:** Icon comes from WP-1's `tierGlyphs` map (`screens/glyphs.ts`) —
no second tier→glyph decision invented here.
**AC-2.3:** `unknown` renders with no coloured field (a plain hairline-bordered
box, muted ink) — deliberately distinct from `headsUp`/`blocked`'s soft
tinted field, so a down source never visually reads as an event (Law 6/7).
**AC-2.4:** The optional `secondary` line stays muted regardless of tier
(states-gallery.html §6) — only the message row carries the tier's accent.
**AC-2.5:** A visually-hidden tier cue ("Notice"/"Heads up"/"Blocked") rides
the `Icon`'s required `label`, so severity is never colour-only (design-
system-v0.1 §4.3, mirrored from `Signal`).
**AC-2.6:** `role="status"`, `data-banner-kind` carries `kind` for
callers/tests to target without a class-name dependency.
**AC-2.7:** Unit tests (message render, status role, tier cue text, per-tier
class assertions incl. a negative check that `unknown` never carries
`headsUp`/`blocked` classes, optional secondary line, `systemBannerMessages`
integration, className forwarding) + Storybook stories (one per kind/tier
pairing + an `AllTiers` gallery); axe-clean (ad hoc, see Deviations).

### S3 — `UpdateChip`

**Given** the reload fix (Part III) needs a quiet, always-testable
"Updating…" pill instead of the cold-every-time skeleton, and
`prefers-reduced-motion` must be honored the same way `SkeletonCard` already
does
**When** `frontend/src/components/UpdateChip/` is added
**Then** a small pill renders `messages.stalePaint()` by default with a
pulsing status dot, and the pulse animation is dropped entirely (not just
slowed) when reduced motion is preferred.

**AC-3.1:** `label` defaults to `messages.stalePaint()` ("Updating
conditions…") but is overridable (the two-phase "Checking current
conditions…" line reuses the same chip — Epic 040).
**AC-3.2:** Reduced motion is honored two ways: (a) JS-detected via
`data/motion.ts#prefersReducedMotion()`, mirroring `SkeletonCard`'s
testable-via-`matchMedia` pattern — the animating class is only applied when
motion is allowed; (b) a CSS `@media (prefers-reduced-motion: reduce)` guard
on the animation itself as a second line of defense, matching `Button.css.ts`'s
existing belt-and-suspenders convention.
**AC-3.3:** The dot is `aria-hidden` (decorative); the label text is what
assistive tech reads, inside a `role="status"` region.
**AC-3.4:** Deliberately uses `text.muted` (gray), not `signal.headsUp`
(amber) — despite the mock's demo swatch using amber for the pulse dot — a
routine background revalidate is not an actionable event, and reserving the
amber hue strictly for real heads-up facts keeps Law 7 intact (documented
below as a mock/spec resolution, not a defect).
**AC-3.5:** Unit tests (default + custom label, status role, aria-hidden
dot, pulse-class present/absent by `matchMedia`, no-`matchMedia` defensive
default, className forwarding) + Storybook stories (`Default`,
`CheckingConditions`); axe-clean (ad hoc, see Deviations).

### S4 — Barrel export + a consumed-copy fix

**Given** WP-7 needs to import the three new composites from the existing
`components` barrel, and `messages.emptyFilters`'s CTA/secondary shared one
param despite the mock using two different phrases in those two slots
**When** `frontend/src/components/index.ts` is extended and
`copy/messages.ts#emptyFilters` gains one parameter
**Then** the three composites are barrel-exported alongside the existing
ones, and `emptyFilters`'s CTA reads a value phrase ("Show trails up to 3
mi") independent of the secondary sentence's verb phrase ("Widen the
distance and 6 trails come back.") — matching states-gallery.html §4 exactly
instead of colliding the two into one string.

**AC-4.1:** `tsc --noEmit` clean; no existing import path or export removed
or renamed.
**AC-4.2:** `emptyFilters` gains a 5th `ctaValue` param, additive-only (zero
existing callers in the codebase at time of change — verified by grep before
editing); `voice.test.ts`'s banned-word lint stays green.

---

## Definition of Done
- [x] All ACs covered by at least one passing test.
- [x] `make check` (backend) unaffected — this epic is frontend-only.
- [x] Frontend `npm run tokens`, `npm run build`, `npm test`, `npm run
      test:a11y` green (638/638 unit tests, 20/20 standing a11y-gate stories,
      plus a deleted-before-commit ad hoc scratch axe run over all 9 new
      stories — see Deviations).
- [x] Targeted self-review; no CRITICALs found (see commit message for
      summary; documented deviations below).
- [ ] Epic row added to `docs/epics/README.md` — deliberately deferred; the
      PO owns the index, added at merge-desk time (WP-7), same convention as
      epic-047/048.
- [ ] Committed (this WP does not push or open a PR — the PO/merge-desk
      handles it, per the WP-4 kickoff instructions).

## Deviations from spec (documented, not blocking)

- **Axe verification for `EmptyState`/`SystemBanner`/`UpdateChip`.** Same
  precedent epic-048 (WP-1) set: the standing a11y gate
  (`src/test/a11y.axe.test.tsx`) is explicitly scoped, by its own header
  comment, to "safety-relevant honesty primitives"
  (Confidence/Signal/Staleness/ConditionStates/ContextRibbon). This epic did
  not add the three new composites to that file, to stay consistent with
  that established scoping decision rather than unilaterally widening it.
  Axe-cleanliness was instead verified via a temporary local harness
  mirroring the gate file's own `runAxe`/`composeStories` pattern against
  every story in all three components (9/9 stories passed with zero
  violations, `color-contrast` disabled per the gate's own jsdom rationale).
  The temporary harness was deleted before commit; it is not part of the
  shipped diff. A permanent, broader a11y gate across all v0.2 components is
  WP-7's "Assembly + WCAG/contrast audit" scope, not this epic's.
- **`SystemBanner`'s props are `SystemBannerModel` PLUS an optional
  `secondary`.** The frozen contract's `SystemBannerModel` carries a single
  `message: string` ("Calm, one sentence, constructive"). states-gallery.html
  §6 ("all live sources down") shows a fuller two-line treatment (status line
  + a muted detail line explaining what still works). Rather than either (a)
  dropping that second line entirely, which would lose real information the
  mock treats as load-bearing, or (b) editing the frozen contract to add a
  field, this epic added `secondary` as an ADDITIVE, optional prop on the
  component (not the model) — every field `SystemBannerModel` requires is
  still exactly satisfied; a caller passing only `{kind, tier, message}`
  gets a fully valid single-line banner.
- **`messages.emptyFilters` gains a 5th parameter (`ctaValue`).** Named
  explicitly as an anticipated, in-scope fix in the WP-4 kickoff brief ("You
  MAY minimally refine a messages.ts string you consume if it reads
  awkwardly (e.g. the emptyFilters CTA phrasing)"). Before the change, the
  function's `cta` template (`` `Show trails ${suggestedChange}` ``) and
  `secondary` template (`` `${suggestedChange} and ${suggestedTrailCount}
  trails come back.` ``) both consumed the SAME `suggestedChange` string,
  but states-gallery.html §4 uses two grammatically different phrases in
  those two slots ("Widen the distance" vs. "up to 3 mi") — satisfying both
  from one param necessarily produces a broken sentence in one slot or the
  other. Verified zero existing callers via `grep -rn "emptyFilters"` before
  changing the signature, so this is additive with no breakage. `S1`'s
  `EmptyState.test.tsx`/`.stories.tsx` exercise the corrected call shape.
- **`UpdateChip`'s pulse dot uses `text.muted`, not `signal.headsUp`
  (amber).** states-gallery.html's static demo CSS hardcodes the pulse dot's
  colour as the mock's `--amber` swatch. Per the spec's own governing rule
  ("When prose and mock disagree, the mock's intent wins; the spec's tokens
  win on exact values" and Law 7, "colour encodes actionability, not
  confidence"), a background cache revalidation is not an actionable
  heads-up fact, so binding it to `signal.headsUp` would spend the one
  reserved amber hue on a non-event and blur the boundary the 4-tier system
  exists to keep sharp. `text.muted` (calm gray) is used instead — the
  mock's *intent* (a small pulsing presence indicator) is preserved; its
  *exact token* is not, per the spec's own tie-break rule.
