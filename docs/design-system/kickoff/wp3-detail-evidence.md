# Kickoff — WP-3 · Detail restyle + EvidencePanel + ContextSentence + MapControls

**Agent:** Gemini 3.1 Pro (B), via Antigravity, in a dedicated git worktree.
**Read first:** `docs/design-system/spec-v0.2.md` (esp. I.3, I.7, II.B) and open
`docs/design-system/mocks/happy-path-before-after.html` (§"Detail — the conditions block") and
`docs/design-system/mocks/states-gallery.html` (§7 mixed detail) in a browser.

## Goal
Bring the Detail screen and the feed's context header to v0.2: **conclusion-first conditions with the
evidence one tap away** (progressive disclosure), an **editable context sentence** (retiring "Adjust"/
"Curation"), honestly-named missing data, and re-tokenized map controls.

## Preconditions
Same as WP-2: **Contract A (tokens)** + **Contract B (types)** frozen; **WP-1 primitives** available. Consume
`ConditionTier` and the `ConditionStatus` engine from **WP-2** (coordinate at the merge desk if WP-2 is still
in flight — code against the frozen types, not WP-2's internals).

## Files
- **Modify/own:** `frontend/src/screens/Detail.tsx`, `frontend/src/screens/FeedConditions.tsx`
  (`ContextRibbon` → `ContextSentence`), `frontend/src/screens/map/MapControls.tsx`.
- **Create:** `frontend/src/screens/EvidencePanel.tsx` (extract the full condition table from `Detail.tsx`).
- **Do NOT touch:** `frontend/tokens/**`, `theme.css.ts`, `RecommendationCard.tsx`, the data layer, the map
  rendering internals (`MapPanel.tsx`, `mapStyle.ts` — only restyle the control cluster).

## Requirements
**EvidencePanel (progressive disclosure — NN/g):**
1. A **conclusion line** first: "Conditions look clear." / "Two things to know before you go." / "This trail
   is closed right now." — computed from the same ConditionStatus summarizer as WP-2.
2. A `<details>`/disclosure ("Checked 2 min ago — all six sources") revealing a compact grid: each source row
   colored by its tier (`clear` neutral, `unknown` gray-italic, `headsUp` amber, `blocked` terracotta),
   source + timestamp as `type.caption`. **Every source stays present** (Rule #1) — the panel hides them
   behind a tap, it does not drop them.
3. Clean the garbage: "flow reading unavailable at Pass Run Trib 2 To Trib 2 gauge" → "No gauge near this
   route"; "Permit info not fetched — 10 nearby facilities" → "None required here". (Copy from WP-6 templates.)

**Detail hero:**
4. `type.display` name; `MetricRow` mono. **Missing ascent/duration named** ("elevation & time not yet
   available for this route"), never `—`. Retire the `CONDITIONS` overline (or reduce to one `type.overline`).

**ContextSentence (`FeedConditions.tsx`):**
5. Render "For {when} near {origin}, {party}." as one `type.lead` sentence with an **edit** affordance
   (opens the existing `AdjustSheet` in `Tuning.tsx`). Retire the word "Adjust" and the "Curation" kicker.
6. The area "In this area" band collapses to **one honest line**; any `unknown` (e.g. AQI down) is gray and
   constructive, never red (Law 6/7).

**MapControls:**
7. Re-token base-layer chips + Locate/Fullscreen/Directions to `Button`/`Chip`, sentence case, `layers` glyph.

## Acceptance
- Storybook stories: EvidencePanel in **clear / mixed / blocked / a-source-unavailable** states, light + dark;
  ContextSentence with edit; MapControls.
- axe-clean; disclosure is keyboard-operable and announced; color never the only signal.
- Unit tests for the conclusion-line selection and the copy-cleanup mapping (**tests before callers**).
- Visual match to the mock detail block and states-gallery §7.
- Rule #1 preserved: no source dropped, provenance + timestamp intact.
- Targeted self-review; zero CRITICAL.

## Out of scope
The feed card (WP-2), tokens, the data/cache layer, map rendering internals.
