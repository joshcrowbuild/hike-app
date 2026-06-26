# UX Assembly Plan v1 — screens, flows, and the build that makes them feel-able

**Status:** DRAFT for review · **Date:** 2026-06-26
**Author:** UI/UX lane
**Purpose:** Decide *which* screens and flows we can now assemble, ground each in **what the backend actually provides today**, and lay out an implementation that lets the destination UX be *felt* tonight while throwing away as little code as possible.

> Reading order: this plan sits on top of `home-curation-prototype-spec-v0.3.md` (Home/Detail/Tuning contract), `outcome-card-ux.md` (post-hike loop + honesty primitives), `design-system-v0.1.md` (tokens + owned components), and `ui-brief-v0.2.md` (product stance). It does not restate them; it sequences them into a buildable whole.

---

## 0. Persona-review revisions (BINDING — these override anything below them)

A six-lens adversarial review (personas Josh / Carter / Ruby-advocate / Anonymous, plus NNG heuristics and a calm-utility+honesty guardian) ran against the draft. The following changes are **accepted and binding on the implementation**. Where the older prose in §3–§7 conflicts, this section wins.

**R1 — Provenance is a first-class VM dimension; mock never wears the costume of verified fact.** *(CRITICAL ×3 — Josh, NNG, honesty-guardian)*  Every fact-bearing value in the VM carries `provenance: 'live' | 'mock' | 'sample'`. The default card is the **honest-thin** card (only what `/plan` really returns: name, distance, condition lines with `source`+`confidence_level`, warnings). Enrichment that has **no live source** (mock condition values, freshness, fit line, ascent/duration, terrain geometry) must be **visually + structurally distinguishable** from sourced facts — it renders demoted and/or under a visible **"sample data"** affordance, and the `Confidence`/`Staleness` components **refuse to render a confident tier over non-live provenance**. A fabricated `58°F · breezy · clear` may never sit in the decision row indistinguishable from a verified condition line. *Degradation that is invisible to the viewer is concealment, not disclosure.*

**R2 — Readiness is a hard FILTER applied after ranking, never a rank penalty.** *(CRITICAL — honesty-guardian; echoed by Josh, Ruby)*  The legacy `readinessPenalty()` in `data.ts` (which subtracts from score) is **removed**, not quarantined. The mock implements readiness as a gate over the already-ranked set, disclosing **"N hidden · show anyway"** (reversible), and **never reorders survivors**. A test asserts readiness-on only *removes* cards, never *reorders* them. Rationale copy is **effect-first and trail-facing** ("Showing easier options — you turned on tune-to-today"), never a body diagnosis ("your recovery is low"). Off by default, never silent. When a fresh reading exists, the affordance may surface as a single quiet, dismissible, one-tap line in the feed rather than a buried toggle — but the toggle-on-but-inert (stale/no reading) state shows its **"showing the full feed, nothing filtered"** disclosure *visibly*, not collapsed.

