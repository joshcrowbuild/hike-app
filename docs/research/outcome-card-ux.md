# UX Exploration — Outcome Card, Belief Store & Readiness Filter

*Pre-Stage-10 exploration. Draft v0.1 — June 24, 2026. Builds on Stage 5 (memory schema), Stage 6 (watch integration), decision-log §9–§10, §19–§20.*

> **Status: EXPLORATION — NOT the design system.** This sketches the three Phase-1 personal surfaces in text/markdown wireframes to pressure-test whether the Stage-5/6 data model renders as a *calm utility* before Stage 10 commits to tokens, components, or platform. Wireframes here are disposable; the **invariants** they illustrate (§1.5, §2.5, §3.5, §5) are what should survive into the real design system. Honors rules #1, #2, #4, #6, #7. Does not change any decision in decision-log §30–§31; where it proposes new ground it is marked 🔶 / ❓ for Stage 10 to confirm.

> **Legend:** ✅ decided (in a prior stage; restated here as a constraint) · 🔶 recommended, confirm at Stage 10 · ❓ open.

> **Scope guard.** Per epic-002, "outcome card display is Stage 10." This doc is the *exploration that precedes* that work — it does not specify final markup, spacing, color, or component APIs. It specifies **behavior, state, and copy stance** so Stage 10 inherits a position, not a blank page (decision-log §19: "A real stance, not a default").

---

## 0. The three honesty primitives (shared vocabulary)

All three surfaces render the same three first-class UI states (decision-log §20: "these are first-class UI states, not afterthoughts"). Naming them once here so the wireframes can reference them tersely.

| Primitive | What it encodes | Where it comes from | Calm-utility rule |
|---|---|---|---|
| **Confidence** | freshness · authority · corroboration, rolled into one (decision-log §7) | `decayed_confidence(belief)`; live-call timestamp | High → plain text, no chrome. Lower → hedged phrasing *with its reason* inline. **Never a number in the primary surface** (decision-log §10 ③, §20). |
| **Staleness** | age relative to rate-of-change | belief `last_updated_at`; live-fetch timestamp | Shown as relative time ("checked 8 min ago", "from a hike last fall"), never a raw datetime. Staleness past a threshold *demotes presentation*, never *demotes rank* (decision-log §7 NON-thing). |
| **Verify-before-you-go** | a low-confidence *condition* that is safety-relevant | Verifier flag on a live fact below the floor | An inline line in the rationale, not a banner, not a modal, not a color-scream (decision-log §7 safety-flag; Stage 6 §6.3 "not a banner"). |

**The hedge is the honesty** (decision-log §7). These primitives are never decoration; they are the product's core promise made visible. The design discipline is to render them *without clutter* — the hard part, and the signature problem (decision-log §19).

---

## 1. Surface One — The Outcome Card (the post-hike flow)

> **Spec anchors:** Stage 5 §1 (`:Outcome` node), Stage 6 §3.3 (party toggle), epic-002 (endpoint + promotion), decision-log §10 sync-UX ②.

### 1.1 The loop this surface closes

`predict → recommend → go → **outcome** → update` (decision-log §9). The watch already captured everything a *sensor* can see (route, pace, ascent, HR, moving/stopped). The card's only job is to capture **what a sensor cannot**: how it *felt*, and — occasionally — to resolve one prediction gap. Everything measured is shown as **already-known**, never re-asked (decision-log §10: "reflect measured facts, ask only what a sensor can't see").

**Non-negotiable framing:** the card is **fully skippable and decays if ignored** (decision-log §10 ②; epic-002 S3). A skipped card is *not an error state* and is *not nagging* — it writes `Outcome{skipped:true}` and moves on. The product is "a planning input, not a health authority — no coaching/nagging" (decision-log §10).

### 1.2 Entry points

| Trigger | When | Note |
|---|---|---|
| Opt-in push | backend generated *after a poll* detects a new hiking activity (decision-log §8, §10 ②) | Push is opt-in; default is silent. Never same-day-guaranteed (needs always-on poller, deferred — §31 S6-12). |
| Next app-open | the calm default when push is off | Card sits at the top of the feed, dismissible. |
| Manual add | "forgot watch" lightweight path (decision-log §10 ⑤) | Degraded episode — fewer measured facts to reflect; the card asks slightly more. |

