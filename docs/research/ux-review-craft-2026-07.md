# UX Review — Craft: Readability · Usability · Visual Aesthetic (2026-07)

*A harsh design review of the LIVE deployed product at the craft layer: rendered type in practice, spacing rhythm, affordances, wayfinding, state feedback, data-viz honesty, microcopy. This is the companion to `ux-review-conditions-2026-07.md` (PR #174), which owns the honesty/composition of the condition data — its 12 findings (verdict contradictions, feed repetition, condition triplication, decimal floats, wrapping breaks) are **not** re-litigated here; where a defect below shares a root with one of theirs, the cross-reference is explicit. Every finding carries a measured value or a code line, the standard it violates, and a concrete fix. Three fix lanes close the doc.*

**Last verified:** 2026-07-13 (reviewed live overnight 2026-07-12→13) · **Owner:** design review (point-in-time) · **Status:** FOR DESIGN REVIEW

---

## 1. Method

- **Surface:** `https://hike-app.vercel.app` against the live Render API, browsed anonymously. Several build lanes are changing this UI concurrently; this reviews the deployment as it stood tonight.
- **Viewports:** 390×844 @2x (phone — primary, owner is phone-first) and 1280×800. Headless Chromium via puppeteer; screenshots `craft-home-mobile`, `craft-detail-top/-map/-bottom`, `craft-tuning-sheet`, `craft-origin-sheet`, `craft-obx-feed`, `craft-home-desktop`.
- **Measurement discipline:** every type size, gap, color, and hit-rect below is a **computed style or bounding rect pulled from the live DOM** (`getComputedStyle`, `getBoundingClientRect`), not an impression. Code citations are from `main` as deployed.
- **Walk:** cold first load → feed scan → card → Detail (map · elevation · conditions · GPX) → back (scroll restore) → Tuning sheet → origin change → Outer Banks feed → second Detail → desktop pass.
- **Standards:** `docs/vision.md` (calm utility), `docs/research/design-system-v0.1.md` (§5.2 type scale, §6.1 space scale, §14 done-bar), the shipped Epic 019 (lean card spine: "2–3 decision facts") and Epic 021 (icon accents) intent, and general craft canon (WCAG, 44px targets, sane number formatting).

### Credit where due (measured, not courtesy)

- **Color discipline is real.** Exactly three text inks render on the Home feed — `#16191d` ×92, `#3c424a` ×41, `#5e636a` ×33 — all three are the tokens. No stray gray anywhere. This is rarer than it sounds.
- **Press/focus states exist everywhere.** `:active → surface-press` on card/context/facet/chips; `:focus-visible` rings on every interactive class, ink not accent. Measured, not assumed.
- **The 44px hit extender is correctly built** — `::before { inset:50%; width/height:max(100%,44px); translate(-50%,-50%) }` on chips, back, facet rows.
- **Back restores feed scroll** (opened card at scrollY 3000, returned to scrollY 3000) and the feed is cached (`anon-feed-cache`), so back is instant.
- **The staged loading copy is genuinely good** — "Reading conditions…" → "Still checking conditions…" → "Waking the server — this can take up to a minute…" — honest, calm, escalating. (See H1 for why most first-time users never see it.)

---

## 2. Findings (by severity)

### C1 · CRITICAL — The origin picker is physically unusable: most of it renders off-screen with no way to scroll to it

**Evidence (`craft-origin-sheet`, both viewports).** Adjust → From opens a "Starting point" bottom sheet listing **35 origins**. Measured live: the sheet is **2,110px tall** inside a `position:fixed; inset:0; align-items:flex-end` overlay, with `max-height: none` and `overflow-y: visible` at every level of the chain (`.un0hxi2` sh 2076/ch 2076 · `.un0hxi1` sh 2108/ch 2108 · overlay 844/844 — **no scrollable element exists**). Bottom-anchored, the sheet's top sits at **y = −1,278px**. Consequences, all verified live:

- The sheet header — **Back and Done — is 1,261px above the viewport** and cannot be reached by touch.
- The first ~20 origins are unreachable. **"Front Royal" — the current default — sits at y = −577px on desktop and further off-screen on the phone.** A user cannot re-select their own default.
- Selecting a reachable origin applies immediately (good) but the sheet **stays open with no visible dismiss**: the scrim is fully covered by the sheet, Done is off-screen, and swiping doesn't scroll the sheet — it **scrolls the feed behind it** (`window.scrollBy` moved the document with the dialog open; the scroll lock the component's own comment promises is not holding for this case). On a phone, tapping "From" is a **dead end**.