**R3 — No fabricated delta question.** *(CRITICAL — honesty-guardian; echoed by Josh, NNG)*  The backend never generates a `delta_question`, so the outcome card **stops at one face + the Ruby toggle** and ships **no delta question** tonight. The conditional-delta branch defaults to never-shown; the happy path must be complete and satisfying without it. (When a real Curator prediction exists — backend ask #1/#2 — the delta returns, gated behind a genuine prediction.)

**R4 — IA is Home-centric, not a three-tab platform.** *(CRITICAL Josh; MODERATE NNG, honesty, anonymous)*  There is **one center of gravity: Home**. The post-hike nod **finds the user** — a single pending outcome surfaces quietly at the **top of Home** on next open (per `outcome-card-ux` §1.2), not a "Trips" tab you navigate to. **Trips** is demoted to a thin "log a hike I forgot / the one un-logged recent hike" surface, never a reverse-chron stream. **Memory** is demoted from co-equal nav to a **quiet on-demand affordance** (reached from the outcome flow's "why?" or a small profile entry) — `ui-brief` §9 forbids the belief layer becoming a headline self-modeling dashboard. No persistent equal-weight Home·Trips·Memory tab bar.

**R5 — Thread viewer scope + Phase-2 type slots through the seam now (cheap tonight, expensive later).** *(CRITICAL ×2 — Carter)*  (a) Every `PlannerClient` method takes an explicit `ScopeContext { viewerId, grantedIds }` (tonight always `{ viewerId:'josh', grantedIds:[] }`; anonymous = `{ viewerId:'anonymous', grantedIds:[] }`), mirroring the backend's `owner_scope = (owner_id = $viewer OR owner_id IN $granted)`. (b) `BeliefVM` gains `owner` (whose overlay) and a nullable `sharing` slot (null tonight; later `shared-with` / `received-from`, the request-then-approve hook). (c) The subject axis is **`self | dependent | member`** (Ruby = dependent, a real second member = member — *distinct kinds*, never conflated). (d) Correction controls key off `owner === viewer` (received conclusions are read-only). (e) `OutcomeVM` models companionship as a **list of companion refs** `{kind: 'dependent'|'member'}` (default `[]`/`[ruby]`), not a bool. (f) `ReadingVM`/`useReadiness` is shaped so the result can represent a **group gate** (aggregate rationale from N members) even though N=1 tonight. None of this adds P2 UI; it stops the corner being painted.

**R6 — Ruby's constraint is a disclosed GATE, not a silent score drop.** *(CRITICAL ×2 — Ruby-advocate)*  Ruby's hard constraint (off-leash / max-distance / scramble / heat ceiling) is modeled as an explicit gate with a reason, **distinct from any soft party-fit**. Excluded candidates are disclosed via a VM `setAside: { name, reason, restorable }[]` channel rendered like readiness's "N set aside · show anyway" ("Old Rag's scramble isn't a Ruby hike"). **Default party = `solo`** so the canonical solo→Ruby reshape is visible (Card C drops, disclosed). The same constraint object that gates the feed is the one shown in the belief store (editing it there changes what the party facet sets aside).

**R7 — The anonymous path is explicit, tested, and never a teaser.** *(CRITICAL ×2 — Anonymous)*  Promoted from "implicit" to a real slice in PR-B. With empty scope: the **fit line is omitted** (or a world-fact clause — no phantom "you"); **taste re-rank is a no-op** (inclusion = viability/proximity only); the **context sentence is neutral** (no "from Front Royal · with Ruby" shown to a stranger — origin is asked/coarse, party defaults solo, no named dependent); the **readiness affordance is absent** (no watch, its absence is correct). Home/Detail render from **one** implementation; the only difference is `scope = empty` (asserted by test). The **on-ramp** is a calm, declinable invitation shown **only** where a personal concept is invoked (tapping a gated destination) — never an interstitial, Home banner, locked/blurred tab, or count-tease; declining keeps the world fully usable. Acceptance: `a-anon1` usable peer set with no sign-in and no personal narration; `a-anon2` a `/trail/:id` deep-link resolves with no prior feed; `a-anon3` no locked/blurred/teaser chrome anywhere; `a-anon4` on-ramp declinable, world stays usable. Add Playwright screenshots of anonymous Home + anonymous deep-link.

**R8 — Error taxonomy + recovery copy are first-class (not a generic "error").** *(CRITICAL — NNG H9)*  The VM carries `error: { kind: 'offline'|'timeout'|'server'|'auth'|'partial'|'empty' }` with a plain-language, blame-free recovery action per kind (retry / widen / sign-in / dismiss-and-continue-degraded). **Partial failure** (some condition lines verify, some don't) shows the verified lines and discloses the gap — it never collapses the whole card. "Try again" is specified (idempotent re-fetch, visible retry state).

**R9 — "Widen the frame" is one proposed action, not a trip back through tuning.** *(MODERATE — Josh, NNG)*  The empty/sparse state proposes the obvious single relaxation with one tap ("nothing easy nearby today — show moderate too?"), because the app knows the frame. Manual tuning stays for when the user *wants* to steer, never as the only escape from empty. Sparse reads **confident, never apologetic**; empty reads **honest absence**; both carry identical widen wording with differing tone.

**R10 — Confidence/Staleness component-contract precision.** *(MODERATE/MINOR — NNG, honesty)*  The non-numeric **dot** encoding is allowed **only** in the belief store, must always be **paired with the confidence word** ("fresh" / "a guess"), and **never exposes the underlying float** (no `0.62`, no tooltip). On the feed, **`flagged` triggers the `Signal` treatment on that line but never demotes the card's position** (Rule #2 — uncertainty ≠ low quality); a test asserts a flagged card is not ranked below a stated-only card. The three confidence tiers map to the same visual treatment on every surface (the dot encoding being the single documented exception).

**R11 — Honesty on fully-mock surfaces (Detail sources, Memory beliefs, Outcome measured-block).** *(MODERATE — honesty)*  Detail does **not** fabricate a multi-source provenance list — it reuses the **real** per-line `source`+`confidence_level` from `/plan` (the one real provenance we have) or shows an honest "full source inspection lands when trail detail is wired." The Memory store and the Outcome measured-block are seeded **only from data the user actually produced in-session**, or are **clearly labeled sample data about a sample person** — never invented facts/receipts posed as learned truth about Josh. The degrade-and-disclose **"partial episode / dead battery"** copy pattern (source-or-silence on our *own* record) is promoted into **P1** so watch-free is felt, not just asserted.

**R12 — Small calm-utility fixes.** Pre-fill the Ruby outcome toggle from the selected plan's party facet (the common case needs zero extra taps). Trips shows the logged face quietly when present and **nothing** when absent (no "not yet" inbox/badge that reads as a to-do). `useRoute` history contract: **sheets do not push history** (Escape/scrim/back closes them; browser Back leaves the screen); **routes do push**; verify browser + mobile Back against every screen/sheet. Light-touch H10: a one-time dismissible orienting line on first Home open; empty states double as documentation.

> **Net effect on tonight's build:** PR-B and PR-C remain the non-negotiable core, but they now carry the provenance dimension (R1), the readiness-as-filter fix (R2), the scope/Phase-2 slots (R5), the Ruby gate + set-aside (R6), the anonymous slice (R7), and the error taxonomy (R8) from the start — all cheap type-shape decisions that are expensive to retrofit. The outcome card ships without the fake delta (R3); the IA stays Home-centric (R4).

---

## 1. North star (the destination app, in one breath)

A **calm, private, agentic outdoor-intelligence utility**: open it, see *three or fewer* genuinely-viable hikes for **this exact moment, for me and Ruby**, each live-verified under **source-or-silence**; tap one to answer *"can I actually do this today?"*; go; afterward tap **one face** so it quietly learns — with a **legible, editable memory** you can inspect and correct, and **watch data as enrichment, never a dependency.** It scales from an **anonymous world-browser** → a **personal single-user overlay** → a **private-by-default household** that shares *derived conclusions, never raw substrate*.

We are mid–**Phase 1** (personal intelligence). The engine spine (Scout→Verifier→Curator), live adapters, the graph overlay, the belief-update pipeline, and the device seam exist. The **frontend** is a single-file prototype of the Home-curation loop on 100% static mock data.

---

## 2. Backend reality — what the UI can stand on today

The honest inventory (from `api/app.py`, `api/schemas.py`, the orchestration modules). **This is the constraint that shapes every screen below.**

| Capability | Status | What's real | What the UI must mock / seam |
|---|---|---|---|
| **Feed / `POST /plan`** | 🟡 partial | Ranked `cards[]`: `canonical_id`, `name`, `distance_mi` (crow-flies), `lines[]` = pre-rendered condition prose each with `source` + `confidence_level` (`stated`/`hedged`/`flagged`), `warnings[]`, feed `notices[]`. Scout→Verifier→Curator + live probes + taste re-rank are wired. | All rich card vocabulary: place line, area, route shape, ascent, duration, effort, tags, terrain/elevation geometry, the "why it fits" sentence, a merged single condition value. |
| **Sources / provenance** | 🟢 real | Per-line `source` + `confidence_level` (from freshness·authority·corroboration). **The one place the API exceeds the prototype.** | Nothing — render it faithfully (the prototype currently under-uses it). |
| **Drive time** | 🟡 partial | When Valhalla resolves, a drive line is folded into `lines[]` as prose ("~28 min drive (45 km) …"); degrades with a feed notice. | A *structured* minutes field and a per-named-origin matrix — neither exists (origin is lat/lon only). |
| **Trail detail** | 🔴 mock | `canonical_id` is returned. | Everything else: there is **no `GET /trail/{id}`**. Character prose, profile/terrain geometry, duration, ascent, multi-source list. |
| **Outcome logging** | 🟡 partial (blocked) | `POST /episode/{id}/outcome` persists rating 1/2/3 + optional reflection; idempotent; ownership-scoped; enqueues belief updates. | **Blocker:** no HTTP way to *create* or *list* episodes (they're FIT-CLI-created), and the backend never *generates* a `delta_question`. So the loop can't run end-to-end without episode create/list endpoints. |
| **Readiness / watch** | 🔴 mock | Internals exist (belief pipeline, device seam). | **No HTTP surface.** No Body Battery / readiness value in any response (Epic 007 is BACKLOG). Entirely client-mock. |
| **Identity / household / auth** | 🔴 mock | Only a fail-closed dev guard (`viewer_id` + `X-Dev-Viewer-Secret`). | No login/session/signup/household/member/grant endpoints. All auth + member + party identity is mock. |
| **Adjust / tuning** | 🔴 mock | Free-text `query` (mechanical intent parse) + `lat/lon` + `k`. | Structured facets (origin/when/effort/party/today/readiness) have **no wire fields**; they must be folded into `query` or carried as mock hints. No per-facet fit scores exist server-side. |

**Two consequences that drive the architecture:**

1. **The real card is *prose + provenance*, not typed facts.** A 1:1 swap from the mock `Trail` model is impossible. We need a **view-model (VM) adapter layer** that both a mock source and the HTTP source can satisfy — written once, screens depend only on it.
2. **The destination design is legitimately richer than the API** (the v0.3 spec *wants* the terrain glyph, decision trio, fit line). So the rich fields become **optional enrichment in the VM that degrades when absent** — which is exactly the app's own *source-or-silence / degrade-and-disclose* ethos made structural. Tonight the mock supplies enrichment so the destination UX is feel-able; when the backend grows those fields, the same screens light up with no rewrite.

---

## 3. Architectural spine (the throwaway-minimizer)

Everything visual is built **once** against a stable seam. This is the single most important decision in the plan.

```
            screens/components  ─────────────┐  depend only on the VM
                                              ▼
   ┌──────────────────────── view-model (VM) ───────────────────────┐
   │  FeedVM { query, cards: CardVM[], notices[], status,            │
   │           setAside: SetAside[], error?: { kind } }   ← R6,R8     │
   │  CardVM { id, name, distanceMi, conditionLines: LineVM[],       │
   │           warnings[], enrichment?: CardEnrichment }             │
   │  LineVM { text, source, confidence: 'stated'|'hedged'|'flagged',│
   │           provenance: 'live'|'mock'|'sample' }       ← R1        │
   │  CardEnrichment? { placeCue, area, routeShape, ascentFeet,      │
   │           durationHours, effort, tags[], fitLine, conditionValue,│
   │           profilePath?, terrainPath?, freshness, caution?,      │
   │           provenance: 'live'|'mock'|'sample' }       ← R1        │
   │  SetAside { name, reason, restorable }               ← R6        │
   │  BeliefVM { …, owner, subject:'self'|'dependent'|'member',      │
   │             sharing: null, provenance }              ← R5,R11    │
   │  OutcomeVM { …, companions: {kind}[] }               ← R5        │
   │  ReadingVM { groupRationale, members:[…] }  (N=1)    ← R5        │
   │  ScopeContext { viewerId, grantedIds }  threaded     ← R5        │
   └────────────────────────────────────────────────────────────────┘
        ▲                                   ▲
        │ adapters                          │
   MockPlannerClient                  HttpPlannerClient
   (canned data shaped EXACTLY        (fetch() the real FastAPI;
    like the API + enrichment;         inert until backend runs;
    quarantines the throwaway          maps FeedResponse→VM,
    scoring engine)                    drops enrichment it can't supply)
```

- **Port:** `interface PlannerClient { plan(input): Promise<FeedVM>; getCard(id): Promise<CardVM|null>; recentEpisodes(): Promise<EpisodeVM[]>; recordOutcome(episodeId, body): Promise<OutcomeVM>; beliefs(): Promise<BeliefVM[]>; readiness(): Promise<ReadingVM> }`. The method **signatures and DTOs mirror the real API** (`PlanRequest`/`FeedResponse`/`OutcomeBody`/`OutcomeResponse` transcribed in `src/data/api.ts`).
- **Selection:** a `PlannerProvider` React context picks mock vs. http by `import.meta.env.VITE_USE_MOCK` / `VITE_API_BASE_URL`. Swapping is a one-line wiring change; tests inject the mock.
- **Async from day one:** screens consume `useFeed()` / `useCard()` / `useReadiness()` hooks returning `{ status: 'loading'|'ready'|'empty'|'error', data, error }` even though the mock resolves instantly — so loading/empty/error states exist *before* the network lands (no second rewrite).
- **Facets translate at the seam, not in components:** an `originCoords` map (named origin → lat/lon) replaces the drive-time table; a `buildQuery(tuning)` folds when/effort/party/today/prompt into `PlanRequest.query`. Components keep using `TuningState` unchanged. The mock honors the structured hints; the HTTP source serializes them into `query`.
- **Quarantine the throwaway:** the ~370-line client scoring engine (`scoreTrail`/`selectTrails`/…) moves *behind* `MockPlannerClient`. No screen imports it. When `/plan` is authoritative it is deleted wholesale; nothing else changes.
- **Navigation becomes real but owned:** a tiny dependency-free `useRoute` hook syncs a small route enum to the URL (`/`, `/trail/:id`, `/trips`, `/trips/:id/outcome`, `/memory`, `?gallery`) so Detail/Outcome survive reload and the anonymous path is deep-linkable. No router dependency (matches the owned-component ethos).

**What is permanent vs. throwaway after this plan:**
- *Permanent:* the VM, the port, `api.ts`, both adapters' interfaces, every screen/component, the hooks, the router, the honesty primitives. 
- *Throwaway (quarantined, deletable in one commit):* the canned mock dataset + the client scoring engine. Even these double as **test fixtures**.

---

## 4. Information architecture & navigation

Five destinations, calm and flat (no deep nav trees — this is a utility, not an app-as-platform):

**Revised per R4 — one center of gravity, not a three-tab platform:**

```
  ┌─────────────────────────────────────────────────────────┐
  │  Home / Curation     (/)            ← THE home; one glance│
  │     ├ pending nod    (top of Home)  ← the outcome FINDS you│
  │     ├ Trail Detail   (/trail/:id)   ← "can I do this?"    │
  │     └ Tuning sheets  (overlay)      ← progressive tuning  │
  │  Outcome card        (/trip/:id/outcome) ← one tap, from  │
  │                                       the pending nod      │
  │  Trips (thin)        (/trips)       ← only "log one I      │
  │                                       forgot"; not a stream│
  │  Memory (on-demand)  (/memory, /:id)← quiet affordance,    │
  │                                       NOT a co-equal tab   │
  └─────────────────────────────────────────────────────────┘
   No persistent equal-weight tab bar. Home is the single
   destination; Outcome surfaces ON Home; Memory is reached
   from the outcome flow's "why?" or a small profile entry.
   Anonymous: Home + Detail only, rendered identically (scope
   = empty); gated destinations open the calm on-ramp (R7),
   never a locked tab.
```

Navigation is **flat and reversible**; sheets are for *adjustment within a screen* (and do **not** push history — R12), full routes for *moving between concerns* (these push). This matches NNG's "match between system and the real world" + "user control and freedom" (every screen has an obvious back; nothing traps).

---

## 5. Screen-by-screen plan

Each screen lists **purpose · data sourcing (real/mock) · states · honesty primitives · persona note**. Priority: **P0** build tonight · **P1** strong-if-time · **P2** scaffold/later.

### 5.1 Home / Curation `(/)` — **P0**
- **Purpose:** orient in one glance; a peer set of ≤3 cards; obvious next tap (Open Detail). (v0.3 §2)
- **Data:** `useFeed(tuning)` → `FeedVM`. **Real:** name, distance, condition lines + per-line source/confidence, warnings, notices. **Mock-enrichment:** place line, terrain glyph, decision-trio labels, fit line, freshness, caution.
- **States:** loading (calm, no skeleton-jank — a quiet "Reading conditions…"), ready (≤3 peers), **sparse** (1 strong option, confident, "widen the frame" path — v0.3 §7), **empty** (no candidates: honest "nothing holds under this frame" + widen), **error** (live-adapter/network down: degrade-and-disclose, never a dead end), **notices** (feed-level disclosures rendered as a quiet line, e.g. "Drive times unavailable this run").
- **Honesty:** per-line confidence tier (stated/hedged/flagged); promoted **Signal** for any caution/`flagged` line beside the decision facts; freshness quiet.
- **Persona:** Josh's daily glance; the Anonymous browser sees the same world feed (empty viewer scope).

### 5.2 Recommendation Card (at rest) — **P0**
- **Purpose:** decidable at rest; one tap = Open Detail (v0.3 §3, C2). Peers, never a crowned winner (C1).
- **Data/degradation:** if enrichment present → full prototype card (place·glyph·trio·signal·freshness·fit). If only real `/plan` → honest-thin card: name, distance, the confidence-leveled condition lines, warnings. **Both are valid renderings of the same VM** — this is the degrade-and-disclose seam visible at the component level.
- **Honesty:** `confidence_level` styles each condition line (stated = plain ink; hedged = secondary + hedge wording; flagged = the accent **Signal** treatment). Accent is signal-only (C4/§11).

### 5.3 Trail Detail `(/trail/:id)` — **P0**
- **Purpose:** "can I actually do this today?" — viability-first (v0.3 §9).
- **Data:** `useCard(id)`. **Real:** name, distance, condition lines + sources/confidence, warnings. **Mock-enrichment:** ascent/duration, elevation profile + terrain SVG (render-skip when geometry absent), character prose, why-it-fits, full source list.
- **States:** loading, ready, error, **not-found** (deep-link to a card no longer in scope → honest "this trail isn't in your current set" + back to Home — fixes the current in-memory-lookup orphan bug).
- **Honesty:** fuller verify-before-you-go context + inspectable sources (the deeper tier of the same vocabulary).

### 5.4 Tuning (sheets) — **P0 (keep, re-wire)**
- **Purpose:** progressive tuning from the context sentence; one concern per sheet (v0.3 §5).
- **Data:** pure UI over `TuningState`; **translated at the seam** (origin→coords, rest→query). Changing a facet re-runs `useFeed` and the set visibly reshapes (v0.3 §6).
- **Honesty:** the **Today** sheet's readiness Toggle is explicit, off by default; when on it states *in plain language* what it does (never silent).
- **Persona:** "with Ruby" drops the committing option (Card C) — Ruby's constraint made visible.

### 5.5 Readiness states (within feed + Today sheet) — **P1**
- **Purpose:** readiness as a *chosen filter*, never silent ranking (`outcome-card-ux` §3).
- **Data:** `useReadiness()` — **fully mock** (no backend). Three cases: **off** (default, full feed); **on + fresh reading** → rationale-not-number ("recovery's on the lower side today; showing easier options") + disclosed/reversible hidden items ("4 strenuous hidden · show anyway"); **on + no/stale reading** → degrade-and-disclose, fail *open* to the full feed and say so (stale = treated as no reading, hard cutoff).
- **Honesty:** staleness as the reason; reversibility always present; effect as rationale, never a score.

### 5.6 Trips `(/trips)` — **P1**
- **Purpose:** the entry point to the post-hike loop — a quiet list of recent hikes (a "trip" = an Episode).
- **Data:** `recentEpisodes()` — **mock** (no episode list endpoint; this is the named backend gap). Each row: trail, when, measured facts, outcome state (logged / not yet).
- **States:** has-trips, empty ("your hikes will show up here — connect a watch or add one by hand"), error.
- **Persona:** Josh after a hike; surfaces the outcome card without nagging.

### 5.7 Outcome card `(/trips/:id/outcome)` — **P1 (signature)**
- **Purpose:** close the loop — capture what a sensor can't (how it *felt*) in one tap (`outcome-card-ux` §1).
- **Data:** **POST shape is real** (`OutcomeBody`→`OutcomeResponse`, via the seam); episode + measured facts are **mock**. `delta_question` is mock (backend doesn't generate one — noted gap).
- **Flow:** measured-then-ask (measured facts shown as *already known*, never re-asked) → the one ask "How was it?" 3 faces → optional "Was Ruby with you?" → conditional single delta question only if a measured value diverged → Done / **Skip is first-class** (writes `skipped:true`, no nag).
- **States:** watch-present (happy), degraded "forgot watch" (manual add, **P2**), degraded "partial episode / dead battery" (discloses the gap in our *own* data, **P2**).
- **Honesty:** quiet acknowledgment ("noted."), no celebration/streak; honest about its own prediction miss.

### 5.8 Memory / Belief store `(/memory`, `/memory/:id)` — **P1 (differentiator) / P2 receipt**
- **Purpose:** the legible "memory with receipts" that *is* the correction surface (no separate feedback form) (`outcome-card-ux` §2).
- **Data:** **fully mock** `BeliefVM[]` shaped to the graph model (subject_type person/dependent; stated vs inferred; confidence; staleness; derived-from episodes).
- **Overview:** grouped by axis — **Capability** (measured) · **Preferences** (inferred — header discloses "a guess") · **You told us** (stated) · **Ruby** (dependent) · **Faded** (collapsed, recoverable). Per row: value · **Confidence** dots (the *only* place a non-numeric dot encoding is allowed) · **Staleness** word · hedged copy for inferred.
- **Receipt `(:id)`:** "why do you believe this?" → the trips behind it (including honest 😐 outcomes, not hidden) + correction controls (keep / not really / mute; edit on stated only).
- **Honesty:** an inferred belief never poses as stated; capability ≠ preference, structural.

### 5.9 Honesty primitives — owned components — **P0 (foundational, reusable)**
Currently only **Signal** is built. This plan builds the other two specified in `design-system-v0.1` §7.1–7.2, because they appear on nearly every screen above and are **permanent, not throwaway**:
- **`Confidence`** — renders the `stated`/`hedged`/`flagged` tier as presentation (plain / hedged-secondary / accented), and a non-numeric **dot encoding** variant for the belief store. Never a number on primary surfaces.
- **`Staleness`** — renders age as a *relative-time word* ("48m old", "from a hike last fall"), demoting (not reordering) past threshold; hard-cutoff variant for readiness.
Both: token-backed, Storybook stories, vitest tests, added to the gallery.

### 5.10 Identity / household / party — **P2 (scaffold only)**
No backend, Phase-2 scope. Tonight: a mock "viewer" (Josh) and the party facet (solo/Ruby/friends) already exist. **Do not** design grant/sharing UI yet (`outcome-card-ux` §2.5 invariant 6: only *reserve* space). Carter and the full sharing dashboard are explicitly out of scope.

---

## 6. User flows (the core loops, assembled)

1. **Daily glance → decide → inspect** *(P0)*: open `/` → read context sentence → scan ≤3 peers (decide at rest) → tap → `/trail/:id` viability → back. 
2. **Tune the frame** *(P0)*: tap context sentence → facet sheet → adjust → set reshapes. 
3. **Caution encounter** *(P0)*: a flagged condition shows a promoted Signal on the card → Detail shows fuller verify context + sources. 
4. **Sparse/empty/error** *(P0)*: honest, confident, with a "widen the frame" or "try again" path — never a dead end. 
5. **Readiness toggle** *(P1)*: Today sheet → turn on → rationale + reversible hides, or fail-open disclosure if stale. 
6. **Post-hike nod** *(P1)*: `/trips` → tap a hike → outcome card → one face → (optional Ruby + delta) → Done/Skip. 
7. **Tend memory** *(P1)*: `/memory` → scan beliefs by axis → tap → receipt → keep/not-really/mute. 
8. **Anonymous browse** *(P0, implicit)*: same Home/Detail with an empty viewer scope; Trips/Memory invite a "you".

---

## 7. Build sequence (tonight) → clean PRs

| PR | Scope | Real vs mock | Throwaway? |
|---|---|---|---|
| **PR-A** | This plan doc (committed first for review). | — | none |
| **PR-B** | **Architecture spine:** `api.ts` (transcribe schemas), VM + adapters, `PlannerProvider`, `useFeed/useCard` hooks, owned `useRoute`, facet→wire translation, quarantine scoring behind `MockPlannerClient`. **Refactor Home + Detail onto the VM** (keep markup/CSS). Async states (loading/empty/error/sparse/not-found). Tests. | seam mirrors real API; mock supplies data + enrichment | scoring engine quarantined (deletable later) |
| **PR-C** | **Honesty primitives:** build `Confidence` + `Staleness` owned components (stories + tests), wire per-line confidence into cards/detail, add to gallery. | renders real `confidence_level`/`source` | none |
| **PR-D** | **Post-hike loop:** `/trips` list + Outcome card flow (measured-then-ask, faces, Ruby, conditional delta, skip), wired to real POST shape via seam. | POST real; episodes/delta mock | mock episodes (fixtures) |
| **PR-E** | **Memory:** belief store overview + receipt on mock belief data; correction controls. | fully mock | mock beliefs (fixtures) |
| **PR-F** | **Shell + nav + gallery:** quiet Home·Trips·Memory nav, route wiring, gallery refreshed with all components/screens; readiness states folded into Today sheet/feed. | — | none |

PRs land in order; each builds green (`tsc` + `vitest` + `vite build`), is independently reviewable, and is verified visually via Playwright screenshots. Depth scales to time; **PR-B and PR-C are the non-negotiable core** (they make the destination UX honest and feel-able); D/E/F are layered while quality holds.

---

## 8. Backend asks this plan surfaces (hand-off, not blockers tonight)

These are the precise endpoints that would let the UI drop mock and run end-to-end — useful product feedback regardless of tonight's build:
1. **Episode create + list/read** (`POST /episode`, `GET /episodes`, `GET /episode/{id}`) — unblocks the entire outcome loop over HTTP (today episodes are FIT-CLI-only).
2. **Structured card enrichment on `/plan`** — surface fields Scout already computes but drops (`length_mi`, `is_loop`, `area_id`) and add effort/ascent/duration; a structured `drive_minutes`; an optional one-line `fit`/rationale from the Curator.
3. **Readiness read** (`GET /readiness`) — the Body Battery → rationale value (Epic 007).
4. **Belief read + correction** (`GET /beliefs`, `POST /belief/{id}/correct`) — the legibility/correction surface (Stage 10).
5. **A human slug** alongside `canonical_id` for clean deep links.

---

## 9. How this honors the principles (self-check)

- **Source-or-silence / degrade-and-disclose:** the VM's optional-enrichment seam *is* graceful degradation; loading/empty/error/notice states are designed, not afterthoughts; confidence + source are first-class on every line.
- **Curation not feed:** ≤3 peers, sparse-is-confident, no crowning.
- **Calm utility:** no streaks/badges/nags; outcome is one tap and skippable; memory is occasional, not a headline dashboard.
- **Confidence is one property, never penalizes ranking:** rendered as tier/dots/words, never a score, never reordering.
- **Watch is enrichment:** readiness is an explicit toggle that fails open; the whole app works watch-free.
- **Private-by-default / access at the data layer:** viewer scope flows through the seam; anonymous = empty scope, a real product; no grant UI yet.
- **Minimal throwaway:** one VM, screens written once; only canned data + the duplicate scorer are provisional, and they double as fixtures.
- **NNG heuristics:** visibility of system status (loading/notices/freshness), match to real world (plain place/condition language), user control (reversible tuning/readiness/corrections, skip everywhere), error prevention & recovery (no-dead-end empty/error/not-found), consistency (one honesty vocabulary across surfaces), aesthetic-minimalist (cartographic-matte, accent-as-signal-only), recognition over recall (context sentence carries state).
