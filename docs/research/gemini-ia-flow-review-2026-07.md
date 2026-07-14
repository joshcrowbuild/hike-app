# IA / Flow / Usability Review + Location-Query Rethink

**Date**: 2026-07
**Author**: Gemini (GLM)

## Part 1: Diagnosis & IA Mapping

### Current IA Model
The app operates on a mobile-first, single-column feed paradigm. It is fundamentally a "curated results" view that defaults to a pre-filled state, rather than a traditional landing page.

- **Header**: Curation / Browsing mode indicator
- **Context Sentence (The Query)**: e.g., "Weekend morning · Shenandoah · from Front Royal" with a recessive `[ADJUST]` action.
- **The Feed**: Vertically stacked cards representing curated trails matching the query. Honesty primitives (safety banners, condition ribbons) are hoisted above the stack.
- **Detail View**: Tapping a card pushes a new route onto the stack, showing deeper information (description, map, route, elevation, granular conditions, save/directions).

### Flow Traces & Friction Points

1. **(a) Land → Browse Feed → Understand a Card**
   - *Trace*: The user lands directly on a populated feed based on a default or persisted tuning state.
   - *Friction (Moderate)*: The desktop experience (1280px) is literally the mobile viewport centered in a vast expanse of grey canvas (`desktop_home.png`). It does not utilize horizontal space for map splits or side-by-side comparison, making the desktop experience feel unoptimized.
   - *Friction (High)*: The context sentence at the top is the *only* indication of the current location bounds. The user must parse the text string to understand why they are seeing these specific trails.
   - *Files*: `frontend/src/screens/Home.tsx`, `RecommendationCard.tsx`
   - *Screenshots*: `mobile_home.png`, `desktop_home.png`

2. **(b) TUNE the query (origin picker + facets + readiness) → see results change**
   - *Trace*: Tap "ADJUST" on the context sentence → Sheet slides up (`mobile_tune.png`) → Select facet → Sheet closes, facet options appear → Select option → Feed updates.
   - *Friction (High)*: The tuning sheet is an opaque overlay that hides the feed entirely on mobile. Furthermore, the "Refine with a phrase" input is buried at the absolute bottom of the Adjust sheet, structurally separating structured facets (When, From, Effort) from unstructured natural language intent.
   - *Files*: `frontend/src/screens/Tuning.tsx`, `AdjustSheet`
   - *Screenshots*: `mobile_tune.png`

3. **(c) Pick a starting location**
   - *Trace*: Adjust → Tap "From" → Select from a hardcoded list of towns or "Near me".
   - *Friction (Critical)*: The list is an enum. If a user wants to start from a place not in the list (e.g., they live 20 miles outside the listed town), it's a dead end. The user's spatial reality is constrained by the app's config file.
   - *Files*: `frontend/src/data/regionsCatalog.ts`
   - *Screenshots*: `mobile_origin.png`

4. **(d) Open Detail → map/route/elevation → save / get directions**
   - *Trace*: Tap card → Detail view slides in (`mobile_detail.png`) → Map is at the bottom, action buttons (Save, Directions, GPX) are clustered above the metrics.
   - *Friction (Low)*: The map is below the fold. For spatial thinkers, having to scroll past the prose description and metrics to see the actual route/terrain is a slight friction point, though it honors the "decision first, navigation second" hierarchy.
   - *Files*: `frontend/src/screens/Detail.tsx`
   - *Screenshots*: `mobile_detail.png`

5. **(e) Log an outcome**
   - *Trace*: After a hike, a "pending nod" appears on Home → Tap nod → Outcome screen.
   - *Friction (Moderate)*: The prompt relies on the user returning to the app organically. However, this respects the strict anti-engagement refusal (no push notifications asking for logs).

