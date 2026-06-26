# Screen-by-Screen Design Spec — `Home / Curation` v0.3

This revises `home-curation-prototype-spec-v0.2.md` after a panel critique (UX/UI, IA, Content, and the core user) found the v0.2 build to be **spec-compliant in letter, spec-violating in spirit**. v0.3 resolves the ambiguities that let that happen and makes the decisions explicit so the rebuild has a corrected contract.

## 0. Changelog — what changed from v0.2 and why

- **[C1] Ordering is now truly peer, not ranked.**
  - v0.2 said "lightly ordered" but the build crowned the first card visually and hard-sorted by score.
  - **v0.3 rule:** selection chooses *which* options appear; presentation renders them as **peers**. No "leading" card styling, no implied 1-2-3. Internal score decides inclusion only, never visual rank.

- **[C2] The card at rest is a complete decision unit. In-place expansion is removed.**
  - v0.2's expand drawer caused three failures: the whole card became an expand button (burying the real primary action), "Open Detail" sat two taps deep, and the reveal was a jarring instant DOM swap.
  - **v0.3 rule:** the at-rest card carries everything needed to *decide*. Tapping the card does one thing: **Open Detail**. Rich map/contour/profile lives on Detail. (This supersedes brief §7 "expansion reveals…"; place-making is redistributed — see C3.)

- **[C3] Place-making is redistributed across the flow.**
  - **v0.3 rule:** at rest = evocative place line + a compact terrain/elevation glyph (enough to read the *shape* of the day); Detail = full map, contour, profile. We get place at a glance without an in-place drawer.

- **[C4] Trust gets a typographic tier, not chromatic alarm — and it is no longer buried.**
  - v0.2 rendered a safety `caution` in the same grey weight as a parking tip, at the very bottom.
  - **v0.3 rule:** a present `caution` (verify-before-you-go) is promoted **one typographic tier** and placed beside the decision facts. Freshness stays quiet. The single accent color is reserved for *signal* (caution/verify), never for button chrome.

- **[C5] One primary input model. Free text is genuinely secondary.**
  - v0.2 stacked a free-text prompt on top of a 5-chip row — two equal, competing models, all shown at rest (a control panel up front).
  - **v0.3 rule:** the primary tuning surface is a **calm context sentence** ("Tomorrow morning · from Front Royal · with Ruby"). Tapping it opens tuning. Free text is a quiet secondary affordance, not a co-equal field. No chip tray at rest.

- **[C6] Copy is stripped of assistant theater.**
  - v0.2 narrated its own reasoning ("Biasing the set toward orientation…", "Pulled forward because it matches X without losing viability").
  - **v0.3 rule:** the surface never describes its own weighting. Fit copy is one human clause about the *hike*. No marketing slogans as headers.

- **[C7] Visual system is cartographic-matte, not glassmorphic.**
  - v0.2 reached for "premium" via blur, translucency, gradients, and big soft shadows — a trend, not the brief's cartographic intent.
  - **v0.3 rule:** matte paper base, ink text, hairline rules, terrain/contour motifs in the chrome, monospaced cartographic labels for data. No blur, no gradients-as-decoration, no glow shadows.

- **[C8] The core interaction has real physicality; no arbitrary default-open card.**
  - **v0.3 rule:** press/active states are first-class (mobile-first), transitions are tight (~120–160ms), and nothing is pre-expanded.

## 1. Global Frame

### Product mode
- **Mode:** `Curation`

### Product promise on this surface
- Show a **small, peer set** of hikes that are compelling, viable, and context-aware — each readable as a decision at a glance.

### Rules for the whole flow
- **[finite]** Never a feed.
- **[quiet]** No chat-shell energy; no self-narration.
- **[peer]** `3 or fewer`, presented as peers (C1).
- **[decidable-at-rest]** Each card is a complete decision unit (C2).
- **[progressive]** Tuning is one tap away, not spread across the surface (C5).
- **[signal-accent]** Color is spent only on trust signal (C4, C7).

## 2. Screen 1 — Home / Curation / Default

### Intent
- Orient in one glance; present a strong peer set; make the next tap obvious (Open Detail).

