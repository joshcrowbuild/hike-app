# UX Review — Live Conditions on the Surface (2026-07)

*A design review of the LIVE rendered product after the condition-data wave (six sourced kinds × six per-kind states, water overlay, GPX export) landed on cards and Detail. The owner's prompt: "all this new data just kinda dumped into the UX and it needs some love." Findings are ordered by severity; each is tied to the product standard it violates and ends in a concrete recommendation. Four epic-shaped lanes close the doc.*

**Last verified:** 2026-07-12 · **Owner:** design review (point-in-time) · **Status:** FOR DESIGN REVIEW

---

## 1. Method

- **Surface reviewed:** the deployed frontend at `https://hike-app.vercel.app` (the Vercel origin in `render.yaml`'s CORS allowlist) against the live Render API — browsed **anonymously** (a supported, real product mode).
- **Viewports:** 390×844 @2x (phone — the primary dogfood surface) and 1280×800 (desktop). Headless Chromium via puppeteer; screenshots taken in-session (`home-mobile-1`, `detail-mobile-top/-map/-bottom`, `home-richmond-mobile`, `home-obx-mobile`, `detail-obx-caution`, `home-desktop`, `detail-desktop`). Each finding below carries a described-evidence note with the exact rendered text, which was captured verbatim from the live DOM.
- **States exercised:** three regions (Shenandoah/Front Royal — all-clear; Richmond — urban all-clear; Outer Banks/Ocracoke — active NWS Beach Hazards Statement + an AirNow outage), Home feed, card, Detail (map · elevation · conditions · character · sources), Tuning sheet, computed-style contrast probes, and a code spot-check of `frontend/src/screens/ConditionStates.tsx`, `cardParts.tsx`, `RecommendationCard.tsx`, `Detail.tsx`, `data/verdict.ts`, `styles.css`, and `orchestration/present.py`.
- **Standards judged against:** `docs/vision.md` (calm; pillar 4 "the tool scores, the human decides"; the six invariants), `docs/research/design-system-v0.1.md` (tokens, type scale, honesty primitives, §4.3 never-color-alone), the six-state silence vocabulary (CDP-02), and the shipped UX epics (019 lean card spine — PR #116; 020 legibility/reach — PR #123; 021 icon accents — PR #118) so nothing landed is re-proposed.

### What's working (keep it)

Credit first, because the foundation is genuinely strong and the fix is composition, not demolition:

- **The lean card spine (Epic 019) holds.** Verdict → dominant trail name → two decision facts → elevation glyph → one Now line. The trail is still the hero on an all-clear card.
- **The six-state primitive is right.** `ConditionStates.tsx` gives every state a distinct glyph + copy + treatment, never color alone (§4.3); `unavailable` routes through flagged `<Confidence>`; `not-fetched` is a dashed quiet ○; sr-only announcements ("Checked, nothing to flag:", "Unverified, verify before you go:") are systematically present.
- **A11y discipline is real.** Icons are `aria-hidden` with sr-only labels (Epic 021 pattern); 44px hit zones exist via the invisible `::before` extension (Epic 020) even where visible chrome is 30px; contrast probes pass AA — couldn't-verify terracotta `#9a4424` on paper ≈ 5.1:1, meta stamps `#5e636a` at 11px ≈ 5.7:1.
- **GPX export is discoverable** — a peer chip beside Save/Directions at the top of Detail, not buried.
- **The Tuning sheet is calm** — three rows + a phrase field, nothing else.
- **Detail is short** (~2000px on mobile) — scroll depth is not the problem; redundancy density is.

---

## 2. Findings (by severity)

### F1 · CRITICAL — Card and Detail disagree on the verdict for the same trail

**Evidence (screenshots `home-obx-mobile`, `detail-obx-caution`; Ocracoke, 2026-07-12).** The Outer Banks feed opens with a regional alert banner — *"weather alert: Beach Hazards Statement — NWS · JUST NOW"* — and directly beneath it, every card reads **"Good to go — conditions look clear."** Tapping Hammock Hills Trail, its Detail page says **"Caution — active weather alert: Beach Hazards Statement · NWS · JUST NOW."** Same trail, same minute, two verdicts.

**Why.** `frontend/src/data/verdict.ts` derives the verdict from `card.warnings`; the feed's regional alert renders as a feed-level banner and is not folded into the per-card warnings on Home, while Detail's payload does attach it — so the two surfaces derive opposite tones from what should be the same signal.

**Standard violated.** Vision pillar 4: *"a safety-critical overlay always takes the top slot"* — and, more fundamentally, the whole trust bet: the tool contradicting itself under stress is the single worst failure mode for a product whose pitch is "trust it under stress." The eval-metric even states it: *"a safety-critical overlay takes the top visual slot 100% of the time."* The banner sort of satisfies the letter (it is at the top of the feed); the Good-to-go cards beneath it break the spirit.

**Recommendation.** One verdict derivation, one signal set, both surfaces. Fold region-scoped alerts into every affected card's warning input (or derive the card verdict server-side alongside the feed), so a card can never say "Good to go" while its own Detail says "Caution." This is the first thing to fix; it is a correctness bug wearing a UX costume.

---

### F2 · CRITICAL — "conditions look clear" asserts a state that was never verified as clear

**Evidence (`home-obx-mobile`).** Card verdict line: *"Good to go — conditions look clear"*, rendered two lines above the card's own verified weather reading: *"✓ Showers And Thunderstorms Likely 77°F · NWS, just now."* Storms likely, hazard statement active — and the headline says "clear."

**Why.** `verdict.ts` step 3 falls back to the literal string `'conditions look clear'` whenever there's a verified reading but no merged enrichment `conditionValue` — regardless of what the reading says. "Clear" is a weather word; what the verdict actually means is "nothing blocking."

**Standard violated.** Source-or-silence in spirit (Invariant 1): the phrase is an unsourced editorial claim contradicted by the sourced fact beneath it. Compare the vision's north-star copy: *"Marginal — go if you start before noon"* — the verdict names its binding constraint; it never characterizes the sky on its own authority.

**Recommendation.** The go-verdict detail must either quote the verified reading ("Good to go — storms possible, nothing blocking") or claim only what was checked ("Good to go — nothing flagged across 6 checks"). Never "clear" as a default string. One-file fix; write the eval case with it.

---

### F3 · HIGH — The feed repeats identical region-scope conditions on all ten cards

**Evidence (`home-mobile-1`, `home-richmond-mobile`, `home-obx-mobile`).** Shenandoah, all ten cards carry, verbatim: *"✓ Mostly Cloudy 61°F · NWS, just now"* (±1°F card to card) and *"✓ Checked — nothing to flag: Fire (NASA · just now), Closures (NPS · just now)."* Richmond: the same pair, ten more times. Ocracoke adds a third identical line — *"Couldn't verify: Air quality"* — ten times, for what is one regional AirNow outage. Roughly **30–40% of every card's vertical height is condition metadata that is identical on every card in the feed.**

**Standard violated.** Vision pillar 4 names the exact failure: *"the most expensive documented failure across every high-stakes domain is not bad data but burying the critical fact in a wall of true-but-trivial ones."* When every card says the same thing, the eye learns to skip the condition block entirely — which is precisely where the one card that differs will someday put its warning. It also breaks calm (the feed reads as a status wall, not a set of trails) and the eval hook *"median actionable flags-per-trip ≤ 1."*

**Recommendation.** Scope conditions to their true granularity. Weather (one NWS zone), air (one AirNow region), fire/closure sweeps, and regional alerts are **region-scope facts**: state them once, at feed level, in a single quiet conditions ribbon under the curation header — with their source + stamp stated once. Cards then carry only **per-trail deltas** (a gauge, a closure on this trail, a microclimate difference) and otherwise stay silent about what the ribbon already said. Honesty is preserved — every fact still has its source and timestamp — it just stops being repeated ten times. (The compact six-state summary component already groups by state; this extends the same idea one level up, to the feed.)

---

### F4 · HIGH — Detail states each condition up to three times

**Evidence (`detail-mobile-top`, `detail-desktop`; Fox Hollow Trail).** The conditions block renders, in order: **(a)** four sentence lines — *"✓ Mostly Cloudy 61°F · NWS, just now / ✓ AQI 45 (Good) · EPA, just now / ✓ nearest gauge: S F SHENANDOAH RIVER AT RT 619 NR FRONT ROYAL, VA · USGS, just now / ✓ 10 nearby facilities · Recreation.gov, just now"*; **(b)** immediately below, a six-row coverage ledger — *"WEATHER ✓ reported · NWS · JUST NOW / AIR QUALITY ✓ reported · EPA · JUST NOW / FIRE ✓ checked — nothing to flag · NASA · JUST NOW / STREAMFLOW ✓ reported · USGS · JUST NOW / CLOSURES ✓ checked — nothing to flag · NPS · JUST NOW / PERMITS ✓ reported · Recreation.gov · JUST NOW"*; and **(c)** a Sources section at page bottom listing the same four providers a third time. Eleven metadata rows; every source name appears two or three times; "NWS · just now" appears three times on one screen.

The ledger's `reported` rows are the empty calories: *"WEATHER ✓ reported · NWS · JUST NOW"* sits directly beneath the line that already reported it. `Detail.tsx` renders `conditionLines` then always appends the full `<ConditionStates>` list; the code comment says present-rows "quietly confirm the lines above" — but confirmation of an adjacent line is duplication, not confirmation.

**Standard violated.** Design-system §7's own discipline: render the honesty primitives *"without clutter — the hedge is the honesty."* Vision pillar 1's proof describes the intended shape: *"a confidence chip that decomposes on tap"* — layered disclosure, not three flat statements.

**Recommendation.** Merge (a) and (b) into **one row per kind**: kinds with a value show the value in their row (`WEATHER — Mostly Cloudy 61°F · NWS · just now`); kinds with silence show their silence state exactly as today. One glyph, one source, one stamp per kind. Six rows total, each carrying real information; the state vocabulary (`reported`/`checked — nothing to flag`/etc.) survives as the row's *treatment*, not as its only content. The Sources section keeps its distinct job (full provider labels + origin ids like "NWS LWX 56,65") — it is the inspection layer, and the only place the long-form label should live.

---

### F5 · HIGH — Streamflow and permits lines dump data instead of answering

**Evidence (`detail-mobile-top`, all three regions).** The streamflow line reads *"✓ nearest gauge: S F SHENANDOAH RIVER AT RT 619 NR FRONT ROYAL, VA · USGS, just now"* — an ALL-CAPS gauge name wrapping two lines on a 390px phone, and **no flow reading at all**. The adapter fetches the reading — `orchestration/adapters/usgs_water.py` returns `latest_discharge_cfs` — but `orchestration/present.py::_body` renders only `monitoring_location`, discarding the number. The permits line reads *"✓ 10 nearby facilities · Recreation.gov, just now"* — which answers no question a hiker has ("do I need a permit?" is not "how many RIDB facilities are nearby?"). The north-star moment in the vision reads *"the streamflow at the one creek ford reads green."* Today it reads a shouted address.

**Standard violated.** This is the literal "data dumped into the UX" case: source-or-silence satisfied to the letter (source ✓, timestamp ✓) while the *fact* — the thing the source was called for — is missing. Pillar 2's proof promises live overlays that render a *reading*, not a station id.

**Recommendation.** Streamflow: render the discharge that is already fetched (`"12 cfs at Pass Run gauge · USGS · just now"`), title-cased, gauge name truncated to the recognizable part; distance-to-gauge is the honest hedge when the nearest gauge is far ("nearest gauge 9 mi away"). A vs-normal band (green/elevated) is a later, separate epic — it needs percentile data and its own honesty design. Permits: either answer the permit question from RIDB data or relabel honestly ("Recreation.gov facilities nearby: 10 — permit rules not yet checked" → which is a `not-fetched` for the *permit* fact, per CDP-02).

---

### F6 · MODERATE — Raw float precision reads as broken instrumentation

**Evidence (`detail-mobile-map`, every Detail page).** Elevation header: *"max 20.35806406360465%"* (Fox Hollow), *"max 1.4513825908586495%"* (Virginia Capital). The full 14-decimal float also lands in the sr-only summary sentence ("…steepest grade 20.35806406360465%."), so screen-reader users get all fourteen decimals read aloud.

**Standard violated.** Design-system §5's "values the user reads as data" contract assumes formatted data; a cockpit that shows fourteen decimals is a cockpit the pilot stops believing. Precision theater is the *inverse* honesty failure: it dresses a ~10m-DEM-derived estimate as impossibly exact.

**Recommendation.** One decimal ("max grade ~20.4%"), and the same rounding in the sr-only sentence. Trivial fix; ship it this week.

---

### F7 · MODERATE — The Character line contradicts the decision facts on the same screen

**Evidence.** Fox Hollow Detail: decision fact **"DISTANCE 3.0 mi"**; Character section: *"A **2.2-mile** out-and-back, climbing 278 ft — clear today."* Virginia Capital Trail: card + facts say **0.7 mi**; Character says *"A flat **0-mile** loop — clear today."* Hammock Hills: facts 3.3 mi, Character *"1.3-mile out-and-back."*

**Why (probable).** The Character sentence derives from route geometry (one-way length, rounded) while the decision fact carries the corpus/agency length — two length sources on one screen with no reconciliation, plus a rounding bug producing "0-mile." The "— clear today" suffix also re-imports the F2 "clear" copy problem into prose.

**Standard violated.** Eval hook: *"every verdict is re-derivable from its shown work."* Two different numbers for the same fact defeat re-derivation and quietly teach the user that numbers here are approximate.

**Recommendation.** One length SSOT per trail surface: Character must consume the same distance the decision fact shows (or explicitly disclose the difference: "2.2 mi one-way"). Kill the "0-mile" rounding. Drop "— clear today" from Character (the verdict owns that claim).

---

### F8 · MODERATE — Desktop-only map instructions and overlapping chrome on the phone

**Evidence (`detail-mobile-map`, 390×844).** Below the map: *"Use ⌘ + scroll (Ctrl + scroll on Windows) to zoom the map."* — rendered unconditionally (`TerrainMap.tsx:129`) on a touch phone with no ⌘ and no scroll wheel; the cooperative-gesture overlay text also sits in the DOM. Bottom-left of the map, the scale bar ("500 ft") overlaps the attribution line ("…ational Map: Topo · © OpenStreetMap contributors (ODbL)") into an unreadable collision. Six map chips (TOPO/IMAGERY/HILLSHADE/LOCATE ME/FULLSCREEN/DIRECTIONS) wrap into two rows, with DIRECTIONS duplicated from the header actions.

**Standard violated.** Mobile-first ergonomics (the owner dogfoods on the phone); design-system "calm, cartographic, matte" — colliding chrome is neither.

**Recommendation.** Gate the zoom hint on pointer type (hide on coarse pointers; MapLibre's cooperative-gestures already shows the two-finger message on touch). Separate scale from attribution (stack or opposite corners). Drop the duplicate DIRECTIONS chip from the map row.

---

### F9 · MODERATE — The three silences: right vocabulary, two practical soft spots

**Evidence.** The state model itself checks out live: **checked-clear** renders as a filled ✓ chip with calm copy + source + stamp; **couldn't-verify** renders through flagged Confidence in the terracotta signal (*"AIR QUALITY couldn't be verified right now"* — correctly source-less and stamp-less); **not-fetched** is a dashed muted ○ with "not checked here" (verified in code + Storybook; not encountered live — all six kinds currently always probe). Distinct glyph + copy + treatment, never color alone. This is the strongest part of the wave.

Two soft spots: **(a)** a region-wide outage renders as a per-card flagged line ×10 (Ocracoke's AirNow outage) — the honest flag becomes a loud wall, violating "honest ≠ loud" (the vision's consolidated-notification principle applies: one outage, one statement); folding into the F3 ribbon fixes this for free. **(b)** the compact-group glyph is `font-size: 0.7em` of a 0.76rem row ≈ **8.5px** — the ✓/○/– distinction the design leans on is sub-legible at arm's length on a phone, leaving copy to do all the work (copy does differ, so this is a soft spot, not a violation of §4.3).

**Recommendation.** (a) region-scope the outage statement with F3. (b) floor the state glyph at ~12px. Also rename the ledger's `reported` label (see F4/F5) — as a *state word* it is honest but vague; when the row carries the value it becomes unnecessary.

---

### F10 · LOW — New condition CSS reintroduces ad-hoc type sizes

**Evidence (`frontend/src/styles.css`).** The six-state block hand-types its scale: `.condition-states { font-size: 0.82rem }`, `.condition-state-kind { font-size: 0.68rem }`, `.condition-state-group { font-size: 0.76rem }`, glyph `0.7em` — none drawn from the semantic type tokens Epic 019 established (`--type-*`). Colors and fonts *do* use tokens (`var(--text-muted)`, `var(--font-family-mono)`).

**Standard violated.** Design-system §14 done-bar ("no literal sizes once migrated") and Epic 019 AC-19.2.1 ("no new hardcoded rems").

**Recommendation.** Snap the four sizes to existing type tokens (or mint `type.conditionState.*` in the DTCG source and regenerate). Fold into whichever lane touches this CSS first.

---

### F11 · LOW — Detail's kicker mislabels the page

**Evidence (`detail-mobile-top`).** Every Detail page opens with the kicker **"CONDITIONS"** above the trail name — but the page is the whole commitment view (facts, map, terrain, character, sources). The label under-describes the page and collides with the actual conditions block below. Epic 020's S20.4 gave Detail a real header ("Detail" + BACK); the kicker is a leftover.

**Recommendation.** Drop the kicker or repurpose it as the region/area line ("SHENANDOAH · FRONT ROYAL"), which the card shows but Detail currently loses.

---

### F12 · LOW — Small wrapping/rhythm breaks under real data widths

**Evidence.** Desktop Detail: the third decision fact wraps mid-token — *"~35 min ·"* / *"est."* (`detail-desktop`). Mobile card: the NWS long-phrase reading wraps the Now line to two lines (*"Showers And Thunderstorms Likely 77°F · NWS, just now"*), pushing card height and burying the checked-clear group. Mobile ledger: the right column wraps *"JUST"* / *"NOW"* mid-stamp with ragged two-column alignment (`detail-obx-caution`).

**Recommendation.** Let the duration fact's column fit its content (`min-content` guard or shorter copy "~35 min est."); allow the stamp to shrink (`white-space: nowrap` on the stamp, wrap before it); consider NWS short-forecast abbreviation only if it stays verbatim-faithful (otherwise wrapping is the honest cost).

---

## 3. Severity roll-up

| # | Severity | Finding | Standard |
|---|---|---|---|
| F1 | CRITICAL | Card says Good-to-go while Detail says Caution (same trail, same minute) | Pillar 4 · safety-top-slot |
| F2 | CRITICAL | "conditions look clear" default copy contradicts the sourced reading beside it | Invariant 1 (source-or-silence) |
| F3 | HIGH | Identical region-scope conditions repeated on all 10 cards | Pillar 4 (critical-fact burial) · calm |
| F4 | HIGH | Detail states each condition 2–3× (lines + ledger + sources) | §7 "hedge without clutter" |
| F5 | HIGH | Streamflow shows a gauge address, not a reading; permits count facilities | Pillar 2 proof · "data dumped" |
| F6 | MODERATE | 14-decimal max-grade float (visual + sr-only) | §5 data formatting · trust |
| F7 | MODERATE | Character mileage contradicts decision facts ("0-mile loop") | re-derivable verdicts |
| F8 | MODERATE | ⌘-scroll hint on touch; scale/attribution collision | mobile-first ergonomics |
| F9 | MODERATE | Outage flag ×10 per region; 8.5px state glyphs | honest ≠ loud · legibility |
| F10 | LOW | Six-state CSS hand-types its type scale | §14 · AC-19.2.1 |
| F11 | LOW | "CONDITIONS" kicker mislabels the Detail page | IA |
| F12 | LOW | Wrapping breaks (duration fact, Now line, ledger stamps) | rhythm/polish |

---

## 4. Proposed lanes (epic-shaped, PO-green-lightable)

**Lane 1 — One sky, one verdict: region-scoped conditions + verdict integrity (fixes F1, F2, F3, F9a) · size M (2–3 days).**
Split condition facts by true scope. Region-scope kinds (NWS zone weather, AirNow, fire/closure sweeps, regional alerts, region-wide outages) render **once** in a quiet feed-level conditions ribbon with their source + stamp; cards carry only per-trail deltas. Regional alerts fold into every affected card's verdict input so card and Detail derive from the same signal set and can never disagree. The go-verdict default copy stops saying "clear" — it quotes the reading or claims only "nothing flagged across N checks." Ships with an eval case: *feed banner alert ⇒ no Good-to-go card in that region*, and *card verdict == Detail verdict* on golden trips. Honesty-critical lane; brief must carry Invariant 1 and pillar-4 text verbatim.

**Lane 2 — The conditions block answers, once: Detail merge + real readings (fixes F4, F5, F9b/c) · size M (2–3 days).**
Detail's sentence lines and the six-row coverage ledger merge into **one row per kind**: value-bearing kinds show their value in the row (weather reading, AQI, **the discharge the USGS adapter already fetches but `present.py` drops**, permit answer or honest "permit rules not checked"), silence kinds keep their exact six-state treatment. One glyph, one source, one stamp per kind; gauge names title-cased and truncated; the `reported` label retires; state glyphs floored at ~12px; Sources section stays as the inspection layer (full labels + origin ids). Backend half is small and surgical (`present.py::_body` for water/permits); frontend half is composition inside `Detail.tsx`/`ConditionStates.tsx`.

**Lane 3 — Numbers that hold up (fixes F6, F7, F12) · size S (1 day).**
Round grades to one decimal everywhere (including sr-only sentences); make the Character line consume the same distance the decision facts show (or disclose "one-way"); kill the "0-mile loop" rounding; drop "— clear today" from Character; fix the duration-fact and stamp wrapping. Pure polish with outsized trust payoff — these are the details a cockpit-grade pitch is judged by.

**Lane 4 — Mobile map manners (fixes F8, F11, + F10 opportunistically) · size S (1 day).**
Pointer-aware zoom hint (hide ⌘-scroll advice on coarse pointers), un-collide scale bar and attribution, drop the duplicate DIRECTIONS map chip, retire or repurpose the "CONDITIONS" kicker as the region line, and snap the six-state CSS sizes to semantic type tokens while the file is open.

**Suggested order:** Lane 1 → Lane 2 (both touch condition composition; 1 is the safety fix) with Lanes 3 and 4 parallel-safe alongside either (disjoint files except `styles.css` token snapping, which rides in Lane 4).

---

*Point-in-time review; supersede rather than edit if the surface is re-reviewed after these lanes land. Screenshots live in the review session; the rendered text quoted above was captured verbatim from the live DOM on 2026-07-12.*