**Why.** `frontend/src/components/Sheet/Sheet.css.ts:35–54` — the `sheet` style has no `maxHeight` and no `overflowY`. The component was built for the three-row Adjust sheet and never confronted with a list taller than the viewport. The comment at the top of the file says React Aria provides "the … scroll lock that the bespoke prototype sheet lacked" — the live behavior contradicts the comment.

**Standard violated.** Mobile-first ergonomics on the primary dogfood surface; Epic 020's whole premise (every control reachable) — a 44px hit area is meaningless at y = −1,278. This is the single worst interaction in the product: the only path to the app's other regions is broken.

**Fix.** (1) `maxHeight: 'calc(100dvh - 2 * <inset>)'` + `overflowY: 'auto'` on the sheet (or scroll only the list slot so header stays pinned); scroll the selected origin into view on open. (2) Then fix the list itself: 35 flat alphabetical rows mixing towns, state parks, beaches, and "Potomac (MD)" with no grouping, no search, no recents — group by region (the feed already knows Shenandoah/Richmond/Outer Banks) and pin the current + recent picks on top. (1) is an emergency patch; (2) is the actual design.

---

### H1 · HIGH — First contact with the product is an unstyled "Loading…" string — for up to a minute

**Evidence (`craft-home-mobile` cold load).** A cold visit renders a bare, top-left, default-sans **"Loading…"** on an empty canvas — no wordmark, no skeleton, no explanation. `frontend/src/data/PlannerProvider.tsx:70–75` returns `<p className="app-loading">Loading…</p>` while `/regions` resolves — and **`.app-loading` has no rule in any stylesheet** (grep: zero hits), so it renders as raw UA-styled paragraph text. Because this gate wraps the entire app, the carefully staged loading system in `Home.tsx` ("Reading conditions…" → "Waking the server — this can take up to a minute…") and the skeleton cards **cannot render until `/regions` returns** — which, on a Render cold start, is exactly the multi-second-to-minute window where reassurance matters most. The best loading copy in the app is unreachable during the only long wait.

