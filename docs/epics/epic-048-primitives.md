# Epic 048 — Primitives (WP-1: Text, Button, Icon glyphs, MetricRow)

**Status:** DONE ✅
**Phase:** 1 (look-and-feel layer; depends on WP-0, blocks WP-2..4)
**Spec refs:** `docs/design-system/spec-v0.2.md` Part II.A (the primitive
table), I.3 (the type-role scale), I.5 (iconography), IV.3 (WP sequencing)

---

## Capability statement

The v0.2 type-role scale, the owned interactive `Button`, and the honest
distance/ascent/duration `MetricRow` now exist as first-class, tested,
Storybook-documented primitives bound only to Contract A (`vars`) — where
before there was a half-migrated Epic-019 scale (raw-rem classes still
lingering), no owned `Button` (each call site hand-rolled its own
hover/press/focus treatment), and a `DecisionFacts`/`DecisionItem` pair that
predates the mono/tabular-nums metric role. The three reserved `Icon` glyphs
(`check`, `triangle-alert`, `layers`) and the 4-tier signal -> glyph map are
also wired, unblocking WP-2's ConditionStatus engine and WP-3's
EvidencePanel/MapControls.

## Architectural context

**Builds on:** WP-0's frozen contracts — Contract A (`frontend/src/design/
theme.css.ts`, the `vars` token surface) and Contract B (`frontend/src/design/
contracts.ts`, incl. `ConditionTier`). Every new component binds `vars` only;
no raw hex/size anywhere in this epic's files.

**Enables:** WP-2 (ConditionStatus engine + TrailCard restyle — consumes
`Text`, `tierGlyphs`), WP-3 (Detail/EvidencePanel/MapControls — consumes
`Text`, the `layers` glyph), WP-4 (EmptyState/SystemBanner — consumes `Text`,
`Button`).

**Does NOT include:**
- **No existing component is restyled or rewired.** `cardParts.tsx`
  (`DecisionFacts`/`DecisionItem`), `RecommendationCard.tsx`, `Detail.tsx`,
  `FeedConditions.tsx`, `ConditionStates.tsx` are all untouched — wiring the
  new primitives into them is WP-2/WP-3/WP-4's job, not this epic's. This
  epic's `MetricRow` is a NEW, standalone primitive (generic `MetricItem[]`
  API) alongside the existing `DecisionFacts`, not a replacement for it yet.
- **No token or contract changes.** `frontend/tokens/**`, `theme.css.ts`,
  `contracts.ts` are untouched (frozen, WP-0 owns them).
- **No `docs/epics/README.md` edit.** The PO owns the index; this epic's row
  is added at merge-desk time (WP-7), same convention epic-047 documented for
  itself.

---

## Stories

### S1 — `Text` (the missing v0.2 type-role primitive)

**Given** the v0.2 role scale is tokenized in Contract A but no component
applies it
**When** `frontend/src/components/Text/` is added
**Then** `<Text role="title" as="h3">` applies size + lineHeight + weight +
family (+ case for `overline`) from ONE place, for all 9 roles.

**AC-1.1:** All 9 roles (`display/title/lead/body/bodySm/metric/metricLabel/
caption/overline`) are supported; `metric` alone binds `vars.type.metric.
family` (mono) + `fontVariantNumeric: tabular-nums`; `overline` alone sets
`textTransform: uppercase` (+ `letterSpacing: 0.06em`, a documented raw-value
exemption, same class as the `a11y.css.ts` sr-only recipe — no `letterSpacing`
token exists in Contract A).
**AC-1.2:** `Text` sets no colour — typography only (size/lineHeight/weight/
family/case), so a caller's own ink token (`vars.text.*`/`vars.signal.*`)
still applies without being fought.
**AC-1.3:** `as` overrides the per-role default element (`display`->`h1`,
`title`->`h3`, `lead`/`body`/`bodySm`->`p`, the rest->`span`); rest props
(e.g. `aria-hidden`) forward to the rendered tag.
**AC-1.4:** Unit test + Storybook story per role + an `AllRoles` gallery
story; axe-clean (verified ad hoc against a temporary local test harness
mirroring `src/test/a11y.axe.test.tsx` — see Deviations).

### S2 — `Button`

**Given** hover/press/focus/disabled treatment for interactive controls is
currently hand-rolled per call site (`.action-chip`, `.text-action` in
`styles.css`)
**When** `frontend/src/components/Button/` is added, built on React Aria's
`Button`
**Then** `primary`/`secondary`/`ghost` x `sm`/`md` all share one state
machine (`data-hovered`/`data-pressed`/`data-focus-visible`/`data-disabled`).

**AC-2.1:** Three variants (`primary` filled-ink, `secondary` outlined,
`ghost` bare) x two sizes (`sm`/`md`); every value bound to `vars`.
**AC-2.2:** Keyboard-focus ring binds `vars.focus.ring` via the shared
`focusRing` recipe (`a11y.css.ts`), same as `Toggle`/`OptionGroup`.
**AC-2.3:** Minimum 44px hit target via an invisible centered `::before`
extension — the same pattern `styles.css`'s "44px minimum hit area" (Epic
020, AC-20.1.1) already established for `.action-chip`/`.text-action`, not a
new one. `44px` is a documented raw-constant exemption (a fixed platform a11y
minimum, not a design choice).
**AC-2.4:** Sentence case only — no `textTransform`, unlike the legacy
`.action-chip`'s mono-uppercase treatment (Law 5).
**AC-2.5:** `isDisabled` flattens each variant onto a muted token
combination (never a raw `opacity` fade) and refuses `onPress`.
**AC-2.6:** Unit tests (press/keyboard-activate/disabled/variant+size
classes) + Storybook story per variant/size/disabled state + an
all-combinations gallery story; axe-clean.

### S3 — `MetricRow`

**Given** distance/ascent/duration need the v0.2 mono/tabular-nums metric
role, and a missing value must never render a bare "—"
**When** `frontend/src/components/MetricRow/` is added
**Then** each `MetricItem` renders its value in `type.metric` (mono, tabular-
nums) and its label in `type.metricLabel` (sentence, muted), and a missing
value renders a NAMED disclosure per kind ("distance unavailable" / "ascent
unavailable" / "time unavailable") instead of a dash.

**AC-3.1:** Generic `items: MetricItem[]` API (`kind: 'distance'|'ascent'|
'duration'`, `label`, `value?: string | null`, `glyph?: LucideIcon`) — a
standalone primitive, not yet wired into `CardVM`/`DecisionFacts` (WP-2's
job).
**AC-3.2:** `null`/`undefined`/`''` value all trigger the named-disclosure
path; the disclosure text is keyed by `kind` (not derived from the caller's
`label` string), so copy stays exact regardless of label phrasing.
**AC-3.3:** An `Icon`-carrying item hides its visible label from assistive
tech (`aria-hidden`) so the fact announces once, not twice — mirrors
`cardParts.tsx#DecisionItem`'s existing convention.
**AC-3.4:** Renders `null` for an empty `items` array (no trail-shaped row to
disclose a gap in), mirroring `DecisionFacts`'s existing rule.
**AC-3.5:** Unit tests (named-disclosure per kind, empty-list, double-
announce guard, role=list/listitem semantics) + Storybook stories (full /
partially-unavailable / no-glyphs / empty); axe-clean.

### S4 — Reserved `Icon` glyphs + the tier -> glyph map

**Given** `check`/`triangle-alert`/`layers` were deliberately left unwired at
Epic 021, and the 4-tier signal system (Contract B's `ConditionTier`) has no
glyph mapping yet
**When** `frontend/src/screens/glyphs.ts` is extended
**Then** all three reserved glyphs resolve to Lucide components, and a new
`tierGlyphs` export maps `unknown -> CircleHelp`, `headsUp -> TriangleAlert`,
`blocked -> CircleSlash` (`clear` absent — Law 1, renders nothing).

**AC-4.1:** No existing glyph key's meaning changes; `check`/`triangle-alert`/
`layers` are additive only.
**AC-4.2:** `tierGlyphs` is typed `Record<Exclude<ConditionTier, 'clear'>,
LucideIcon>`, importing `ConditionTier` from the frozen `contracts.ts` (read
only — the type is imported, not redefined).

### S5 — Barrel exports

**Given** WP-2..4 need to import the new primitives from the existing
`components` barrel
**When** `frontend/src/components/index.ts` is extended
**Then** `Text`/`Button`/`MetricRow` (+ their prop/type exports) are
re-exported alongside the existing primitives, with no existing export
removed or renamed.

**AC-5.1:** `tsc --noEmit` clean; no existing import path changes.

---

## Definition of Done
- [x] All ACs covered by at least one passing test.
- [x] `make check` (backend) unaffected — this epic is frontend-only.
- [x] Frontend `npm run tokens`, `npm run build`, `npm test`, `npm run
      test:a11y` green.
- [x] Targeted self-review; no CRITICALs found (see commit message for
      summary; documented deviations below).
- [ ] Epic row added to `docs/epics/README.md` — deliberately deferred; the
      PO owns the index (WP-1 kickoff constraint), added at merge-desk time.
- [ ] Committed (this WP does not push or open a PR — the PO/merge-desk
      handles it, per WP-1 kickoff instructions).

## Deviations from spec (documented, not blocking)

- **`MetricRow`'s file location and API.** Spec Part II.A's component table
  lists `MetricRow` as the EXISTING `cardParts.tsx#DecisionFacts`,
  "re-token to `type.metric`/`type.metric-label`." The WP-1 kickoff brief
  instead directed a NEW, standalone `frontend/src/components/MetricRow/`
  with a generic `MetricItem[]` API, explicitly excluding `cardParts.tsx`
  from this epic's touched files. Both `DecisionFacts` (unre-tokened) and the
  new `MetricRow` (re-tokened, unused) now exist side by side; reconciling
  them — either by re-pointing `DecisionFacts` at the new primitive or
  retiring one — is left to WP-2 (TrailCard restyle), which already owns
  `cardParts.tsx`/`RecommendationCard.tsx`.
- **`Icon`'s row in the spec table** ("Wire `check`/`triangle-alert`/
  `layers`; add tier->glyph map. No API change.") is satisfied entirely
  inside `screens/glyphs.ts`; the `Icon` component itself (`components/Icon/
  Icon.tsx`) is unchanged, matching "No API change."
- **Axe verification for `Text`/`Button`/`MetricRow`.** The codebase's
  standing a11y gate (`src/test/a11y.axe.test.tsx`) is explicitly scoped, by
  its own header comment, to "safety-relevant honesty primitives"
  (Confidence/Signal/Staleness/ConditionStates/ContextRibbon) and calls out
  "generic chrome (Sheet, Toggle, OptionGroup, Icon) is out of scope here."
  `Text`/`Button`/`MetricRow` are the same category of generic chrome, so
  this epic did not add them to that file (consistent with `Toggle`/
  `OptionGroup`/`Icon` never having been added either). Axe-cleanliness was
  instead verified ad hoc, once, via a temporary local test harness
  mirroring the gate file's own `runAxe`/`composeStories` pattern against
  every story in all three new components (20/20 passed after fixing one
  `heading-order` false-positive in `Text`'s `AllRoles` gallery story, which
  stacked `display`(h1)/`title`(h3) outside real page context — fixed by
  rendering that demo-only pair `as="div"`). The temporary harness was
  deleted before commit; it is not part of the shipped diff. A permanent,
  broader a11y gate across all v0.2 components is WP-7's "Assembly + WCAG/
  contrast audit" scope, not this epic's.
