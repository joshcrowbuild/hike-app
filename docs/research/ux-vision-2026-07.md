# UX Vision (2026-07) — Cockpit-Grade Discipline, Beautifully Delivered

**Owner:** design-agent
**Status:** FOR REVIEW

---

## 1. First Principles

The Adventure Planner is a **calm, private utility**. It exists to answer one question for one person: *Is this trip a good idea right now?* 

The core job is not to present a dashboard of raw data, but to deliver a **trustworthy, re-derivable verdict** so the user can spend 30 seconds reading it, trust it under stress, and go outside.

**What the person should feel:**
Relief. The physical sensation of exhaling because someone else has done the homework perfectly, checked the margins, and handed you the result. The UI must feel utterly deliberate, quiet, and un-anxious. When the app warns you, it should feel like a tap on the shoulder from an expert, not a siren.

## 2. Design Philosophy

1. **The Hedge is the Honesty:** Confidence and certainty are conveyed through quiet language ("seems to be"), never through loud colors or numeric percentages on primary surfaces.
2. **One Answer, Many Alternatives:** A planner should plan. The primary surface is an opinionated recommendation (The Call), not a flat list of equal choices. 
3. **Information Rests Until Asked For:** We don't dump 12 metadata rows on the primary view. The summary is the surface; the proof is a tap away.
4. **Context is Region-Wide:** If a weather system affects the whole valley, state it once at the top of the screen. Don't repeat it on every trail.
5. **Flat, Matte, Cartographic:** UI depth is a distraction. Use ink on paper. Distinguish data through typography (monospace for facts) and spacing, not shadows.
6. **The Glyph Must Not Lie:** Every visual representation of data (like the terrain profile) must share a common scale. If it's flat, draw it flat.
7. **Absolute Silence is an Error:** The absence of a hazard must be actively confirmed ("Checked, nothing to flag"), never implied by empty space. 

## 3. Divergent Directions

### Direction A: The Single Answer (Conversational)
**The Bet:** You opened the app to decide where to go. We already know your tastes and capability. We should just tell you the best option.
```text
[   Sat, 7:00 AM   ]
[   Shenandoah     ]

      Fox Hollow
      is your best
      bet today.
      
[ GOOD TO GO ]
  Clear, 61°F, 3.0 mi.
  
  (Swipe left for
   Hammock Hills)
```
- **Interaction:** Full screen single recommendation. Swipe horizontally for next-best.
- **Brilliant at:** Eradicating analysis paralysis. Extreme calm.
- **Sacrifices:** Spatial orientation, quick comparison of distances.
- **Honesty Layer:** Stated inline immediately under the hero text.

### Direction B: Map-First (Cartographic)
**The Bet:** Hiking is inherently geographic. The list is the wrong container.
```text
+------------------+
|      MAP         |
|   /      \       |
|  / [Fox]  \      |
| /          \     |
|    [Ham]         |
+------------------+
| Region: Clear    |
| Tap a trail      |
+------------------+
```
- **Interaction:** The map is the app. Trails are drawn as routes. Conditions are pinned to the map or shown globally in a quiet bottom ribbon.
- **Brilliant at:** Spatial context, understanding micro-climates.
- **Sacrifices:** Text density, quick reading of specific facts like ascent. 
- **Honesty Layer:** Anchored to the trail pins; requires a tap to reveal confidence.

### Direction C: Radically Minimal (Text & Silence)
**The Bet:** Dashboards cause anxiety. Prose brings calm.
```text
SHENANDOAH — SAT MORNING

The region is mostly clear (61°F). 
Air quality couldn't be verified.

We recommend Fox Hollow (3.0 mi).
It's good to go, though the USGS 
gauge is 9 miles away.

Hammock Hills (3.3 mi) is also clear.
```
- **Interaction:** A prose log that reads like a briefing from a guide. No cards.
- **Brilliant at:** Natural reading, eliminating "UI".
- **Sacrifices:** Scannability.
- **Honesty Layer:** Woven directly into the English sentences ("couldn't be verified").

### Direction D: The Cockpit (Instrument-First)
**The Bet:** Users want to compare structured data.
```text
TRAIL      DIST  ASC  VERDICT
Fox Hollow 3.0   278  [GO]
Ham. Hills 3.3   13   [GO]
Cap. Trail 0.7   0    [NO]
```
- **Interaction:** A strict, perfectly aligned matrix.
- **Brilliant at:** Direct comparison.
- **Sacrifices:** Visual delight, emotion. 
- **Honesty Layer:** Strict columns for freshness and source.

## 4. Recommended Synthesis: "The Confident Call + Quiet Context"

I recommend fusing **The Single Answer** with elements of **Map-First**, explicitly resolving the tensions:
1. **Calm vs. Informative:** We state region-wide context (weather, air quality) exactly once at the top of the screen. We inform completely without the anxiety of repetition.
2. **Hedging vs. Reassurance:** We use "The Call" (one hero recommendation). We hedge in the prose ("seems clear"), which reassures because it is honest.
3. **A List vs. An Answer:** The primary surface is *An Answer* (one large card), but the *List* of alternatives is docked below it.
4. **Utility vs. Delight:** Delight comes from the beautiful, true-to-scale terrain drawing on the hero card and the immaculate typography, not engagement mechanics.

