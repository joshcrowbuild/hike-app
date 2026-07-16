# Kickoff — WP-2 · ConditionStatus engine + TrailCard restyle

**Agent:** Gemini 3.1 Pro (A), via Antigravity, in a dedicated git worktree.
**Read first:** `docs/design-system/spec-v0.2.md` (esp. I.2, I.3, II.B, the 7 laws) and open
`docs/design-system/mocks/happy-path-before-after.html` (§"The feed", §"One card") and
`docs/design-system/mocks/states-gallery.html` (§1 condition tiers, §7 mixed detail) in a browser.

## Goal
Turn the feed card into the v0.2 design: **name leads, silence-when-clean, one action zone, mono metrics,
no per-card weather** — and build the **ConditionStatus engine** that maps our six coverage states onto the
4-tier signal system, as the single source of tier→treatment for the whole app.

## Preconditions (do not start until these exist and are frozen)
- **Contract A (tokens)** merged: `signal.{unknown,headsUp,blocked}`, the `type.*` v0.2 roles, `amber.600`
  (AA-verified), tokenized line-heights. Consume via `vars` from `frontend/src/design/theme.css.ts` — **never
  hardcode a hex or size.**
- **Contract B (types)** merged, including:
  ```ts
  type ConditionTier = 'clear' | 'unknown' | 'headsUp' | 'blocked'
  ```
- **WP-1 primitives** available: `Text`, `Button`, `MetricRow`, extended `Icon` glyphs.

## Files
- **Create/own:** `frontend/src/screens/ConditionStatus.ts(x)` (the engine — pure mapping + a `<ConditionStatusLine>`).
- **Modify:** `frontend/src/screens/ConditionStates.tsx` (reconcile to emit tiers), `cardParts.tsx`
  (`ConditionSilence`, `Verdict`, `DecisionFacts`), `frontend/src/screens/RecommendationCard.tsx` (the card).
- **Do NOT touch:** `frontend/tokens/**`, `theme.css.ts`, `Detail.tsx`, the data layer (`frontend/src/data/**`).

## Requirements
**ConditionStatus engine (the reusable core):**
1. Pure function `toTier(coverage): ConditionTier` mapping the six coverage states — `no-hazard → clear`;
   `present` → `headsUp` **or** `blocked` by *actionability* (closure/permit-hard-stop → `blocked`; heat/flow/
   advisory → `headsUp`); `no-data | unavailable | not-fetched | stale-degraded → unknown`.
2. `<ConditionStatusLine tier copy source? />` — renders **nothing** for `clear` (Law 1); a gray sentence for
   `unknown`; amber for `headsUp`; terracotta + soft field for `blocked`. Icon per I.5. All color from
   `signal.*` tokens.
3. A card-level summarizer: given a card's conditions, return the single most-severe tier + a conclusion
   string ("Heat advisory — start early" / "Closed — footbridge out" / for detail: "Two things to know").

**TrailCard restyle (`RecommendationCard.tsx`):**
4. **Name leads** (`type.title`), then `MetricRow` (mono, tabular; missing values named, never `—`).
5. Status line only when tier ≠ `clear`.
6. **One action zone** (Save · Directions as `Button`s). Remove the separate "OPEN DETAIL" affordance — the
   whole card opens Detail on tap/enter (keep keyboard + a11y).
7. **Remove per-card weather** (it's an area fact — Law 3; it will live in the ContextSentence/area band).
8. Sentence case throughout; no all-caps except a `type.overline` if truly needed.

## Acceptance
- Storybook stories covering **all four tiers × card** + the mixed-conditions card, light **and** dark.
- axe-clean; card is a single tab stop that activates Detail; status color is never the *only* signal (icon+text).
- Unit tests for `toTier` across all six coverage inputs (**tests before callers**).
- Visual match to the mock card and the states-gallery §1 tiers.
- **Rule #1/#2 preserved:** never invent a condition; presentation never reorders (`Staleness` still demotes).
- Targeted self-review; zero CRITICAL.

## Out of scope
Detail screen, EvidencePanel, the data/cache layer, tokens.
