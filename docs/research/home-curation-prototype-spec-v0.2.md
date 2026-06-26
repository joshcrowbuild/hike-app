# Screen-by-Screen Design Spec — `Home / Curation` v0.2

This is the build-facing version of the brief: concrete enough to prototype without pretending we’ve already solved every token or component API.

## 1. Global Frame

### Product mode
- **Mode**
  - `Curation`

### Product promise on this surface
- **Promise**
  - Show a **small, highly selected set** of hikes that feel compelling, viable, and context-aware.

### Rules for the whole flow
- **[finite]**
  - Never feels like a feed.
- **[quiet]**
  - No chat-shell energy.
- **[selective]**
  - `3 or fewer` recommendations at a time.
- **[tunable]**
  - Controls are available, but not dominant at rest.
- **[inspectable]**
  - Detail deepens by interaction, not by dumping information upfront.

## 2. Screen 1 — Home / Curation / Default

### Intent
- **Primary job**
  - Orient me quickly and present a strong starting set.

### Layout
- **[top bar]**
  - Minimal.
  - Left: product/mode label.
  - Right: one quiet utility affordance at most.
  - No heavy nav.

- **[hybrid header]**
  - Compact context summary plus secondary input.
  - This is the “frame setter,” not a filter tray.

- **[recommendation stack]**
  - Vertical stack of `up to 3` cards.
  - Lightly ordered.
  - First card gets mild emphasis only.

### Header content blocks
- **[context line]**
  - Examples:
    - `From Front Royal`
    - `Saturday morning`
    - `Solo + Ruby`
    - `Moderate`
  - These should read like a composed summary, not a row of raw chips.

- **[secondary text input]**
  - Placeholder tone:
    - `Something cooler`
    - `A quieter hike`
    - `Good with Ruby`
  - Visually subordinate to context summary.

- **[quick tuning row]**
  - Affordances:
    - `Origin`
    - `When`
    - `Effort`
    - `Party`
    - `Today`
  - Compact and tactile.
  - No exposed mega-filter state.

### Recommendation stack behavior
- **[count]**
  - 1 to 3 cards only.

- **[ordering]**
  - There is a sequence, but avoid explicit ranking language like:
    - `#1`
    - `Best match`
    - `Top result`

- **[scroll posture]**
  - Finite stack.
  - No endless loading pattern.
  - No “more like this” on the first pass.

## 3. Recommendation Card — At Rest

### Intent
- **Primary job**
  - Create desire through **place character**, while staying grounded enough to compare options.

### Card content order
- **[1. place cue]**
  - Short, atmospheric but precise.
  - Example shape:
    - `High ridge, long views, open sky`
    - `Cool forested climb with water nearby`
  - Should evoke outing character, not marketing copy.

- **[2. identity block]**
  - Trail name
  - Area/region
  - Route shape if relevant

- **[3. compact practical row]**
  - Drive
  - Miles
  - Elevation
  - Time
  - Keep it compact and scannable

- **[4. fit line]**
  - One sentence max.
  - Effect-first personalization.
  - Example shape:
    - `Good fit for a moderate half-day with Ruby`
    - `A cooler option for a warm afternoon`

- **[5. subtle state cue if needed]**
  - One condition/freshness cue only if meaningful.
  - Example shape:
    - `Trail condition checked 2h ago`
    - `Creek crossings worth verifying`
  - Quiet, inline, never badge soup.

### At-rest constraints
- **Do**
  - feel layered
  - feel precise
  - imply depth

- **Do not**
  - lead with giant imagery
  - read like an e-commerce card
  - read like a feed item
  - read like an analytics widget

## 4. Recommendation Card — Expanded In Place

### Intent
- **Primary job**
  - Let the user inspect one option without fully leaving home.

### Reveal order
- **[1. terrain / map block]**
  - First reveal.
  - Small but meaningful terrain context:
    - route shape
    - contour/elevation profile
    - trail orientation
  - This is the main place-making device.

- **[2. practical viability block]**
  - Clear planning facts:
    - drive time
    - hike distance
    - ascent
    - expected duration
    - one or two relevant “today” conditions

- **[3. why it fits block]**
  - Slightly fuller rationale.
  - Examples:
    - `Works well for a shorter Saturday morning`
    - `Likely to stay cooler than the ridge options`
  - Still effect-first, not system-explaining.

- **[4. trust / source block]**
  - Lowest on the expanded card.
  - Visible, but secondary.
  - Contains:
    - freshness
    - source presence
    - cautionary note if relevant

### Interactions
- **Tap card**
  - expands

- **Tap map/terrain**
  - deepens or transitions to detail

- **Tap source/trust cue**
  - opens deeper inspection only if included in prototype

- **Primary CTA**
  - `Open detail`

### Motion
- **Feel**
  - tight
  - tactile
  - slightly mechanical precision
- **Avoid**
  - floaty unfolding
  - soft lifestyle easing
  - theatrical expansion

## 5. Screen 2 — Tuning Panels

Each quick control from the header opens a **focused sheet**, not a generalized filters screen.

### Shared rules
- **One concern at a time**
  - each sheet solves one tuning problem

- **Short, controlled**
  - should feel like precision adjustment, not configuration

- **Immediate effect**
  - changing a setting should visibly reshape curation on return

### A. Origin Sheet
- **Contains**
  - current origin
  - saved/default place
  - simple override/search
- **Goal**
  - redefine the planning frame quickly

### B. When Sheet
- **Contains**
  - today
  - tomorrow
  - weekend
  - morning / afternoon / full day
- **Goal**
  - shape viability and outing type