### Ranked Findings
1. **[CRITICAL] Fixed Origin Enum**: The "From" location picker is too rigid, creating a hard dead end for users whose mental anchor isn't in the hardcoded list.
2. **[HIGH] Natural Language vs. Facets Split**: The intent parser is powerful, yet the free-text input is buried beneath structured dropdowns in the UI.
3. **[MODERATE] Desktop IA Underutilization**: The 1280px viewport is wasted.
4. **[MODERATE] Map Below the Fold**: Spatial context in the Detail view requires scrolling.

---

## Part 2: Interrogating the Location/Query Model

The current answer to "where do I want to go?" is a fixed enum of towns + "near me".

**Critique against real use cases:**
- **"Near me now"**: Functions well, relying on device geolocation.
- **"Dreaming from home about a place"**: Fails completely unless the destination happens to be one of the config-driven towns. 
- **"Within 2 hours of X"**: The backend possesses Valhalla drive-time isochrones, but the frontend forces the user to set 'X' to an enum town. The computational power of the engine is bottlenecked by a primitive UI.
- **"A specific trail"**: Impossible. There is no way to search by trail name (Epic 038 / B001 addresses this, but it is currently absent from the UI).
- **"A whole region"**: The region is inferred backward from the curated cards (`resolveRegionLabel`), not explicitly chosen by the user.

**Location Coupling:**
Location ("From Front Royal") is currently treated as just another peer facet alongside "When" and "Effort" in the Adjust sheet. This is an awkward structural split. Location is the *primary* anchor of a spatial query, not a secondary modifier. The user's intent is usually a single cohesive thought: *"A moderate hike near Charlottesville this weekend"*. Forcing them to decompose this into three separate dropdowns breaks the natural flow of thought.

---

## Part 3: Generative Paradigms

Here are 3 distinct paradigms for how a user expresses location + intent, and how curated results are presented.

### Paradigm 1: The Unified Intent Line (Omnibox)
**Interaction Model**: Replace the rigid "Adjust" sheet and the context sentence with a single, prominent natural language input field at the top of the Home feed. The user types their entire intent in one go: "Moderate hikes within 2 hours of Charlottesville this weekend". Structured chips appear below the input to clarify how the engine parsed the query.
**Wireframes**:
*(Mobile)*
```text
-------------------------
| Curation              |
| [ 🔍 Hikes near C'ville... ] |
|  (Moderate ✕) (Weekend ✕) |
|                       |
| [ Card 1 ]            |
| [ Card 2 ]            |
-------------------------
```
*(Desktop)*
```text
-----------------------------------------------------
| Curation                [ 🔍 Moderate hikes near... ] |
|                                                   |
| [ Card 1 ]      [ Card 2 ]      [ Card 3 ]        |
-----------------------------------------------------
```
**Tradeoffs**: High flexibility, zero dead ends. Fast time-to-value. However, it relies heavily on the `parse-intent` engine being highly accurate. Discoverability of specific features (like "dog friendly") is lower than an explicit checklist.
**Refusals Fit**: Respects source-or-silence (the engine still verifies the results). Respects anti-engagement (fast input, fast answer). 
**Architecture Fit**: The engine *already* has a `parse-intent` seam. The B001 search epic scopes trail-name search and geocoding. This paradigm simply promotes those existing/planned backend capabilities to be the primary UI.

### Paradigm 2: The Map-First Isochrone Picker
**Interaction Model**: The primary view is a map, not a feed. The user drops a pin (or uses current location) and drags a slider for "Time budget" (e.g., 1 hour drive). A shaded isochrone blob draws on the map, and verified trail pins appear inside it. Swiping up on a bottom sheet reveals the curated cards for those pins.
**Wireframes**:
*(Mobile)*
```text
-------------------------
|       /====\          |
|      /      \         |
|     |   📍   |        |
|      \      /         |
|       \====/          |
|-----------------------|
| 1 hr drive | Moderate |
|-----------------------|
| [ Card 1 ]            |
-------------------------
```
*(Desktop - Split View)*
```text
-------------------------------------------------
| [ 📍 Front Royal ] [ 🚗 1 hr ] [ 🏃 Moderate ]|
|-----------------------|-----------------------|
|          /====\       |                       |
|         /      \      |  [ Card 1 ]           |
| Map    |   📍   |     |  [ Card 2 ]           |
|         \      /      |  [ Card 3 ]           |
|          \====/       |                       |
-------------------------------------------------
```
**Tradeoffs**: Highly spatial and intuitive. Utilizes desktop width beautifully with a split view. However, it strains the "curated feed, not infinite scroll" refusal if the map becomes a dense, overwhelming sea of pins.
**Refusals Fit**: Strains "search is a finite tool curated through the engine" if not carefully constrained. Map pins must strictly represent the *curated survivors*, not the raw corpus.
**Architecture Fit**: A perfect fit for the existing Valhalla drive-time isochrones. It would require moving the MapLibre component to the Home screen (it is currently code-split strictly to the Detail screen).