**Standard violated.** First-run comprehension (a stranger learns nothing in the app's first N seconds); calm utility (the calmest thing on a long wait is a designed one); the product's own staged-loading design intent, which this gate short-circuits.

**Fix.** Replace the provider gate's fallback with the same shell the app renders anyway (topbar + wordmark + skeleton cards + the staged copy, driven by elapsed time, not by which fetch is pending). One file, plus moving `LOADING_COPY` up a layer. Ship it before anyone else's first visit.

---

### H2 · HIGH — The feed can't be compared: every card carries exactly one decision fact

**Evidence (measured on all 10 Shenandoah and all 10 Outer Banks cards).** `decisionItemsPerCard = [1,1,1,1,1,1,1,1,1,1]` — every card renders **DISTANCE only**. Detail carries three facts (distance · ascent · duration), so the data exists. Epic 019's spine explicitly specifies the card shows "**2–3 decision facts**" (S19.1); the conditions companion review, days ago, still described "two decision facts" on the card. Meanwhile each card is **409px tall** — at 844px, **1.9 cards per screen** — so comparing the "10 OPTIONS" means scrolling ~4,200px to collect ten distance numbers, because nothing else on the cards differs (the condition block is region-identical — companion F3 — and the glyph lies, H3). The feed is a ranking you must take on faith, not a comparison you can make.

**Standard violated.** Epic 019 S19.1 (2–3 facts) — the shipped spine has regressed or been half-emptied; vision pillar 4 ("the tool scores, the human decides" — deciding requires comparable facts); the card's whole reason to be 409px tall.

**Fix.** Restore ascent + duration as facts 2–3 (they're in the VM — Detail proves it), subject to H4's correction first. If a deliberate lane removed them, it removed the card's decision function with them; re-litigate that decision with this measurement on the table.

---

### H3 · HIGH — The terrain glyph is normalized decoration posing as data: 13 ft of dune renders identically to 278 ft of ridge

**Evidence (measured on every card, both regions).** The card glyph's polyline spans **y 3→43 on every single card** — the amplitude is normalized to the full 44px frame regardless of actual relief. Hammock Hills Trail (**ascent 13 ft**, per its own Detail) renders the same dramatic mountain profile as Fox Hollow Trail (**278 ft**). One OBX card ("Path Loop B Showers") flatlines only because its profile is a constant. Additionally `preserveAspectRatio="none"` stretches 288×46 → 322×44, distorting stroke geometry directionally.

On a card whose only decision fact is distance (H2), the glyph is the *only* visual differentiator between trails — and it actively misinforms: a flat coastal boardwalk and a mountain climb are indistinguishable at feed-scan speed. This is the inverse of the product's honesty discipline applied to pixels: the sourced numbers are honest, the picture fabricates drama.

**Standard violated.** Design-system §8 `TerrainGlyph` as a data-bearing primitive ("values the user reads as data"); vision's cockpit thesis — a cockpit instrument with auto-ranging gain and no scale is not an instrument.

**Fix.** Scale glyph amplitude against a shared reference (per-feed max relief, or an absolute ft-per-px band with a visible floor for near-flat trails — a flat trail should *look* flat; that's the information). Keep `preserveAspectRatio` meaningful or draw at final aspect. If real relief scaling is deferred, the honest interim is to drop the glyph, not to keep the fiction.

---

### H4 · HIGH — The decision facts contradict each other on their own row: "3.3 mi" beside "~15 min · est."

**Evidence (Hammock Hills Detail, live).** Facts row: **DISTANCE 3.3 mi · ASCENT 13 ft · DURATION ~15 min · est.** — that is a 13 mph hiking pace. Fox Hollow: **3.0 mi · ~35 min** (5.1 mph). No walker does this; every user who knows their own pace now distrusts all three numbers.

**Why (code-confirmed).** `api/app.py:805 _estimated_duration_min` integrates the grade-aware pace over the **elevation profile's one-way ground distance**, while the DISTANCE fact carries the full (out-and-back) trail length. One-way time is being displayed beside round-trip distance on the same row. This is the same two-geometries root as companion **F7** (Character-line mileage vs. facts) surfacing in a worse place: *inside* the decision facts themselves, the row the whole product funnels toward.

**Standard violated.** The eval hook "every verdict is re-derivable from its shown work" — here the shown work refutes itself; Rule 7's spirit (an estimate must at least be an estimate *of the displayed quantity*).

**Fix.** One geometry SSOT for the fact row: compute duration over the same length the DISTANCE fact shows (double the profile integral for out-and-back, or state "one-way" on both). Add a pace sanity eval (0.5–4 mph band) so no future fact row can ship a 13 mph hike. Coordinate with companion Lane 3 (F7) — same fix family, one lane.

---

### M1 · MEDIUM — The type "scale" is 12 rendered sizes, five of them within 2.3px of each other

**Evidence (computed, Home at 390px).** Distinct rendered font sizes on one screen: **8.5, 9.92, 10.24, 10.88, 11.2, 12.16, 12.88, 13.6, 14.4, 15.2, 16, 20.8 px** — twelve sizes where the design-system §5.2 scale defines **eight**. The micro-label tier alone renders at five near-identical sizes: NOW 9.92 · OPEN DETAIL 10.24 · ADJUST/10-OPTIONS 10.88 · wordmark/fact-label 11.2 · state-group 12.16. None of these five is distinguishable from its neighbor at reading distance — they are five maintenance burdens delivering one apparent size, sloppily.

The rot is in both layers: `frontend/tokens/primitive.json` has grown to a **13-step size ramp** including `fact-label 0.7rem`, `supporting 0.72rem` — two "steps" 0.02rem apart, minted per-element instead of snapping to the documented scale (token-laundering: the letter of AC-19.2.1, the death of its point). And `frontend/src/styles.css` still contains **70 `font-size` declarations of which only 7 reference a token** — literals at 0.6, 0.62, 0.64, 0.68, 0.74, 0.78, 0.85, 1.15em, 1.25em… (Companion F10 flagged this pattern in the six-state CSS; measurement shows it is the norm across the file, not the exception.)

**Standard violated.** §5.2 (eight steps), §14 done-bar [d3] "no raw size literals", [d4] "no ad-hoc values" — by the contract's own definition of done, **the design system does not currently exist** on this surface.

**Fix.** Collapse the primitive ramp back to the documented eight steps (kill `fact-label`/`supporting`/`verdict`/`condition` as separate primitives; they're roles, map them to steps), then a mechanical pass snapping the 63 literal declarations. Add the lint §10 promised ("no raw values — enforced by review, later by lint") so it can't regrow.

---

### M2 · MEDIUM — Nothing sits on the 4px spacing grid

**Evidence (measured, first card).** Internal block gaps top-to-bottom: **21 · 11 · 11 · 17 · 11 · 17 px**. Card padding **16.8px**. Card-to-card gap **14px**; `.card-stack` gap **13.6px**. Chip hit-inset **14.875px**. The §6.1 scale is 4/8/12/16/20/24/32 — **not one measured value lands on it**. The fractional pixels (13.6 = 0.85rem, 16.8 = 1.05rem) show these are hand-typed rem values, not tokens. The result is a rhythm that is always *almost* consistent — 11 vs 17 vs 21 reads as noise, not hierarchy, and it's why the card feels hand-assembled rather than set.

**Standard violated.** §6.1 space scale; §14[d4].

**Fix.** Snap in the same mechanical pass as M1: 11→12, 17→16, 21→20, 13.6/14→16, 16.8→16. One afternoon, and every margin stops arguing with every other margin.

---

### M3 · MEDIUM — The product never says its own name: "CURATION", "BROWSING", "Detail", and a title tag that says "Prototype"

**Evidence.** The persistent top-left mark is **"CURATION"** (11.2px mono) — a mode noun, not a product. Top-right: **"BROWSING"** (9.92px), whose meaning ("Browsing anonymously — not signed in") exists only in its `aria-label`; sighted users get an unexplained gerund, and there is **no sign-in affordance anywhere** — a status with no action. The Detail page's title slot says **"Detail"** — the name of the UI container, information-free. And the document title shipping to every browser tab and bookmark is **"Adventure Planner — Curation Prototype"** — the word *Prototype* is live in production chrome. A stranger landing here cannot answer "what is this app?" from anything on screen; the closest thing to a proposition is the tuning sentence "Weekend morning · Shenandoah · from Front Royal", which is excellent — and unsupported by any identity around it.

**Standard violated.** Epic 020 S20.4 (a persistent quiet wordmark; real page titles); first-run comprehension; basic shipping hygiene (the tab title).

**Fix.** Pick the working name; put it in the wordmark slot and the `<title>`. Repurpose the Detail title slot as region context ("SHENANDOAH · FRONT ROYAL" — which Detail currently loses; companion F11 proposed the same for the kicker — do it once, in one slot). Give BROWSING its action (Sign in) or demote it until auth exists.

---

### M4 · MEDIUM — Tuning amnesia: every visit resets to Front Royal

**Evidence.** Selected Ocracoke; context updated; hard reload → **"Weekend morning · Shenandoah · from Front Royal"**. localStorage holds `adventure-planner:anon-feed-cache` — *keyed by the tuning* — but the tuning itself is React state only. The infrastructure to persist the preference exists and is used to cache the feed for a preference it then forgets. Cost compounds with C1: re-selecting your region means re-entering the broken sheet, every session.

**Standard violated.** Personal utility (a tool that forgets its one user's one setting); "calm" (repeat ceremony is friction).

**Fix.** Persist the anon tuning triple + phrase to localStorage beside the cache it already keys. ~20 lines.

---

### M5 · MEDIUM — The elevation chart has no scale in either axis — it cannot be read, only admired

**Evidence (`craft-detail-bottom`).** The Detail chart SVG contains **zero `<text>` elements**: no elevation ticks, no distance axis, no start/end markers, no direction indicator for an out-and-back. The header gives totals (↑278 ft ↓239 ft) but the *chart* answers none of the questions a profile exists for: where is the climb, how long is it, is it front-loaded? (Whether the big right-side rise is 50 ft or 500 ft is unknowable from the graphic — H3's same disease at Detail scale.) Under it, the sole caption is **"usgs–3dep"** — a lowercase raw pipeline identifier where a human label belongs. The header row also fractures its own numbers: "↑ 278 / ft" wraps value and unit onto separate lines in a ragged four-column layout.

**Standard violated.** §5.1's "cartographic voice" and the cockpit thesis — cartography is exactly the discipline of labeled scale; a profile with no axes is a sparkline blown up to chart size and given a section of its own.

**Fix.** Three quiet mono labels: min/max elevation on y, total distance on x, a start dot. Title-case the source into the existing source-line pattern ("USGS 3DEP"). Keep value+unit atomic (`white-space: nowrap`) in the header.

---

### M6 · MEDIUM — The document outline is flat: no h1 on Home, section labels that aren't headings

**Evidence.** Home renders **no h1 or h2 at all** — card names are `h3`s floating without ancestors; the wordmark is a `span`. Detail has exactly one heading (`h1` trail name); "Map & terrain", "Character", "Sources" are styled `span` kickers — a screen-reader rotor sees a one-item outline on a four-section page. Meanwhile the card is one giant `<button>` (356×347px) wrapping the h3, so trail names are unselectable/uncopyable on desktop.

**Standard violated.** WCAG 1.3.1/2.4.6 craft; the a11y discipline the components otherwise maintain (sr-only labels are systematically present — the *structure* layer was skipped).

**Fix.** Home: wordmark → `h1` (or a visually-hidden h1), "10 options · Shenandoah" → `h2`. Detail: section kickers → `h2`s (styling unchanged). Cheap, mechanical.

---

### L1 · LOW — Microcopy seams: double-prefixed alerts, a lowercase banner, incantation bullets

**Evidence.**
- The OBX banner reads, to a screen reader, "**Regional alert: weather alert:** Beach Hazards Statement — NWS · 2m ago" — two prefixes, both saying "alert". Visually it *starts lowercase* ("weather alert: …") and orphans an em-dash before the line break. The one safety-critical string in the app is its least-edited sentence.
- Sources section: "· single authoritative source" is appended to **3 of 4 bullets** — an incantation, not information; say it once or only flag the exceptions.
- The refine placeholder "cooler · quieter · good with Ruby" is charming for the household and opaque to anyone else — fine *if* this stays single-user; note it as intentional or genericize.

**Fix.** A one-hour copy pass with a rule sheet: sentence-case sentences, one prefix per statement, no repeated qualifier suffixes, no dangling punctuation before wraps.

---

### L2 · LOW — Skeleton draws a card that no longer exists

**Evidence (`craft-home-desktop`, cold).** The skeleton silhouette renders **two side-by-side fact bars**; the real card renders one fact (H2). AC-19.3.1 ("skeleton element set == card element set; no reflow on swap") is violated in both directions — today it's the *skeleton* promising the richer card the spec asked for. Fix alongside whichever way H2 resolves.

---

### L3 · LOW — Desktop is a 432px phone column on a 1280px canvas

**Evidence.** Card width 432px, shell 464px, viewport 1280 — 64% of the canvas is empty margin, on a product whose Detail contains a map and an elevation profile that would actually use the width. Acceptable posture for a calm single-column utility *this quarter*; noted so it's a decision, not a default. No fix requested now.

---

## 3. Severity roll-up

| # | Severity | Finding | Standard |
|---|---|---|---|
| C1 | CRITICAL | Origin sheet renders 1,278px off-screen; no scroll, no reachable Done; default origin unselectable; scroll leaks to feed | Sheet contract · mobile-first |
| H1 | HIGH | Cold start = unstyled bare "Loading…" gate; staged copy + skeletons unreachable during the only long wait | first-run · calm |
| H2 | HIGH | 10/10 cards carry one decision fact (DISTANCE); 409px cards, 1.9/screen — feed can't be compared | Epic 019 S19.1 · pillar 4 |
| H3 | HIGH | Terrain glyph amplitude-normalized (y 3→43 on every card): 13 ft == 278 ft | §8 TerrainGlyph · cockpit thesis |
| H4 | HIGH | "3.3 mi · ~15 min · est." — one-way duration beside round-trip distance (api/app.py:805) | re-derivable facts · Rule 7 |
| M1 | MEDIUM | 12 rendered type sizes; 13-step primitive ramp; 70 font-size decls, 7 tokenized | §5.2 · §14[d3][d4] |
| M2 | MEDIUM | Card gaps 21/11/17, pad 16.8, stack 13.6 — zero values on the 4px grid | §6.1 |
| M3 | MEDIUM | No product name anywhere; "CURATION"/"BROWSING"/"Detail"/"…Prototype" title | Epic 020 S20.4 · first-run |
| M4 | MEDIUM | Tuning resets on reload (cache is keyed by the tuning it forgets) | personal utility |
| M5 | MEDIUM | Elevation chart: zero axis labels; caption "usgs–3dep"; value/unit wrap | cartographic voice |
| M6 | MEDIUM | No h1 on Home; Detail sections aren't headings; card text unselectable | WCAG 1.3.1/2.4.6 |
| L1 | LOW | "Regional alert: weather alert:" double prefix; lowercase banner; ×3 "single authoritative source" | microcopy discipline |
| L2 | LOW | Skeleton silhouette ≠ card silhouette (two fact bars vs one) | AC-19.3.1 |
| L3 | LOW | Desktop = phone column; 64% empty canvas | noted, not urgent |

---

## 4. Fix lanes (PO-green-lightable)

**Lane A — Unbreak the doors: sheet mechanics + memory + first paint (C1, M4, H1) · size S (1 day).**
`Sheet.css.ts` gets `maxHeight` + internal scroll with a pinned header, selected-row scroll-into-view, and a scroll-lock regression test (open sheet → `window.scrollBy` must not move the feed). Origin list grouped by region with current/recent pinned. Tuning triple persisted to localStorage beside the feed cache. The `PlannerProvider` gate swaps its bare `<p>` for the app shell + staged loading copy. Small, surgical, and it fixes the two worst minutes of the product: the first one and the one where you try to change region.

**Lane B — A feed you can decide from: facts, glyph, geometry (H2, H3, H4, L2) · size M (2–3 days).**
Cards regain ascent + duration (per Epic 019's own spec), duration is recomputed over the same geometry as the displayed distance (backend `_estimated_duration_min` consumers; add the 0.5–4 mph pace sanity eval), the terrain glyph adopts a shared relief scale so flat renders flat, and the skeleton mirrors the final card. **Coordinate with conditions-review Lane 3 (F7)** — the two-geometries root is one fix; land it once.

**Lane C — The system actually exists: type/space snap + identity + chart labels (M1, M2, M3, M5, M6, L1) · size M (2 days).**
One mechanical sweep: primitive size ramp collapsed to the documented eight steps, the 63 literal font-sizes and off-grid gaps snapped to tokens, and the lint the design-system contract already promised (§10) turned on. Riding along in the same files: wordmark/title/Detail-slot identity fixes, heading structure, the three elevation-chart axis labels, and the microcopy rule-sheet pass. Exit criterion is §14's own done-bar: no raw size/space literals in component CSS.

**Order:** Lane A first (it unblocks dogfooding other regions at all), then B and C in parallel (disjoint files except trivial `styles.css` overlap).

---

## 5. Verdict

This UI is a well-tokened sketch wearing a design system as a lanyard: the palette discipline, press states, hit extenders, and honesty vocabulary are genuinely excellent bones — and then nothing sits on them straight. Twelve type sizes and zero on-grid spacings on the flagship screen mean the system's own definition-of-done fails on contact with production; the feed's 409px cards each carry exactly one comparable fact plus an elevation glyph that renders 13 feet of dune with the same drama as 278 feet of ridge; the fact row pairs a round-trip distance with a one-way duration and asks you to trust both; the product never states its own name but does ship "Prototype" in the tab title; and the single path to every other region is a bottom sheet whose Done button renders 1,261px above the screen. None of this is expensive to fix — that's the indictment: these are one-afternoon-to-two-day defects sitting on top of infrastructure most teams never build, which means the gap here isn't capability or taste, it's that nobody has yet held the shipped pixels to the standard the repo's own documents wrote down.

---

*Point-in-time review; supersede rather than edit if re-reviewed after these lanes land. All measured values captured from the live DOM overnight 2026-07-12→13; screenshots live in the review session.*