### C. Effort Sheet
- **Contains**
  - easy
  - moderate
  - big day
- **Goal**
  - tune exertion without pretending precision math is the interface

### D. Party Sheet
- **Contains**
  - solo
  - Ruby
  - other party shapes later
- **Goal**
  - apply meaningful constraints simply

### E. Today Sheet
- **Contains**
  - condition-sensitive tuning
  - readiness toggle if present in prototype
- **Rule**
  - readiness must read as an explicit choice, not silent personalization

## 6. Screen 3 — Home / Curation / Tuned State

### Intent
- **Primary job**
  - Show that tuning materially changes the options.

### What must visibly change
- **[set reshapes]**
  - cards reorder or swap
- **[context summary updates]**
  - header reflects new frame immediately
- **[fit lines adapt]**
  - rationale language changes with tuning
- **[option count may shrink]**
  - sparse but strong is acceptable

### Design rule
- **Do not**
  - make tuning feel cosmetic
- **Do**
  - make curation feel more specific, not more busy

## 7. Screen 4 — Home / Sparse Result

### Intent
- **Primary job**
  - Prove that having only `1` compelling option can still feel confident and designed.

### Behavior
- **If only one result**
  - do not apologize
  - do not frame as failure
  - do not immediately backfill with weak options

### Content treatment
- **Primary card**
  - slightly more room
  - stronger viability context
- **Secondary support**
  - quiet prompt to widen the frame only if needed

## 8. Screen 5 — Home / Cautionary State

### Intent
- **Primary job**
  - Show how the system expresses “verify-before-you-go” without sounding alarmist.

### Content rule
- **Caution belongs inline**
  - never as a big warning banner on home

### Example treatments
- **Good**
  - `Creek crossing conditions worth verifying`
  - `Closure info is older here than usual`
- **Bad**
  - `WARNING`
  - `HIGH RISK`
  - stoplight severity UI

### Hierarchy
- **Home**
  - subtle cue only
- **Expanded / Detail**
  - fuller context

## 9. Screen 6 — Trail Detail

### Intent
- **Primary job**
  - Answer: **Can I actually do this today?**

### Content order
- **[1. viability summary]**
  - drive
  - length
  - ascent
  - duration
  - one or two go/no-go conditions

- **[2. map / terrain]**
  - route understanding
  - elevation profile
  - terrain character

- **[3. outing character]**
  - reinforce why this is compelling as a place

- **[4. why it was selected]**
  - fit summary
  - context-aware but restrained

- **[5. trust / source detail]**
  - freshness
  - source basis
  - any verify-before-you-go nuance

### Page feel
- **Less editorial than home**
  - more operational
  - still elegant
  - still quiet

### Primary action
- **For prototype**
  - likely no true “commit” flow needed
  - the main point is inspection quality

## 10. Content Model for the 3 Seed Cards

Use three clearly different outing archetypes.

### Card A — Ridge / overlook
- **Role**
  - clean, obvious strong option
- **Place character**
  - exposed, views, clear outing identity
- **Viability**
  - straightforward

### Card B — Forest / cooler / water
- **Role**
  - contrast option
- **Place character**
  - shade, cover, creek/waterfall feel
- **Viability**
  - appealing for warmer or lower-energy conditions

### Card C — Bigger day / more ambitious
- **Role**
  - aspirational but still plausible
- **Place character**
  - more consequential outing
- **Viability**
  - slightly less convenient or more committing

## 11. Copy Rules

### Home copy
- **Should be**
  - concise
  - observational
  - restrained
  - place-aware

- **Should not be**
  - chirpy
  - salesy
  - “AI helper” voice
  - overly explanatory

### Personalization copy
- **Use**
  - fit/effect language
- **Avoid**
  - overt self-modeling language on home

Example:
- **Prefer**
  - `A better fit for a shorter day`
- **Avoid**
  - `Based on your historical behavior and inferred preference profile`

### Trust copy
- **Use**
  - relative freshness
  - concise caution
- **Avoid**
  - scores
  - over-labeled certainty
  - warning theatrics

## 12. Component Set For Prototype

These are the minimum components I’d expect in Option 2.

### Core
- **`TopBar`**
- **`ContextSummary`**
- **`TuningChip`**
- **`SecondaryPromptInput`**
- **`RecommendationCard`**
- **`PracticalRow`**
- **`FitLine`**
- **`TrustCue`**
- **`TerrainPreview`**
- **`DetailHeader`**
- **`FocusedSheet`**

### Structural variants
- **`RecommendationCard.Collapsed`**
- **`RecommendationCard.Expanded`**
- **`RecommendationStack.Default`**
- **`RecommendationStack.Sparse`**
- **`RecommendationCard.Cautionary`**

## 13. Prototype Acceptance Criteria

We should consider Option 1 successful if the spec supports a prototype that:

- **[a1]**
  - feels like curation, not a feed

- **[a2]**
  - avoids generic chat-AI form language

- **[a3]**
  - makes `3 or fewer` options feel sufficient

- **[a4]**
  - makes place feel primary without becoming vague

- **[a5]**
  - lets tuning feel powerful without becoming a search UI

- **[a6]**
  - keeps trust subtle on home

- **[a7]**
  - makes detail feel viability-first

## 14. What We Build Next

For Option 2, implement:

- **Step 1**
  - scaffold `frontend/`

- **Step 2**
  - build the mobile-first `Home / Curation` shell

- **Step 3**
  - implement the 3 seed recommendation cards and one expanded state

- **Step 4**
  - add focused tuning sheets

- **Step 5**
  - add one `Trail Detail` route/view