### Paradigm 3: Progressive Disclosure (Where → What → When)
**Interaction Model**: A step-by-step wizard approach when the app is first opened, transforming into the context sentence once set. 
1. "Where are you starting from?" (Geocoder input)
2. "How far are you willing to drive?" (Slider)
3. "What kind of hike?" (Quick chips: View, Waterfall, Workout)
**Tradeoffs**: High friction for quick repeat queries. Slower time-to-value. Excellent for onboarding, terrible for habitual use.
**Architecture Fit**: Requires UI state machine changes, but no new backend capabilities.

---

## Part 4: The Curation-Intent Gap (Closing the "Why" Loop)

The most glaring omission in the UX becomes obvious when looking at the `RecommendationCard`. 

The engine uses a sophisticated `parse-intent` pipeline and `belief_update` store to score trails based on the user's highly specific natural language prompt (e.g., "cooler, quieter, good with Ruby"). However, **the UI presents the result identically to a standard database query**. 

The card displays standard stats (Distance, Ascent, Duration) and current conditions (54°F). It **completely fails to explain *why* the trail was chosen** or how it matches the user's specific context. If the app is a "cockpit-grade utility" functioning as an expert guide, it currently hands the user a route without any rationale.

**The Fix: The "Curator's Note"**
To solve this, the `CardVM` must expose the engine's matching rationale, and the UI must present it prominently on the card. 
- *Example*: A 1-sentence dynamically generated note directly below the trail name: *"The high ridge runs cooler, and the wide loop is ideal for Ruby. Crowds are lighter before mid-morning."*
This single UI addition closes the loop, proving the engine's intelligence and drastically reducing the user's decision fatigue.

---

## Part 5: The Spatial Disconnect (Map Critique)

Applying the same critical lens to the spatial UI reveals a tension between the app's "curation first" philosophy and the user's need for spatial context. 

### Map Interaction Breakdown
- **Location**: Maps exist *only* on the Detail view, pushed below the fold beneath text descriptions and stats.
- **Controls**: Housed in the document flow below the map, rather than floating over the canvas.
- **Interactions**: Fullscreen modal expansion, base layer switching (Topo/Imagery), and a brilliant bi-directional scrub (the map cursor syncs with the elevation profile).

### Friction Points & Analysis

1. **[HIGH] The Island Map (Zero Feed-Level Spatial Context)**
   The most jarring spatial friction is that the Home feed has no map. A user cannot see their curated options relative to one another or relative to their origin. To compare the location of three trails, the user must pogo-stick in and out of the Detail view for each one and construct a mental map in their head. The app assumes text ("Shenandoah") is sufficient spatial context for a decision. It is not.
   *Fix*: This strongly reinforces the need for **Paradigm 2 (Map-First Isochrone Picker)** or at minimum, a "Map View" toggle on the Home feed that plots the curated cards together.

2. **[MODERATE] The Map as an Afterthought (Hierarchy)**
   The code comments state that pushing the map below the fold honors the "decision first, navigation second" hierarchy. However, for outdoor routing, the map *is* a primary decision tool. Users need to know: Does it follow a highway? Is it entirely in a dense forest? Is it exposed on a ridge? Hiding this behind prose forces unnecessary scrolling.
   *Fix*: Elevate a static map snippet or a 3D terrain preview higher up in the Detail hierarchy, perhaps alongside the elevation glyph.