### Layout (top → bottom)
- **[top bar]** Minimal. Left: `Curation` wordmark/mode. Right: nothing, or one quiet affordance. No status pills, no environment labels.
- **[context sentence]** The frame setter and the **primary tuning entry** (C5). Reads as composed prose, e.g. `Tomorrow morning · from Front Royal · with Ruby`. Tappable; opens tuning.
- **[refine affordance]** A quiet secondary control for free text (e.g. a small `Refine` text-button that reveals an input). Subordinate by size and position (C5).
- **[recommendation stack]** Up to 3 **peer** cards. No emphasized first card.

### What is NOT on this surface at rest
- No chip tray (Origin/When/Effort/Party/Today as 5 visible buttons).
- No self-describing subtitle.
- No marketing headline.

### Header copy rules
- Literal and composed. The context sentence states the frame; it does not sell it.
- Bad (v0.2): `A smaller set. A clearer day.` / `Biasing the set toward orientation…`
- Good: the context sentence itself is the only framing text needed.

## 3. Recommendation Card — At Rest (the only card state)

### Intent
- Create desire through **place character** and let the user *decide* without expanding.

### Content order
- **[1. place line]** Evocative but precise; a sense of *somewhere*, not a tag dump.
  - Bad (v0.2): `High ridge, long views, open sky` (reads as keywords).
  - Good: `A high open ridge that earns its views fast.`
- **[2. identity]** Trail name · area · route shape.
- **[3. terrain glyph]** Compact elevation/route sparkline — the *shape* of the day at a glance (C3).
- **[4. decision row]** The go/no-go trio, equal weight, monospaced data:
  - **Drive** (from current origin)
  - **Effort shape** (distance + ascent, or a compact "miles · ascent")
  - **Condition value** — the *actual* live value, not "checked Nh ago" (e.g. `58°F · breezy · clear`).
- **[5. signal line]** Only if a `caution` exists: promoted one tier, placed here (not at the bottom), accent-marked (C4). e.g. `Verify creek crossings — running high.`
- **[6. freshness]** One quiet, low-tier line. e.g. `Conditions 48m old.`
- **[7. fit line]** One human clause, effect-first, about the hike (C6).
  - Bad (v0.2): `Pulled forward because it matches "ridge" without losing viability.`
  - Good: `Good with Ruby and short enough for a morning.`

### Primary action
- **Tap card → Open Detail.** Single, unambiguous (C2). No nested interactive elements inside the card's primary tap target.

### At-rest constraints
- **Do:** read as a complete, calm decision unit; expose the decision trio without interaction.
- **Do not:** hide the terrain shape; bury the caution; crown a winner; read like a feed/e-commerce/analytics widget.

## 4. (Removed) Recommendation Card — Expanded In Place

- **Removed in v0.3** (C2). Depth lives on Detail. Rationale: the in-place drawer inverted the primary action, created invalid nested buttons, and produced a jarring reveal. If a lightweight terrain peek is later desired, it must be a *distinct, secondary, clearly-affordanced* control with proper height animation — not the card's main tap.

## 5. Screen 2 — Tuning (entered from the context sentence)

Tapping the context sentence opens tuning. Each facet is a **focused sheet**, one concern at a time.

### Shared rules
- One concern per sheet; precision adjustment, not configuration.
- Changing a setting visibly reshapes the set on return.
- Free text ("Refine") is available here as a secondary path, never the headline.

### Facets
- **Origin** — current origin, default place, override.
- **When** — today / tomorrow / weekend × morning / afternoon / full day.
- **Effort** — easy / moderate / big day.
- **Party** — solo / Ruby / friends.
- **Today** — condition-sensitive tuning; readiness as an **explicit** toggle, never silent. When on, it reads as an inline statement of what it's doing — in plain terms, not system-speak.

## 6. Screen 3 — Tuned State

### Must visibly change
- Set reshapes (cards swap), context sentence updates, fit lines adapt, count may shrink.

### Design rule
- Tuning makes curation **more specific, not more busy**. Never cosmetic.

## 7. Screen 4 — Sparse Result (1 option)

- One strong option is a confident outcome, not a failure.
- Do not apologize, do not backfill with weak options.
- Offer a quiet "widen the frame" path only.

## 8. Screen 5 — Cautionary State (verify-before-you-go)

- Caution is **inline and promoted one tier** (C4), beside the decision facts — never a banner, never stoplight severity.
- Good: `Verify creek crossings — running high.` / `Closure info here is older than usual.`
- Bad: `WARNING`, `HIGH RISK`, red/yellow/green severity UI.
- Hierarchy: home = one promoted signal line; Detail = fuller context + sources.