## 5. Concrete Redesigns

### Mobile: Home 
```text
[ CURATION ]                   [ SIGN IN ]

  SHENANDOAH · SATURDAY MORNING
  ✓ Mostly Cloudy 61°F · NWS 
  – Air quality couldn't be verified

+----------------------------------------+
| FOX HOLLOW TRAIL                       |
| Good to go — nothing flagged           |
|                                        |
| 3.0 mi   ↑ 278 ft   ~35 min            |
|                                        |
|      _.-^^-._                          |
| __.-^        ^--._                     |
+----------------------------------------+

  OTHER OPTIONS
  Hammock Hills (3.3 mi)          [ GO ]
  Virginia Capital (0.7 mi)       [ NO ]
```
**Hierarchy:** Region Context -> The Call (Hero Card) -> Alternatives. The terrain profile is finally scaled to reality.

### Desktop: Home
```text
[ CURATION ]                 [ SIGN IN ]

+--------------------+-----------------+
|                    | SHENANDOAH      |
|                    | ✓ Cloudy 61°F   |
|        MAP         |                 |
|                    | +-------------+ |
|                    | | FOX HOLLOW  | |
|                    | | Good to go  | |
|                    | | 3.0mi ↑278ft| |
|                    | +-------------+ |
|                    |                 |
|                    | OTHER OPTIONS   |
|                    | Hammock Hills   |
+--------------------+-----------------+
```
**Hierarchy:** The 1280px width is respected. The left 60% is a gorgeous matte map. The right 40% is the decision panel, mirroring the mobile hierarchy.

### Mobile: Detail
```text
[ BACK ]                       [ GPX ]

  FOX HOLLOW TRAIL
  Good to go — nothing flagged across 6 checks

  3.0 mi   ↑ 278 ft   ~35 min 
  
  [ MAP ]
  
  ELEVATION
  Min 1,200 ft · Max 1,478 ft · USGS 3DEP
  [ Scaled chart with axes ]
  
  CONDITIONS
  [WEATHER] ✓ Mostly Cloudy 61°F · NWS
  [AIR]     – Couldn't verify
  [FIRE]    ✓ Checked - nothing to flag
  [WATER]   ✓ 12 cfs at Pass Run gauge
  
  SOURCES (Inspection Layer)
  ...
```

### Intent / Search Entry
```text
[ BACK ]                       [ DONE ]

  Where are you starting?
  
  [ Search origins... ]
  
  RECENT
  Front Royal (Shenandoah)
  
  SHENANDOAH
  Big Meadows
  
  OUTER BANKS
  Ocracoke
```

## 6. Design Language

- **Type Scale:** Strictly enforce the 8-step semantic scale. No literal sizes.
  - `font.sans`: The system grotesque for prose (clean, legible).
  - `font.mono`: Used strictly for *all data* (cartographic voice).
- **Confidence Encoding:** Never use color alone. 
  - *High*: `text.primary`, plain statement.
  - *Medium*: `text.secondary`, hedged phrase ("seems to").
  - *Low/Verify*: `signal.caution.fg` (terracotta) beside an inline 2px rule. No massive banners.
- **Spacing:** Absolute adherence to the 4px grid (`space.0` to `space.8`).
- **Terrain Drawing:** The SVG amplitude must scale relative to a regional absolute maximum. Flat trails must draw flat.
- **Motion:** Sub-160ms. Press states confirm touch. No decorative lift.
- **Silence:** Checked-and-clear is stated quietly (`border.faint`, `text.muted`).

## 7. Voice & Microcopy

- **A Verdict:** "Good to go — nothing flagged across 6 checks." (Replaces the false "conditions look clear")
- **A Hedge:** "Good to go — storms possible, nothing blocking."
- **An Unverifiable Fact:** "Air quality couldn't be verified right now."
- **An Empty Search:** "We don't have verified data for that region yet."

## 8. Kill List

1. **The 10-Card Repetition:** Kill the condition block repetition. Region stats go to the top ribbon.
2. **Default "Clear" Copy:** Kill `conditions look clear` as a fallback string.
3. **Normalized Terrain Polyline:** Kill the 100% stretch amplitude.
4. **Desktop Empty Space:** Kill the stranded 432px center column on large viewports.
5. **Raw Floats:** Kill the 14-decimal precision on grades.
6. **"CURATION" / "BROWSING":** Kill the mode labels and replace with the real app name and a "Sign In" affordance.

## 9. "If you only did three things"

1. **Implement Region-Scoped Conditions (The Context Ribbon).** Stop repeating the weather and air quality on every card. Move them to a single header. *(Touches: `Home.tsx`, `RecommendationCard.tsx`)*
2. **Build "The Call" Hero Card.** Reintroduce ascent and duration to the primary card, scale the terrain glyph honestly, and make it the primary focus of the feed. *(Touches: `cardParts.tsx`, `RecommendationCard.tsx`)*
3. **Fix the Detail Conditions Merge.** Flatten the Detail conditions into one row per kind, showing the actual value (e.g. CFS for streamflow) instead of just the gauge name. *(Touches: `Detail.tsx`, `ConditionStates.tsx`, `orchestration/present.py`)*

---