### 1.3 Wireframe — the measured-then-ask card (watch present)

```
┌─────────────────────────────────────────────┐
│  You hiked Hawksbill Loop                     │   ← trail_id matched (Stage 6 §3.2)
│  Saturday · 4.2 mi · 1,180 ft up              │   ← Episode.{distance_m, ascent_m}, measured
│                                               │
│  ┌─────────────────────────────────────────┐ │
│  │  Measured                               │ │   ← already-known block; not asked, just shown
│  │  2h 45m moving · ~15 min/mi on grade    │ │     (moving_min, pace_on_grade)
│  │  Steady pace the whole climb            │ │   ← LLM-extracted conditions_note (optional)
│  └─────────────────────────────────────────┘ │
│                                               │
│  How was it?                                  │   ← the ONE required ask (Outcome.overall)
│                                               │
│        🙂          😐          😞             │   ← 3 → 2 → 1 ; one tap; that's the whole minimum
│                                               │
│  ⌃ Was Ruby with you?      [ no  ●━ yes ]     │   ← party toggle (Stage 6 §3.3, S6-5)
│                                               │
│  Skip                                  Done   │   ← Skip is first-class, never buried
└─────────────────────────────────────────────┘
```

**One tap = a complete outcome.** Tap a face → `overall` set → card can close. The delta question (§1.4) only appears *if a prediction gap is worth resolving* — otherwise the card ends here. Two taps is the ceiling (epic-002: "1–3 tap rating + optional one-sentence delta"; decision-log §19: "reflect-back + ≤2 taps").

### 1.4 Wireframe — the conditional delta question

