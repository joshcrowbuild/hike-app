# Epic 047 — Design system v0.2 foundations (WP-0: tokens + frozen contracts)

**Status:** DONE ✅
**Phase:** 1 (look-and-feel layer; blocks WP-1..7)
**Spec refs:** `docs/design-system/spec-v0.2.md` Part IV.1 (the two frozen
contracts), Part IV.3 (WP sequencing), Appendix A (drift reconciliation),
Appendix B (the exact token deltas)

---

## Capability statement

The token pipeline (DTCG → Style Dictionary → `tokens.css` → `theme.css.ts`)
carries the full v0.2 vocabulary — the 4-tier signal system, the tokenized
role-based type scale, IBM Plex — and two frozen interface files
(`theme.css.ts`, `contracts.ts`) exist for WP-1..7 to code against in
isolated worktrees with zero merge conflict, where before there was only the
v0.1 Epic-019 scale and no component-API contract at all.

## Architectural context

**Builds on:** the shipped v0.1 pipeline (`frontend/tokens/*.json` DTCG →
`style-dictionary.config.js` → `frontend/src/design/tokens.css` →
`frontend/src/design/theme.css.ts`) — v0.2 extends it, does not replace it.

**Enables:** WP-1 (Text/Button/Icon/MetricRow primitives), WP-2 (ConditionStatus
engine + TrailCard), WP-3 (Detail/EvidencePanel/ContextSentence), WP-4
(EmptyState/SystemBanner/Skeleton), WP-5 (perf, token-independent), WP-6
(voice/glossary lint) — all depend on this epic per the WP dependency table
(spec IV.3).

**Does NOT include:**
- **No component file changes.** `RecommendationCard.tsx`, `Detail.tsx`,
  `FeedConditions.tsx`, `ConditionStates.tsx`, `Signal.tsx`, etc. are
  untouched — that's WP-1..7. `signal.caution` and the v0.1 `type.*` roles
  stay defined (not deleted) because those files still bind them.
- **No dark theme.** No `prefers-color-scheme` / `data-theme` support exists
  anywhere in `tokens/` or `src/design/` yet, so no dark-theme amber variant
  is authored here — noted as a follow-up (see below).
- **No voice/glossary lint** (WP-6) and **no perf work** (WP-5) — independent
  of tokens, scoped to their own WPs.

---

## Stories

### S1 — Token deltas (Appendix B)

**Given** the v0.1 primitive/semantic token JSON
**When** the v0.2 deltas are applied
**Then** `npm run tokens` regenerates `tokens.css` with every new token, and
nothing existing changes value.

**AC-1.1:** `primitive.json` gains `color.amber.600` (+ `alpha.10`),
`lineHeight.{tight,snug,normal,relaxed}`, `space.{10,11,12}`,
`duration.slow`, and `font.family.{sans,mono}` updated to the IBM Plex
stacks with the system stack retained as fallback.
**AC-1.2:** `semantic.json` gains `signal.{unknown,headsUp,blocked}`
(fg/bg per spec); `signal.caution` stays defined with a `$description`
marking it deprecated and naming the call sites that still bind it.
**AC-1.3:** `semantic.json`'s `type` group gains the v0.2 role scale
(`display/title/lead/body/body-sm/metric/metric-label/caption/overline`),
each carrying `size` + `lineHeight` (referencing the new primitive scale) +
`weight` (+ `family` → mono for `metric` only, D2). The v0.1 roles
(`name/verdict/fact-value/fact-label/condition/supporting`) are unchanged.
**AC-1.4:** `npm run tokens` is green and `tokens.css` is never hand-edited
(the auto-generated banner + the new custom properties are asserted in
`typeScale.test.ts`).

### S2 — Amber contrast verification (D1)

**Given** the spec's candidate `amber.600` (`#8a6a16`, 4.55:1 on
`surface.canvas` — passing AA but tight)
**When** WP-0 measures and, if needed, darkens it
**Then** the shipped hex clears **≥4.6:1** on both `surface.canvas` and
`surface.raised`, stays a warm amber (not brown), and the measurement is
recorded both in a token `$description` and in a falsifying test.

**AC-2.1:** Final hex `#846515` measures **4.91:1** on `surface.canvas`
(`#f4f3ef`) and **5.22:1** on `surface.raised` (`#fbfaf7`) — both computed
from the same hue/saturation ray as the spec candidate (43.45°, 72.5%),
lightness lowered from 31.4% to 30.9% for headroom.
**AC-2.2:** `typeScale.test.ts` asserts `amber.600` is `>= 4.6:1` on both
surfaces from the primitive hex directly (not hand-copied), so a future
value regression fails the build.
**AC-2.3 (follow-up, not blocking):** no dark-theme token set exists yet in
this repo; a lighter dark-theme amber variant is deferred until a dark
palette exists to extend.

### S3 — IBM Plex, self-hosted (D3)

