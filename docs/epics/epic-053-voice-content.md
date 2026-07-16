# Epic 053 — Voice & content system (WP-6)

**Status:** IN_PROGRESS (WP-6 delivery in progress)

**Scope:** Banned-builder-noun glossary + lint · state-message templates · microcopy  
**Owner:** WP-6 (Haiku agent)  
**Blocks:** WP-7 (Assembly + audit)  
**Depends on:** WP-0 (Contracts A & B frozen)

---

## Design spec

- **Source:** `docs/design-system/spec-v0.2.md §I.7` (Voice & content)
- **Mocks:** `docs/design-system/mocks/states-gallery.html` (all state examples)
- **Law 4:** Speak human — no builder nouns on screen.
- **Law 6:** Degrade calmly — never alarm-red for a non-event.

## Deliverables (new files only; no component edits)

### 1. `frontend/src/copy/messages.ts`

State-message templates exporting **one function/const per state**, following the rule:
> Conclusion-first, ≤1 sentence, name the one thing + the one next step.

**Exports:**
- `clear()` → undefined (Law 1: silence is a state)
- `headsUp(detail)` → string (e.g., "Heat advisory today — start before 10am.")
- `blocked(detail)` → string (e.g., "Closed — footbridge out (NPS, checked 4m ago).")
- `unknown(sourceName)` → string (e.g., "Air-quality data is unavailable right now — everything else checked out.")
- `emptySearch(searchTerm, placeLabel, trailCount)` → { headline, secondary, cta }
- `emptyFilters(filterDescription, placeLabel, suggestedChange, suggestedTrailCount)` → { headline, secondary, cta }
- `personalizationDegraded()` → { headline, secondary, cta }
- `liveOutage()` → { message, secondary }
- `stalePaint()` → string ("Updating conditions…")
- `systemBannerMessages` → Record of kind → (tier) → string

**Types:** All against `frontend/src/design/contracts.ts` (`ConditionTier`, `SystemBannerKind`).

### 2. `frontend/src/copy/voice.test.ts`

Vitest that lints banned words in user-facing strings and enforces the glossary.

**Banned words** (design-system-v0.2.md §I.7, table):

| Banned | Say instead |
|--------|-------------|
| Curation / Curated | (a plain greeting, or nothing) |
| Adjust | Edit day, place or party |
| N checks / Checked N sources | "Conditions look clear" (+ evidence on tap) |
| frame / context / personal context | (name what actually happened) |
| fetched / not fetched | "not required here" / "unavailable right now" |
| Couldn't verify: X | "X is unavailable right now — everything else checked out" |
| options | trails |

**Baseline allowlist:**
- Documents EXISTING pre-v0.2 occurrences (FeedConditions.tsx, Home.tsx, test files, etc.)
- NEW violations fail the test
- WP-7 burns down the allowlist as components migrate
- Allowlist entry: { file, pattern, reason }

**Pattern:** Each banned word is a regex; allowlist entries define file + pattern combination that are exempt (pre-v0.2, refactoring debt, tests, demo only, internal comments).

### Test expectations

- Scans `frontend/src/**/*.ts` and `frontend/src/**/*.tsx` (excludes `.test.`, `.stories.`, `tokens/`, `node_modules`)
- Skip-guards for: comments (`//`, `*`), internal type/function names, component names like `AdjustSheet`, `OptionGroup`
- Fails on any NEW violation outside the baseline allowlist
- Prints allowlist summary on pass (for progress tracking)

---

## Acceptance criteria

- [x] Messages module exports one const/function per state (9 total)
- [x] All messages follow the 1-sentence, conclusion-first rule
- [x] Messages type against `ConditionTier` and `SystemBannerKind` from contracts
- [x] Voice lint test runs in vitest (part of `npm test`)
- [x] Baseline allowlist documents pre-v0.2 occurrences
- [x] NEW violations are caught and fail the test
- [x] `npm run build && npm test` is green
- [x] Messages sourced from mocks (states-gallery.html) and spec (I.7)
- [x] No edits to existing components, tokens, or design contracts

---

## Notes

- Microcopy follows the **mocks exactly** (states-gallery.html is the SSOT for copy, per spec §IV.2)
- System banner messages are typed by kind (`regional-alert`, `live-outage`, `personalization-degraded`)
- Allowlist is documented so WP-7 can track burn-down during assembly
- No npm dependencies added; no `.env` or `package.json` script changes needed