3. **[LOW] Document-Flow Controls in Fullscreen**
   When the map enters fullscreen, it operates as a modal overlay, but the controls (Topo, Locate Me) remain in the document flow below the map image. This artificially restricts the map's height and feels unpolished compared to native map experiences.
   *Fix*: In fullscreen mode, controls should float over the map canvas to maximize the spatial viewport.

### The Bright Spot
**[EXCELLENT] Bi-directional Elevation Scrubbing**
The synchronization between the elevation profile and the MapLibre cursor is a best-in-class interaction. It perfectly embodies the "cockpit-grade utility" vision, allowing a user to instantly see exactly where the steepest 15% grade occurs on the physical terrain. This interaction must be preserved in any redesign.

---

## Part 6: Deep UX Review (The Skipped Edges)

Looking beyond the core feed and maps, a deep dive into the peripheral interactions (`Outcome`, `Tuning`, and `FeedConditions`) reveals both friction points and excellent implementations of the product's core principles.

### 1. The Outcome Screen (The Black Box of Learning)
- **Current State**: The `Outcome.tsx` screen asks "How was it?" with a simple 3-face rating (Good, Okay, Rough). It writes this outcome to the backend to update the user's `belief_store`.
- **The Friction**: This creates a massive "Curation-Intent Gap" on the input side. If a user taps "Rough," the engine learns *something*, but the user has no idea what. Did the engine learn they hate distance? Ascent? That specific region? Hiking with Ruby? When the learning is a black box, the user cannot trust it.
- **The Fix (Explicit Hypothesis)**: The feedback loop must be transparent. When a user taps a face, the UI should explicitly state the hypothesis the engine is forming. *Example: "Noted. You seemed to struggle with the 1,500ft ascent today. I'll look for gentler climbs next time."*

### 2. The Tuning Sheets (Navigation Friction)
- **Current State**: `Tuning.tsx` uses a two-level modal sheet pattern. A user taps "When" on the main `AdjustSheet`, which pushes a second `PanelSheet` to pick "Tomorrow Morning".
- **The Friction**: Every single facet change requires 3 distinct taps (Open facet -> Pick value -> Close/Back to main sheet). If a user wants to change "When" and "Effort", it requires navigating a modal hierarchy. This is far too slow for a "cockpit-grade" utility.
- **The Fix (Surface Volatility)**: The engine's NLP prompt (the Omnibox) solves much of this, but for structured data, the top 2 most volatile facets (e.g., Effort, When) should be exposed directly on the Home feed as quick-toggles, bypassing the sheets entirely.

### 3. The "Near Me" Control (A Win for Honesty)
- **Current State**: The `NearMeControl` uses device geolocation to set the origin.
- **The UX Win**: This component perfectly executes the "source-or-silence" rule. If geolocation fails or permission is denied, it does not silently fail or fabricate an approximate location. It immediately surfaces an honest, calm error ("Location permission denied — pick a starting point below"). This is a textbook example of the product's trust principles in action.

---
### Ranked Recommendation & First Step

1. **Unified Intent Line (Omnibox)**: Best alignment with the product's calm, utility-first vision. Fast, zero dead-ends, leverages the existing NLP engine.
2. **Map-First Isochrone Picker**: Great for spatial thinkers and desktop, but carries a higher risk of turning into a generic map-app clone.
3. **Progressive Disclosure**: Too slow for a cockpit-grade tool.

**The Single Smallest First Step**:
Implement the **Unified Intent Line** by elevating the `parse-intent` free-text input out of the recessive `AdjustSheet` and placing it directly on the `Home` screen header. Couple this with the B001 geocoder seam to resolve arbitrary place names, finally killing the fixed `origins.ts` enum. This instantly unlocks the backend's power without a massive frontend rewrite.