Shown **only when** a measured value diverged meaningfully from prediction (e.g. the route took far longer than the Curator's pace estimate), and only **one** such question. This is the single gap worth one sentence; never a survey.

```
┌─────────────────────────────────────────────┐
│  🙂  noted.                                   │   ← acknowledges the tap; no celebration, no streak
│                                               │
│  We figured ~2h10. You took 2h45.            │   ← honest about its own miss (delta_question)
│  Anything slow it down?                       │
│                                               │
│  [ mud      ] [ crowds   ] [ took it easy ]   │   ← tap-chips → delta_answer, zero typing default
│  [ + something else                       ]   │   ← optional free text; expands only if tapped
│                                               │
│                                        Done   │
└─────────────────────────────────────────────┘
```

**Why chips before a text field:** the minimum-friction path must require zero keyboard. A tapped chip writes `delta_answer`. Free text is available but never the default posture — calm utility means the common case is two taps total.

### 1.5 Degraded variants (none are error states — decision-log §10 ⑤)

```
FORGOT WATCH (manual add):                  PARTIAL EPISODE (dead battery):
┌─────────────────────────────┐             ┌─────────────────────────────┐
│  Add a hike                 │             │  You started Old Rag         │
│  Which trail?  [ search… ]  │             │  ~1.1 mi recorded, then your │  ← discloses the gap plainly
│  Roughly how long? [  ]     │             │  watch stopped.              │
│  How was it? 🙂 😐 😞        │             │  Want to finish it by hand?  │
│  Skip                  Add  │             │  How was it? 🙂 😐 😞  Skip   │
└─────────────────────────────┘             └─────────────────────────────┘
```

The disclosure ("then your watch stopped") is the honesty primitive applied to *our own* data, not just trail data — **source-or-silence applies to the episode record itself**. We never silently invent the missing miles.

### 1.6 Outcome → Episode → Belief (what the user is told vs. what happens)

The user sees a quick reflect-back. Behind it, the data flows per Stage 5 §2 / epic-002. The UX exposes this flow **only later, on pull**, in the belief store (§2) — never as a push notification at outcome time (decision-log §10 ④: "Beliefs — pull, not push").

```
  TAP (🙂, "mud")                  WORKER QUEUE (async)              LATER, IN BELIEF STORE
  ───────────────                  ─────────────────────            ──────────────────────
  Outcome{overall:3,               +1 corroboration on              "Likes ridge loops"
   delta_answer:"mud"}      ──►     prefers_ridge_trail      ──►     appears once N=3
   skipped:false}                   (epic-002 S4)                    (provisional → active)
                                                                     — user can confirm/correct
   delta_answer non-empty   ──►     stated belief, conf=1.0   ──►   shows immediately as
                                    (epic-002 S5)                    "You told us" (type:stated)
```

**Three UX-load-bearing facts from the schema:**

1. **An inferred belief never poses as a stated one** (Rule #7, §30 belief-type). The outcome card *never* tells the user "we now believe you like ridges" — that would dress an inference as a fact at the moment of one data point. Inferred beliefs surface only after N=3, only in the pull surface, and always labeled inferred (§2).
2. **A stated delta gets `confidence=1.0`, `decays=false`** (epic-002 S5). If the user *types* a preference, it is theirs, immediately, permanently — and shown as "You told us" in the store.
3. **Skipped writes a node** (epic-002 S3). Skipping is data ("not worth reflecting on" is itself weak signal), and it keeps the card idempotent — a later non-skip POST replaces it (epic-002 S3 AC-3.3).

### 1.7 What the Outcome card must NOT do (calm-utility guardrails) 🔶

- **No streaks, no badges, no "you're on a roll."** Engagement-seeking is the explicit anti-pattern (CLAUDE.md; decision-log §1). Acknowledgment is a quiet "noted," not a reward.
- **No re-asking measured facts.** If the watch knows distance, never ask distance. Asking what we already measured is the fastest way to feel like a chore.
- **No coaching.** "Your HR was high" is not shown as advice. The watch is "a planning input, not a health authority — no coaching/nagging" (decision-log §10).
- **No guilt on skip.** No "you've skipped 3 reflect-backs." Decay handles abandonment silently.

---

## 2. Surface Two — The Belief Store ("memory with receipts")

> **Spec anchors:** Stage 5 §1 (`:Belief`, provenance), §4 (legible store *is* the correction UI), §6 (`scopedQuery` viewer-scoping), decision-log §6 ("memory with receipts = edges"), §9 ("legible and user-editable... doubles as the correction surface"), §19 surface 5.

### 2.1 The thesis this surface embodies

**The legible belief store *is* the correction surface** (CLAUDE.md architecture line; decision-log §4, §9 role-gold). There is no separate "feedback" form. The user corrects the system by *editing what it believes about them* — and because every belief is `DERIVED_FROM` episodes (Rule #7; decision-log §6), every belief can show its **receipts**: which trips, what confidence, how fresh. "Why do you believe this?" is a traversal made visible.

This is the surface that earns trust. A remembered preference is "a new class of hallucination" (decision-log §9) — so it must be inspectable and falsifiable, never a black box.

### 2.2 Wireframe — the store overview

```
┌──────────────────────────────────────────────────────────┐
│  What I've learned about you                               │
│  Everything here is editable. Tap any item to see why.     │   ← legibility promise, stated plainly
│                                                            │
│  CAPABILITY  (measured from your hikes)                    │   ← axis grouping (Stage 5 §1)
│  ─────────────────────────────────────────────            │
│  Moderate-grade pace   ~15.8 min/km    ●●●●○  fresh        │   ← value · confidence dots · staleness
│  Comfortable distance  up to ~22 km    ●●●●●  fresh        │     dots = confidence (NOT a number)
│  Heat                  runs warm        ●●○○○  inferred ⓘ  │   ← low conf + inferred → hedged, flagged
│                                                            │
│  PREFERENCES  (inferred — a guess from how you hike)       │   ← header itself discloses "inferred"
│  ─────────────────────────────────────────────            │
│  Ridge trails          you seem to like  ●●●○○  3 hikes    │   ← hedged copy "seem to" for inferred
│  Loops over out-backs  you seem to like  ●●●○○  3 hikes    │
│  Crowds                you seem to avoid ●●○○○  thin ⚠     │   ← below-floor: shown but flagged thin
│                                                            │
│  YOU TOLD US  (stated — won't change unless you do)        │   ← type:stated, decays:false
│  ─────────────────────────────────────────────            │
│  "No scrambles with Ruby"                       ✎          │   ← from a typed delta_answer, conf 1.0
│                                                            │
│  RUBY                                                       │   ← dependent subject_type (Stage 5 §1)
│  ─────────────────────────────────────────────            │
│  Max distance          ~16 km           ●●●●○  stated      │
│                                                            │
│  ⌃ Faded beliefs (3)  — things I'm no longer sure of       │   ← decayed-out, collapsed, recoverable
└──────────────────────────────────────────────────────────┘
```

**Design decisions embedded here:**

- **Axis is the primary grouping**, and the group header *is* the disclosure. "PREFERENCES (inferred — a guess from how you hike)" tells the user, once, at the top, that this whole block is a hypothesis — so each row stays terse. This keeps `capability ≠ preference` (Rule #7, §30) legible *as layout*, not just as a property.
- **Confidence renders as a non-numeric encoding** (here, filled dots — but the encoding itself is 🔶, see §5 U-1; never a raw float — decision-log §10 ④, §20). `decayed_confidence()` (Stage 5 §3) maps to that scale at read time. The user never sees `0.62`.
- **Ruby is a `dependent` subject** — `Belief.subject_type:"dependent"`, modeled as a `:Person` reached via `HAS_DEPENDENT` (Stage 5 §1), not a distinct node label. The store groups her beliefs separately so "about you" stays unambiguous.
- **Staleness renders as a word** ("fresh", "thin", "from last fall"), driven by `last_updated_at` + decay. A belief that has decayed below the floor falls into **"Faded beliefs"** — collapsed, not deleted (the node still exists for provenance; decision-log §9 "decaying, legible").
- **Inferred copy is hedged in the row itself** ("you *seem to* like"). Stated copy is plain ("won't change unless you do"). The phrasing carries the type — the hedge *is* the honesty (decision-log §7).

### 2.3 Wireframe — the receipt (tap any belief → "why do you believe this?")

This is the differentiator. Tapping a belief traverses `Belief-[:DERIVED_FROM]->Episode` (Stage 5 §1) and shows the evidence — **"memory with receipts"** literally rendered.

```
┌──────────────────────────────────────────────────────────┐
│  ← Ridge trails — you seem to like these                   │
│                                                            │
│  This is a guess, not something you told us.               │   ← inferred disclosed up front (Rule #7)
│  Confidence: ●●●○○   ·  based on 3 hikes                    │
│                                                            │
│  Why I think this — the trips behind it:                   │   ← source_episode_ids → receipts
│  ─────────────────────────────────────────────            │
│  • Hawksbill Loop      Sat       🙂   ridge, exposed       │
│  • Stony Man           last mo   🙂   ridge                │
│  • Bearfence           Apr       😐   ridge, scramble      │   ← the 😐 is shown honestly, not hidden
│                                                            │
│  ⓘ This came from how you hike, not what you said.         │   ← Stage 6 §5 disclosure tag, inline
│     I could be wrong.                                       │
│                                                            │
│  ┌──────────────┬──────────────┬──────────────┐            │
│  │  Yes, keep   │  Not really  │  Mute this   │            │   ← the correction controls (§2.4)
│  └──────────────┴──────────────┴──────────────┘            │
└──────────────────────────────────────────────────────────┘
```

**Why the receipt shows the 😐:** honesty is bidirectional. If one supporting episode was lukewarm, hiding it would make the belief look stronger than its evidence. Showing all three episodes (and their outcomes) is the same source-or-silence discipline applied to the user's own memory. The user can see *exactly* why the system thinks this, and disagree from a position of full information.

### 2.4 The correction controls — what each does to the graph

| Control | Belief mutation | Why this design |
|---|---|---|
| **Yes, keep** | `confirmed_by_user=true`, `type→stated`, `decays=false` (mutation per Stage 6 §4.5) | Promotes an inferred guess to a stated fact. The user's affirmation is the strongest signal — it stops decay and saturates confidence. (The three-button control *set* is this doc's proposal, 🔶; §4.5 specifies only the mutation.) |
| **Not really** | belief retired: confidence floored, removed from Curator injection; `DERIVED_FROM` edges retained | **A correction is not a delete.** The episodes are still true; only the *generalization* was wrong. We keep provenance so the system can learn it over-generalized (decision-log §9 "corrections harden the Verifier"). 🔶 Stage 10 to confirm whether "Not really" writes a negative stated belief vs. just suppresses. |
| **Mute this** | belief retained but `injected=false`; still visible, greyed | "True but don't act on it." Lets the user silence a correct-but-unwanted inference without destroying data. ❓ Is mute distinct enough from "Not really" to keep both? Stage 10 usability call. |
| **✎ (edit, on stated only)** | edits `value` of a `type:stated` belief | Only stated beliefs are free-text editable. Inferred ones are corrected via the three buttons, not typed-over — you don't hand-edit a measurement. |

**Load-bearing rule:** a correction **never silently deletes the episodes**. "Share the conclusion, not the substrate" has a correction-side twin — *correct the conclusion, preserve the substrate*. The belief is the editable layer; the episodes are the immutable receipts (Rule #7; decision-log §6).

### 2.5 Belief-store invariants (must survive into Stage 10)

1. **Every belief is tap-to-receipts.** No belief without traversable provenance (Rule #7). If a belief can't show its episodes, it shouldn't show at all.
2. **Confidence and staleness are visible on every row**, as a non-numeric encoding and words — never hidden, never a raw number (decision-log §7, §20). *The encoding itself (dots vs. bar vs. word-only) is 🔶 for Stage 10 (§5 U-1); the invariant is "non-numeric," not "5 dots."*
3. **Inferred and stated are visually unmistakable**, and inferred copy is hedged (Rule #7, §30). The store is where "an inference never poses as a stated fact" is most directly tested.
4. **Correction preserves provenance.** Editing a belief never deletes an episode (decision-log §6, §9).
5. **Every belief-store read is viewer-scoped.** Reads go through `scopedQuery(viewer)` (Stage 5 §6; Rule #4 — access control at the query/data layer, never in the agent). The store never renders another member's `:Belief`/`:Episode`/`:Outcome` nodes; the scoping holds even before the grant system exists. ✅
6. **The store doubles as the sharing dashboard** (decision-log §9, §19 surface 5) — but grants are Stage 8; **this exploration shows no grant UI**, only leaves room for it (a future per-row "shared with" affordance). 🔶 Reserve layout space; do not design grants here.

---

## 3. Surface Three — The Readiness Filter

> **Spec anchors:** decision-log §10 ("a user-toggled FILTER, not a background default"), Stage 5 §5 / S5-9 (never persisted), Stage 6 §5.3 (JIT filter parameter), Rule #6.

### 3.1 The one principle that defines this surface

**Readiness is a filter the user *chooses* to apply — it never silently shapes the feed** (decision-log §10: "now a user-toggled FILTER, not a background default (corrected)"). "You choose when your body shapes the feed; it never silently does." This correction is load-bearing: an always-on readiness default would make the app a health authority that nags. A toggle makes it a tool the user reaches for.

**It is a constraint, not a ranking adjustment** (Stage 6 §5.3: "the filter is a constraint (Curator hard-filter half), not a ranking adjustment"). When on, it *filters out* what today's recovery can't support — it does not re-rank by readiness. This keeps it consistent with Rule #2 (confidence/state never penalizes rank; here, readiness gates, it doesn't bury).

### 3.2 Wireframe — the filter control (off by default)

```
┌──────────────────────────────────────────────────────────┐
│  Feed                            origin: Front Royal  ▾    │
│  ─────────────────────────────────────────────            │
│  effort ▾   type ▾   party ▾   [ tune to today  ○ ]       │   ← readiness toggle, sits among filters
│                                                  ↑         │     OFF by default (decision-log §10)
│                                          off = no readiness │
└──────────────────────────────────────────────────────────┘
```

### 3.3 Wireframe — toggled ON, reading available (the happy path)

```
┌──────────────────────────────────────────────────────────┐
│  [ tune to today  ● ]   reading from Garmin, 20 min ago    │   ← live, JIT — staleness shown (§3.4)
│                                                            │
│  Your recovery is on the lower side today.                 │   ← rationale, NOT a number (decision-log
│  Showing easier options; hiding the big climbs.            │     §10 ③ "surfaces as rationale, never
│                                                            │     as a number")
│  ───────────────────────────────────────────              │
│  ⌃ 4 strenuous trails hidden by this filter   show anyway  │   ← never silently disappear; reversible
└──────────────────────────────────────────────────────────┘
```

**Two design rules visible here:**

- **Rationale, never a number** (decision-log §10 ③). The user sees "on the lower side today," not "Body Battery 34." The number is a private input; the *effect* is the disclosure. This mirrors the Curator rule from Stage 5 §4: surface the effect, never the raw personal datum.
- **Filtered-out items are disclosed and reversible** ("4 hidden · show anyway"). A hard filter that silently vanishes options is opaque; calm-utility means the user always sees the filter is acting and can override it. This also respects the lesser-traveled-trails-are-first-class stance — nothing is *buried by rank*, only *gated by an explicit, reversible choice*.

### 3.4 Wireframe — toggled ON, no reading (the absent-data case)

The absent-data case is "trivial — apply the filter with no reading and it just says it can't" (decision-log §10). This is **degrade-and-disclose** (Rule #6: watch data is enrichment, never a dependency).

```
┌──────────────────────────────────────────────────────────┐
│  [ tune to today  ● ]                                      │
│                                                            │
│  No fresh reading right now.                               │   ← honest; not an error, not a blocker
│  Showing the full feed — nothing filtered.                 │   ← degrades to baseline, full feed intact
│                                                            │
│  ⌃ last reading was 2 days ago (too old to use)   why?     │   ← staleness as the reason, plainly
└──────────────────────────────────────────────────────────┘
```

**Why "showing the full feed" and not an empty/error state:** the product was "built watch-free first, so 'no watch' is baseline by construction" (decision-log §10). The filter failing open to the complete feed is the *correct* behavior — readiness is enrichment, and its absence costs nothing. A reading too old to trust is treated exactly like no reading (live readiness "has a freshness window," decision-log §10) — **staleness here is a hard cutoff, not a hedge**, because a stale recovery score is worse than none.

### 3.5 Readiness-filter invariants (must survive into Stage 10)

1. **Off by default; user-initiated only** (decision-log §10). Never a background default. ✅
2. **Effect as rationale, recovery as private input — never a number in the feed** (decision-log §10 ③; Stage 5 §4 disclosure pattern). ✅
3. **A constraint (gate), not a ranking penalty** (Stage 6 §5.3; Rule #2). It hides, it never buries-by-rank. ✅
4. **Filtered items are disclosed and reversible** ("N hidden · show anyway"). 🔶 Confirm the exact affordance at Stage 10.
5. **Absent / stale reading fails open to the full feed, and says so** (Rule #6 degrade-and-disclose; decision-log §10 freshness window). ✅
6. **Never persisted** (Stage 5 S5-9, Stage 6 §5.3). The reading is a JIT query parameter; it leaves no belief, no node, no trace in the store (§2 will *never* show a readiness belief — by construction). ✅
7. **Group readiness (party) is the same control, gated on the *less*-recovered member** (decision-log §10, §11). Out of scope to wireframe here (party + grants = Stage 8); the toggle copy generalizes to "tune to the group" (decision-log §10). 🔶 Stage 8.

---

## 4. Cross-surface consistency — how the three connect

```
   OUTCOME CARD              BELIEF STORE                 READINESS FILTER
   (push / write)            (pull / correct)             (toggle / JIT)
   ─────────────             ────────────────             ────────────────
   logs the felt sense  ──►  the felt sense + the     ◄── never writes here
   the watch can't see       measured facts become         (S5-9: not persisted)
                             receipts behind beliefs
                                   │
   typed delta_answer  ──────────► appears as "You told us"
   (stated, conf 1.0)              (editable, never decays)
                                   │
                             user corrects here  ──────► changes what the
                             ("Not really" / "Yes")       Curator injects (Stage 5 §4)
                                                          → next feed reflects it
```

- **The Outcome card writes; the Belief store reads and corrects; the Readiness filter neither — it gates JIT.** Three distinct postures: push-write, pull-correct, toggle-gate. Keeping them distinct prevents the readiness signal from ever leaking into the belief store (the most important boundary, S5-9).
- **One confidence vocabulary across all three** (§0). Non-numeric encoding in the store; rationale-not-numbers in the filter; hedged-copy in both. A user learns the honesty language once.
- **One skip/override posture across all three.** Skip the outcome card; override the readiness filter ("show anyway"); correct or mute a belief. Every surface is reversible and user-controlled — the calm-utility throughline (decision-log §1, §19).

---

## 5. Open questions for Stage 10 ❓ and recommendations to confirm 🔶

| # | Item | Status | Note |
|---|---|---|---|
| U-1 | Confidence as 5 dots vs. another non-numeric encoding (bar, word-only) | 🔶 | Dots tested well conceptually for "render confidence without a number" (decision-log §20); the *invariant* (§2.5 #2) is non-numeric, not dots specifically. Confirm with real users at Stage 10. |
| U-2 | "Not really" → write a *negative stated belief* vs. *suppress only* | ❓ | Affects whether the system can learn it over-generalized (decision-log §9). Schema supports either; pick at Stage 10. |
| U-3 | Keep both "Mute" and "Not really"? | ❓ | Possible redundancy (§2.4). Usability call. |
| U-4 | Delta-question chips: fixed vocabulary vs. LLM-suggested per trail | 🔶 | Fixed chips keep it offline/cheap and predictable; LLM-suggested is richer but adds a call. Lean fixed for Phase 1. |
| U-5 | Exact staleness thresholds: when "fresh" → "thin" → "faded"; readiness freshness-window length | 🔶 | Tie to the decay half-lives (Stage 5 §3, half-lives marked 🔶 to tune) and the readiness freshness window — keep UI thresholds derived from those, not independently chosen. |
| U-6 | Push copy for the outcome trigger (opt-in) | 🔶 | Must not feel like an engagement nudge (decision-log §1). "You hiked Hawksbill — got a sec?" not "Don't lose your streak!" |
| U-7 | Sharing affordance placement in the belief store | 🔶 | Reserve per-row space; do **not** design grant UI here — Stage 8 (§2.5 invariant 6). |
| U-8 | Token-first realization across Tailwind (web) + SwiftUI (native) | 🔶 | Per decision-log §20 — the honesty primitives (§0) must be expressible as shared tokens. This doc defines their *behavior*; Stage 10 defines their *tokens*. |

---

## 6. What this exploration does NOT do (scope honesty)

- **Not a design system.** No tokens, no color, no spacing, no component APIs, no typography (decision-log §20, Stage 10).
- **Not final copy.** All strings are *stance illustrations* — they show the hedge/disclosure posture, not approved microcopy.
- **No grant / sharing UI** (Stage 8). The belief store *will* double as the sharing dashboard (decision-log §9, §19); this doc only reserves room.
- **No party/multiplayer surfaces** (Stage 8). Ruby appears only as a dependent subject in the belief store and the outcome-card toggle (Stage 6 §3.3) — both single-user-valid.
- **No feed/trail-detail card** (decision-log §19 surfaces 2–3) — those are a separate exploration; this one is scoped to the three personal post-hike/memory surfaces requested.
- **Does not change any §30/§31 decision.** Where it breaks new ground it is marked 🔶/❓ for Stage 10 to ratify. The data model is taken as fixed; only its *presentation* is explored here.

---

*End of exploration. The disposable part is every wireframe; the durable part is §0 (the three honesty primitives) and the four invariant sets (§1.7, §2.5, §3.5, §4). Stage 10 inherits a stance, not a blank page.*