**Given** the spec's self-host requirement (Latin subset, `font-display:
swap`, system fallback, preload the most-used faces)
**When** the fonts are wired
**Then** the build never blocks on the webfont and never fetches a CDN.

**AC-3.1:** `@fontsource/ibm-plex-sans` (400/500/600) and
`@fontsource/ibm-plex-mono` (400/500) are installed as devDependencies
(provenance for the woff2 assets); the Latin-only woff2 files are copied to
stable, unhashed paths under `frontend/public/fonts/` and served from there
— NOT imported via the fontsource package CSS — specifically so the
`index.html` preload `href` matches the fetched URL byte-for-byte (a
Vite-bundled, content-hashed import can't be preloaded reliably from a
static HTML file).
**AC-3.2:** `frontend/src/design/fonts.css` hand-authors the five
`@font-face` rules (`font-display: swap` on each), imported from
`main.tsx`; `font.family.sans`/`.mono` keep the system stack as fallback so
first paint never blocks.
**AC-3.3:** `index.html` preloads Sans 400 + Sans 600 (the two most-used
faces — body/lead/caption prose and display/title headings); Mono 500 is
self-hosted with `font-display: swap` but not preloaded (a smaller share of
on-screen text, `type.metric` only).

### S4 — Contract A: the token contract (`theme.css.ts`)

**Given** the typed `vars` contract over `tokens.css`
**When** every v0.2 token is wired
**Then** `vars.signal.{unknown,headsUp,blocked}`, `vars.lineHeight.*`,
`vars.space.{10,11,12}`, `vars.duration.slow`, and `vars.type.*` (both the
v0.1 and v0.2 role sets) are exposed, and `color.amber.*` stays **absent**
from the contract — consistent with the pre-existing rule that primitive
color ramps never reach components directly (amber reaches them only via
`signal.headsUp`).

**AC-4.1:** File carries a top-of-file "FROZEN CONTRACT (WP-0)" banner.
**AC-4.2:** `tsc --noEmit` is clean with the new `vars` shape.

### S5 — Contract B: component APIs (`contracts.ts`, NEW)

**Given** WP-2..WP-7 need a shared, stable set of types to code against in
isolated worktrees
**When** `frontend/src/design/contracts.ts` is created
**Then** it defines `ConditionTier`, `ConditionCoverage`, the
`ConditionTierMapper` signature, `TrailCardModel`, `EvidenceItem`, and
`SystemBannerModel`, aliasing `vm.ts` shapes where they already fit.

**AC-5.1:** Top-of-file "FROZEN CONTRACT (WP-0)" banner.
**AC-5.2:** No divergent duplication of `CardVM`/`LineVM`/`ConditionStatusVM`
— the new types alias/`Pick` from `vm.ts` and add only the v0.2 presentation
fields (`tier`, `conditionTiers`, banner shape).
**AC-5.3:** `tsc --noEmit` is clean.

### S6 — Scale test + drift reconciliation

**Given** `typeScale.test.ts` pinned the v0.1 Epic-019 roles
**When** it's updated for v0.2
**Then** it asserts the new role scale is authored as tokens (not
hand-edited), that `display` is the dominant role (Law 5), that `metric` is
the only role carrying a mono `family` (D2), and keeps the existing
`neutral.500` (`#5e636a`) WCAG-AA assertion unchanged.

**AC-6.1:** `typeScale.test.ts` green with the new assertions; the
`neutral.500` / muted-on-raised AA test is preserved verbatim.
**AC-6.2:** `docs/research/design-system-v0.1.md` carries a "superseded by
spec-v0.2.md" banner at the top.

---

## Definition of Done
- [x] All ACs covered by at least one passing test.
- [ ] `make check` (backend) unaffected — this epic is frontend-only.
- [x] Frontend `npm run tokens`, `npm run build`, `npm test` green (see PR
      description / commit for the exact run).
- [x] Targeted self-review; no CRITICALs found (see commit message for
      summary; documented deviations below).
- [x] Epic row added to `docs/epics/README.md`.
- [ ] Committed (this WP does not push or open a PR — the PO/merge-desk
      handles it, per WP-0 kickoff instructions).

## Deviations from spec (documented, not blocking)

- **Font delivery mechanism.** The spec's D3 line reads "self-hosted woff2,
  Latin subset" and the WP-0 kickoff brief suggested importing the
  `@fontsource/*` package CSS directly. WP-0 instead copies the Latin-only
  woff2 files into `public/fonts/` and hand-authors `fonts.css`, so the
  `index.html` preload `href` is guaranteed to match the fetched URL
  (Vite content-hashes anything bundled from `node_modules`, which a static
  `index.html` preload tag can't target reliably). The fontsource packages
  are still installed and are the source of the shipped woff2 files.
- **Preload count.** The kickoff brief said "preload the two most-used
  faces"; spec I.3 literally lists three ("preload Sans 400/600 + Mono
  500"). WP-0 preloads two (Sans 400 + Sans 600) and reconciles the
  difference by *not* preloading Mono 500 — it's self-hosted with
  `font-display: swap` and used only for `type.metric`, a smaller share of
  on-screen text, so it doesn't compete for bandwidth with the two faces
  that paint the most text on first load.
- **v0.2 type-role `size` values are literal, not primitive references.**
  The v0.1 roles reference a `size.*` primitive step (`{size.name}`); the
  v0.2 roles hardcode the rem value directly, matching Appendix B's jsonc
  exactly, rather than adding a second `size.*` primitive namespace whose
  keys would collide in spirit (though not in literal key name) with the
  v0.1 sizes carrying different values under similar names (e.g. a new
  "title" role at 1.25rem vs. the existing `size.title` primitive at
  1.5rem, used for an unrelated purpose).
