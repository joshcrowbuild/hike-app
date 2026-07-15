# Call-Card Design Spec (2026-07) — The Hero "Call"

**Owner:** design-agent
**Status:** FOR DESIGN REVIEW — PO adoption pass required before merge.
**Implements:** `ux-vision-2026-07.md` (The Confident Call + Quiet Context)

## 1. Information Hierarchy & Wireframes

The primary surface is **The Call**: a single, opinionated recommendation that occupies the majority of the feed's initial viewport. Secondary options are docked quietly beneath it.

### Mobile Width (Default)
```text
[ CURATION ]                   [ SIGN IN ]

  SHENANDOAH · SATURDAY MORNING
  ✓ Mostly Cloudy 61°F · NWS 
  – Air quality couldn't be verified

+----------------------------------------+
| FOX HOLLOW TRAIL                       |
| [VERDICT SLOT (Future)]                |
| Good to go — nothing flagged           |
|                                        |
| 3.0 mi   ↑ 278 ft   ~35 min            |
|                                        |
|      _.-^^-._                          |
| __.-^        ^--._                     |
|                                        |
| [WARNING BLOCK IF APPLICABLE]          |
| [CONDITION STATES - COMPACT]           |
+----------------------------------------+

  OTHER OPTIONS
  Hammock Hills (3.3 mi)          [ GO ]
  Virginia Capital (0.7 mi)       [ NO ]
```

### Desktop In-Column (34rem Max Width)
(Note: The map-split is a future lane. This specifies the existing 34rem central column behavior).
```text
+-------------------------------------------------+
| SHENANDOAH · SATURDAY MORNING                   |
| ✓ Mostly Cloudy 61°F · NWS                      |
| – Air quality couldn't be verified              |
|                                                 |
| +---------------------------------------------+ |
| | FOX HOLLOW TRAIL                            | |
| | [VERDICT SLOT]                              | |
| | Good to go — nothing flagged                | |
| |                                             | |
| | 3.0 mi   ↑ 278 ft   ~35 min                 | |
| |                                             | |
| |        _.-^^-._                             | |
| |   __.-^        ^--._                        | |
| |                                             | |
| | [WARNING BLOCK IF APPLICABLE]               | |
| | [CONDITION STATES - COMPACT]                | |
| +---------------------------------------------+ |
|                                                 |
| OTHER OPTIONS                                   |
| Hammock Hills (3.3 mi)                 [ GO ]   |
| Virginia Capital (0.7 mi)              [ NO ]   |
+-------------------------------------------------+
```

## 2. Every State (Honesty Grammar)

- **Stated (High Confidence)**: Plain text (`vars.text.primary`). E.g., "Good to go".
- **Hedged (Medium Confidence)**: Secondary text (`vars.text.secondary`), hedged language. E.g., "Good to go — seems clear but storms are possible".
- **Flagged (Low/Unavailable)**: Uses the `Signal` primitive (accent color) for the whole block, with `vars.signal.caution.fg`.
- **Warning-Bearing (§41)**: If a live alert exists, it MUST be visible on the hero card. The warning is styled using the `Signal` component and sits immediately below the terrain profile, above the compact conditions. It is never hidden.
- **Conditions Pending (Two-Phase Render)**: Before conditions arrive, the hero card shows a pending state: "Checking current conditions...". The card must never read as "clear" until confirmed.
- **Honestly-Empty Feed**: When there are no recommendations matching the criteria, the feed states "We don't have verified data for that region yet." instead of showing an empty list or blank screen.
- **Set-Aside/Unverifiable**: "Couldn't verify right now" routes through the flagged `<Confidence>` tier.

## 3. Alternatives Docking Model & Interaction Spec

- **Interaction**: The alternatives list docks beneath the hero card. It is not an infinite scroll.
- **Surface**: It surfaces exactly the next 3 best options by default.
- **Expansion**: A "Show more" button can reveal the rest of the list if there are more than 3 alternatives, but it's an explicit tap.
- **Navigation**: Tapping an alternative navigates to its Detail screen directly, OR if in a specific selection flow, it promotes that alternative to the Hero slot (this depends on the future map integration, but for v1, tapping goes to Detail).

## 4. Type & Token Spec

We reuse existing tokens exclusively to maintain consistency and accessibility.
- **Hero Title**: `vars.font.family.sans`, `vars.size.title`, `vars.font.weight.semibold`, `vars.text.primary`.
- **Hero Verdict/Hedge**: `vars.font.family.sans`, `vars.size.body`.
  - Confident: `vars.text.primary`.
  - Hedged: `vars.text.secondary`.
- **Facts Row**: `vars.font.family.mono`, `vars.size.label`, `vars.text.primary`. Borders: `vars.border.faint`.
- **Warnings**: `vars.signal.caution.bg` for background, `vars.signal.caution.fg` for text.
- **Pending/Empty State**: `vars.text.muted` for pending copy, potentially with a pulse animation.
- **Surface/Card Base**: `vars.surface.raised`, `vars.border.hairline`, `vars.radius.md`.

*No new tokens are required for this lane.*

## 5. Microcopy Samples

- **Confident Call**: "Good to go — nothing flagged across 6 checks."
- **Hedged Call**: "Good to go — seems clear, but afternoon storms possible."
- **Warned Call (Caution)**: "Heads up — Trailhead access road is washed out."
- **Pending Line**: "Checking current conditions..."
- **Empty Search**: "We don't have verified data for that region yet."
- **Unverifiable Fact**: "Air quality couldn't be verified right now."

## 6. Future-Verdict Slot (CDP-04)

- **Location**: The future CDP-04 GO/MARGINAL/NO-GO verdict will land immediately below the trail name and above the hedged condition summary on the Hero card.
- **Placeholder Discipline**: Until CDP-04 is built, this slot remains *empty*. We do not synthesize a GO/NO-GO badge based on incomplete data. The text verdict ("Good to go") acts as the primary assessment in v1.

## 7. Build Plan (Increment Strategy)

When adopted by PO, this will be merged into production via the following PR sequence:

1. **Increment 1: Context Ribbon & Cleanup (Touches: `Home.tsx`, `RecommendationCard.tsx`)**
   - Extract the region-level conditions (weather, air quality) from the individual cards into the new Context Ribbon at the top of the feed.
   - Remove redundant condition lines from the cards.
2. **Increment 2: Hero Card Structural Rewrite (Touches: `cardParts.tsx`, `RecommendationCard.tsx`)**
   - Build the Hero `article` component with the new facts row (Distance, Ascent, Duration).
   - Integrate the terrain profile SVG.
   - Implement the two-phase render (Pending vs Loaded).
3. **Increment 3: Honesty & Warnings on Hero (Touches: `Home.tsx`, `ConditionStates.tsx`, `cardParts.tsx`)**
   - Apply the §41 `WarningBlock` to the Hero card.
   - Render the compact `<ConditionStates>` summary at the bottom of the Hero card.
   - Implement the docking model for alternatives (top 3 below the hero).
