# Epic 055 — The "This feed" card + conditions strip + Detail provenance

**Status:** DONE ✅
**Phase:** 1 (frame-conditions wave, card lane — the centerpiece)
**Spec refs:** `docs/design-system/frame-conditions-wave.md` §2 (mocks of record), §3–4; mocks `frame-card-typescale.html` (variant 01), `frame-card-conditions-zones.html`, `frame-card-recent-weather-mud.html`, `conditions-strip-states.html`, `detail-provenance-tap.html`

---

## Capability statement

The feed opens with one boarding-pass card that states the frame (From as the
headline, When as the subline, Party·Effort as small slate chips — hierarchy
by type scale, every facet tappable at rest) and holds the area's conditions
temporally aligned to the frame's day: a forecast zone with a working day
toggle, a right-now zone honestly caveated "may change by ‹day›", a collapsed
Past-3-days rain reveal with the hedged mud read, and skeleton-chip loading.
Feed cards go conditions-silent; the Detail shows this trail's chips with
tap-to-reveal receipts.

## Architectural context

Builds on: frozen Contracts A/B (+ the PR-0 `interactive`/`forecast` tokens and
`ChipState`/`ConditionChipModel`/`ReceiptModel`); `vm.ts`'s
`RegionConditionsVM` et al.; the existing `AdjustSheet`/`PanelSheet` overlays
(facet taps open the existing panels); `splitFeedConditions` hoisting;
`useFeed().reload()` as the Refresh/retry action.
Enables: Epic 057's chrome polish on a settled Home layout.
Does NOT include: data-layer changes (`frontend/src/data/*` beyond the mock
engine — Epic 056 owns those files); backend anything (054).

---

## Stories

### S1 — The facet stack
**AC-1.1:** From (headline, ~21–23px slate + chevron), When (subline slate),
Party·Effort (small filled slate chips) — sizes per the type-scale-stack mock;
all four open their existing PanelSheets; anonymous viewers see only
world facets.
**AC-1.2:** Affordances visible at rest, no hover-dependence, tap targets
≥ 30px; slate binds `vars.interactive.*` only.
**AC-1.3:** `This feed` header + `current`/`forecast` tags use the overline
role (the one uppercase exception); everything else sentence case.

### S2 — Forecast zone + day toggle
**AC-2.1:** Zone header `‹Day› forecast`; segmented toggle from
`forecast.days`; default = `targetKey`; switching days never refetches.
**AC-2.2:** Chips: high temp, precip %, optional short — mono values.
**AC-2.3:** `forecast` null → pending skeletons while phase-2 runs, then one
muted `Forecast unavailable right now` line on degrade. Never a fabricated
value.

### S3 — Right-now zone
**AC-3.1:** Region-shared current readings render as strip chips
(fresh/stale/unavailable per `ChipState`; stale = dashed + gray age).
**AC-3.2:** Caveat `· may change by ‹day›` only when the frame targets a
future day; `current` overline tag.
**AC-3.3:** A quiet Refresh action calls `reload()` (the one on-demand
refetch, Q10).
**AC-3.4:** Warning-owned kinds tint (headsUp amber / blocked terracotta,
max severity wins — Q5/Q7).

### S4 — Past 3 days + mud read
**AC-4.1:** Collapsed `› Past 3 days` disclosure; open = per-day rain (wet
days in `forecast.fg`, dry muted).
**AC-4.2:** Mud read renders ONLY when `mud` present: amber, dashed border,
`inferred` tag, statement + evidence + source, exactly per the mock.
**AC-4.3:** `recentPrecip` null → the reveal does not render at all.

### S5 — Cards silent, Detail receipts
**AC-5.1:** `RecommendationCard` drops its condition summary line; keeps
name/metrics/WarningBlock/actions; warnings tint by severity.
**AC-5.2:** Detail: WarningBlock(s) then a `Current conditions` strip of this
trail's per-kind chips; tapping a chip reveals ONE receipt line below the
strip (source · age · confidence), swapped per tap, collapsed by default —
replacing the always-visible sourced list. No popover.
**AC-5.3:** The old `ContextSentence` ribbon + compact `ConditionStates` band
are removed from Home (superseded by the card).

### S6 — Honesty + tests
**AC-6.1:** Mock engine exercises every state (all-fresh, stale, unavailable,
warned amber + terracotta, forecast, precip, mud, pending, degraded).
**AC-6.2:** Component tests cover: facet taps open panels; toggle switches
days without refetch; mud renders only when present; chips tint by severity;
receipt reveals on tap; cards render no condition line; a11y roles/labels on
toggle + chips + disclosure.
**AC-6.3:** No condition value ever renders from non-live provenance wearing
a confident tier (existing honesty primitives respected).

---

## Definition of Done
- [x] All ACs covered by at least one passing test
- [x] `npm run build` + `npm test` green (702 tests)
- [x] Targeted review agent run; CRITICALs fixed (desk review)
- [x] Committed and pushed