## 9. Screen 6 — Trail Detail

### Intent
- Answer **"Can I actually do this today?"** — operational, viability-first.

### Content order
- **[1. viability summary]** drive · distance · ascent · duration · 1–2 go/no-go conditions (with real values).
- **[2. map / terrain]** full route, contour, elevation profile (the rich place-making moved here, C3).
- **[3. outing character]** why this place is compelling, in plain language.
- **[4. why it fits]** restrained, effect-first; never system-explaining.
- **[5. trust / sources]** freshness, source basis, verify-before-you-go nuance, fully inspectable.

### Page feel
- Less editorial than home; more operational; still quiet.

## 10. Content Model — 3 Seed Cards

Three distinct archetypes, each a complete decision unit.

- **Card A — Ridge / overlook:** clean strong option; exposed views; straightforward viability; carries a real condition value.
- **Card B — Forest / cooler / water:** contrast option; shade/creek; appealing in heat; **carries the seed `caution`** (creek crossings) to exercise C4.
- **Card C — Bigger day / more committing:** aspirational but plausible; longer drive/duration; drops out under the `Ruby` party constraint to exercise tuning.

## 11. Copy Rules (tightened)

### Home copy
- **Be:** concise, observational, place-aware, literal.
- **Avoid:** chirpy, salesy, "AI helper" voice, self-narration, slogans.

### Personalization copy
- **Use:** fit/effect language about the hike.
- **Never:** describe the system's weighting or defend its selection ("without losing viability", "pulled forward because…").

### Trust copy
- **Use:** real condition values + relative freshness; concise, promoted caution.
- **Avoid:** numeric confidence scores, over-labeled certainty, warning theatrics.

## 12. Visual System (new in v0.3)

- **Base:** matte paper (flat off-white), no gradient-as-decoration, no backdrop blur.
- **Ink:** high-contrast near-black primary text; a single restrained mid-grey for *truly* secondary text only.
- **Rules/edges:** hairline borders; terrain/contour line motifs allowed as quiet texture.
- **Accent:** one color, reserved for trust **signal** (caution/verify). Not on buttons, not on chrome.
- **Type:** structured grotesque for headings; **monospaced for data/labels** (cartographic, coordinate-like). No soft-humanist display type.
- **Shadow:** minimal/none; rely on borders and spacing, not glow.
- **Motion:** tight (~120–160ms), press/active states first (mobile-first); no float, no theatrical easing; nothing pre-opened.

## 13. Component Set

- `TopBar` (minimal)
- `ContextSentence` (primary tuning entry)
- `RefineAffordance` (secondary free text)
- `RecommendationCard` (single at-rest state; tap → Open Detail)
- `TerrainGlyph` (at-rest sparkline)
- `DecisionRow` (drive · effort · condition value)
- `SignalLine` (promoted caution)
- `FreshnessLine`
- `FitLine`
- `FocusedSheet` (per facet)
- `DetailView` (viability-first)

## 14. Acceptance Criteria (v0.3)

- **[a1]** Reads as curation of peers, not a ranked feed (C1).
- **[a2]** No chat-AI / self-narrating language anywhere (C6).
- **[a3]** Each card is decidable at rest — drive, terrain shape, and a real condition value are visible without interaction (C2, C3).
- **[a4]** Place feels primary and evocative, not a keyword dump (C3, C6).
- **[a5]** Tuning is one tap from the context sentence; the surface is not a filter tray (C5).
- **[a6]** Trust is subtle but legible: caution is promoted one tier and never buried; accent is signal-only (C4).
- **[a7]** Detail is viability-first with the rich terrain (C3, §9).
- **[a8]** Visual world is cartographic-matte, not glassmorphic (C7); core interaction has real physicality (C8).

## 15. Build Order

- **Step 1** — Re-found the visual tokens (matte cartographic) in `styles.css`.
- **Step 2** — Rewrite the data model + copy (place lines, condition values, fit lines; remove self-narration).
- **Step 3** — Rebuild Home: context sentence + refine; peer stack; complete at-rest cards (terrain glyph, decision row, promoted signal).
- **Step 4** — Wire tuning sheets from the context sentence.
- **Step 5** — Rebuild Detail (viability-first, rich terrain).
- **Step 6** — Verify build + re-run the panel check against §14.
