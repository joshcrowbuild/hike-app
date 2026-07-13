# Epic 040 — Two-phase render (cards first, conditions verified behind)

**Status:** REVIEW (2026-07-12 · S1–S4 built + gated in one lane; PO review pending. Post-merge measured verdict vs the SLO table still owed per the DoD — A2 fast-curate model not yet configured, so the honest phase-1 target is <2.5s until it lands)
**Phase:** A
**Spec refs:** Epic 039 mitigation ladder **B1** (design record [`../research/feed-first-paint-latency-wave1.md`](../research/feed-first-paint-latency-wave1.md), incl. its S2 "Two-phase-render compatibility" section, honored below) · Epic 018 S4 / CDP-02 (the six-state `ConditionStatus` vocabulary this design wears) · CLAUDE.md rules #1/#2/#3/#5/#6

---

## Capability statement

A first-ever visitor (or any fresh-key retune) sees corpus-backed, taste-ranked trail cards in **< 1.5s**, each wearing honest per-kind silence, and watches verified live conditions patch in per-card behind them — the production posture the SLO table calls "paint instantly, verify visibly behind" (exactly rule #3's "fetched JIT and overlaid"). Fresh measurement (2026-07-12): cache-miss 3.6–5.1s, cold-everything 14.4s — the < 8s cold SLO is missed; this epic is the ladder's architectural fix.

## Architectural context

**Builds on:** the six-state `ConditionStatus` vocabulary (Epic 018 S4 — `present · stale_degraded · no_hazard · no_data · unavailable · not_fetched`, wired end-to-end: `engine._condition_summary` → `ConditionStatusResponse` → the frontend's kebab-case condition-silence renderer). Wave 3 built exactly the language a pending card needs: **`not_fetched` is now a legitimate on-screen state** — "not probed (yet)" is true silence, not a placeholder trick. Also builds on: the S2 engine-layer `FeedCache` (`CachedPlan` below presentation — untouched here, per the S2 compatibility section), S3 stale-while-revalidate, B5 default-frame warmer, B4 corroboration overlap.
**Enables:** the end-state SLO column (< 1.5s to cards on a fresh key; < 2.5s cold); C1 payload diet and the (still-refused-for-conditions) edge-cache split — post-split, the cards half is slow data and MAY be edge-cached; the conditions half never is.
**Does NOT include:**
- Skipping the anonymous LLM taste-rank. **S4 stays DEFERRED — not relitigated.** Phase 1 keeps the real taste rank; the latency headroom comes from what phase 1 *omits* (the probe fan-out), not from degrading rank quality.
- SSE/WebSocket streaming (decision D1 below — refused this epic, revisitable).
- Any change to `FeedCache`'s layer or key (S2 compatibility section: the split happens in rendering/composition, the cache is not touched).
- Non-anonymous caching or auth changes (Rule #5 posture unchanged).

---

## Recorded decisions

### D1 — Transport: second call, not SSE

**Decision: a second plain HTTP call** (`POST /plan/conditions`), not SSE/streaming.

- The API is sync FastAPI on a single uvicorn worker (Render free tier); a long-lived SSE stream pins a threadpool slot per viewer for the whole fan-out and adds a transport failure surface (proxy buffering, reconnect semantics, slowapi incompatibility) the calm utility gets nothing for.
- The fan-out completes as one batch (`verify_batch` joins all probes); there is no meaningful per-card arrival order to stream — "one patch when verification lands" is the honest granularity. Per-card *rendering* staggering is a frontend presentation choice, not a transport need.
- A second call is testable with the existing TestClient/eval harness, rate-limited by the existing slowapi decorators, and CORS-inert. SSE would make the eval-replay gate (D3) transport-dependent.
- Revisit trigger: if a future wave streams genuinely incremental verification (per-kind arrival), SSE re-enters; nothing below precludes it (the patch payload is already per-card).

### D2 — The pending state is `not_fetched` + client-held pending-ness (no 7th state)

Phase-1 cards carry a full six-state `conditions` tuple with **every probe-able kind `not_fetched`** — which is *true* (nothing has been fetched), source-or-silence by construction: no source, no `checked_at`, no condition lines, no warnings. **No `pending` wire state is added.** "Verification in flight" is client state, not a fact about the world: the frontend initiated phase 2 and knows it's pending — exactly the S3 precedent where `stale`/`revalidating` are `FeedState` signals, never VM fabrications. A phase-1 response is therefore indistinguishable from an honest "not probed in this deployment" response — because that is literally what it is at that moment.

### D3 — What the eval-replay gate asserts for phase-1 responses

The gate (evals/replay.py — code predicates, no judge) gains two-phase criteria; a scenario runs the same recorded bundle through **both** paths:

1. **`phase1_silence`** — the phase-1 batch fabricates nothing: zero facts on every trail, every `ConditionStatus.state == "not_fetched"`, no `source`/`checked_at` on any status (the existing `_ANSWERED_STATES` attribution check applied to an all-unanswered feed), zero warnings, zero `unavailable` disclosures, zero set-asides. Silence before verification, never a guess.
2. **`two_phase_composition`** — phase 1 + the conditions patch, composed, is **equivalent to today's single-pass output** over the same bundle: same surfaced trail set, same per-kind facts (source + pinned value subset), same six-state dispositions, same warnings, same set-asides. Two phases are a presentation split, never a second truth.
3. **`phase_order_stable`** — the composed card order is the phase-1 order minus phase-2 removals (D5): no reorder ever.

The existing single-pass criteria keep running unchanged — the classic path stays gated (it remains the fallback, D6).

### D4 — Stale-while-revalidate composition (S3 × two-phase)

The stale paint is a whole-FeedVM swap decoupled from condition timing (S3's non-preclusion argument, now cashed in). Composed ladder for a returning anonymous visitor:

1. **t≈0.4s** — stale paint (unchanged S3): neutralized cards, `stale-degraded` silence, "Showing your last visit (Xm ago) — checking current conditions…".
2. **t≲1.5s** — phase 1 lands: swap to **fresh** cards (fresh corpus data, real rank), conditions `not_fetched`; disclosure becomes "Checking current conditions…" (`revalidating` stays true; `stale` clears — the cards are no longer stale, only unverified).
3. **t≲+4s** — phase 2 lands: per-card patch; disclosure clears; `revalidating` false.

Rules: `writeFeedCache` persists **only the composed (phase-2-complete) feed** — the S3 write-gate extends from "non-error, non-empty" to "conditions complete", so a stale paint never re-serves an all-`not_fetched` frame as "your last visit". Same for `feedSnapshot.current` (Detail never resolves a card from a half-composed feed). `aria-busy` stays `status === 'loading'` only; both pending phases speak through the polite `role="status"` line.

### D5 — Phase 2 may remove, never reorder

Phase-1 order is final for the frame. A phase-2 hard-guardrail block (hazardous AQI) **removes** that card with the standard disclosed set-aside (existing `set_aside` semantics — a safety gate, not a demotion, Rule #2); a verified hazard stays a card wearing its warning (2026-07-01 decision, unchanged). Nothing ever reshuffles under the user's eyes (calm utility). Consequence accepted and recorded: the judge ranks phase-1 candidates **with** drive-time hints (the Valhalla prefilter is origin-relative but cheap and load-bearing for candidate pruning — it stays in phase 1, see S1) but **without** live-condition input — which it never had anyway (Rule #2: conditions never feed ranking).

### D6 — Backward compatibility & kill switches

`POST /plan` unchanged by default (`phase` absent → today's full single-pass response — the eval baseline, the API contract for old clients, and the rollback). Client kill switch: `VITE_TWO_PHASE=0` (build-time, same convention as S3's cap). Server kill switch: `ADVENTURE_TWO_PHASE_ENABLED=0` makes `phase:"cards"` serve the full response (clients detect completeness per S3-story AC-3.2 and skip the second call). Either side alone fully reverts the flow.

### D7 — FeedCache interplay (S2 compatibility honored)

The cache stays keyed on inputs storing `CachedPlan` below presentation — this epic only *splits the rendering* of a plan, exactly the split the S2 doc reserved ("`feed_card` can be split into card-vs-condition rendering inside `_render_feed` without touching the cache"). On a **warm** key, `phase:"cards"` returns the full feed (facts are already paid for — withholding them to honor a phase would be manufactured latency); the response self-describes as complete and the client skips phase 2. On a **miss**, `phase:"cards"` computes the graph-only plan and does **not** write the FeedCache (an all-`not_fetched` plan must never be served to a later full request); the conditions call's composed result is what warms the key, single-flighted as today. The B5 warmer keeps warming full frames — a warm default frame short-circuits the whole two-phase dance for the most common path.

---

## Stories

### S1 — Engine: graph-only phase-1 plan

**Given** an anonymous `/plan` with `phase:"cards"` on a cold key
**When** the engine runs
**Then** it returns taste-ranked, corpus-backed cards — intent parse → scout → drive prefilter (+ drive-time lines, already paid for) → corroboration (B4-overlapped) → LLM taste rank — with **no live-probe fan-out**, every probe-able kind `not_fetched`, and no warnings/set-asides/condition lines.

**AC-1.1:** A phase-1 engine run issues ZERO live-condition probes (spy adapters record no `probe()` call for any point kind) while the Valhalla drive prefilter still runs when configured (its facts fold in as drive-time lines exactly as today).
**AC-1.2:** Every phase-1 card's `conditions` carries the full canonical kind order with `state=="not_fetched"`, empty `source`, `checked_at is None`; `warnings`, `unavailable`, and feed `set_aside` are empty (nothing verified → nothing asserted, nothing blocked — rule #1's contrapositive).
**AC-1.3:** The taste rank runs exactly as the full path's anonymous rank (same judge tier, same demotion signals, drive hints included) — S4 stays deferred; a judge failure on the anonymous path still re-raises (`test_anonymous_judge_failure_still_raises` semantics preserved for phase 1).
**AC-1.4:** A phase-1 result is NEVER written to the anonymous `FeedCache` (a later full-phase request on the same key must miss and compute; `stats.hits` unchanged) — and a warm key serves the full `CachedPlan` re-rendered as a complete response instead of recomputing a phase-1 (D7).
**AC-1.5:** `phase` absent or `ADVENTURE_TWO_PHASE_ENABLED=0` → byte-identical single-pass behavior (the existing engine tests keep passing untouched).

### S2 — API: `POST /plan/conditions` (the patch call)

**Given** the canonical_ids + origin a phase-1 response returned
**When** the client posts them to `/plan/conditions`
**Then** the verified overlay for exactly those cards comes back: per-card six-state `conditions`, condition lines (freshness rendered at serve time), warnings, unavailable disclosures — plus the disclosed removal list (hard-guardrail set-asides).

**AC-2.1:** The response carries, per requested canonical_id: `conditions` (full six-state vocabulary, sourced/timestamped exactly per the `_ANSWERED_STATES` contract), `lines`, `warnings`, `unavailable` — through the same `feed_card` rendering path production serves (no second presentation truth).
**AC-2.2:** A hard-guardrail-blocked id returns as a `set_aside` entry (cause + source), never as a card payload — and ids the graph doesn't know 404-per-item or are omitted with disclosure, never fabricated.
**AC-2.3:** The probe fan-out honors the existing registry TTLCache, `probe_max_workers`, and per-source failover exactly as `/plan` does (shared code path, not a re-implementation); PlanMetrics emits for the call with its real probe/LLM spend (zero LLM — this call never ranks).
**AC-2.4:** The endpoint is slowapi-rate-limited (plan-class limit), anonymous-allowed, auth-gated for non-anonymous viewers exactly like `/plan`; request size is bounded (max k ids, matching `PlanRequest.k`'s cap).
**AC-2.5:** The composed (phase-1 + patch) plan is what warms the anonymous `FeedCache` for that key (single-flighted), so a follow-up full `/plan` within TTL is a hit — and a conditions call for a key the cache already holds fresh serves from it without re-probing.

### S3 — Frontend: two-phase flow wearing the six states

**Given** an anonymous Home load with two-phase enabled
**When** phase 1 resolves
**Then** the FIRST fresh commit paints ranked cards whose condition blocks render the `not-fetched` silence treatment, a polite `role="status"` "Checking current conditions…" note shows, and the phase-2 patch fills each card in place — no reorder, removals disclosed calmly.

**AC-3.1:** Time-to-cards on a fresh key is governed by phase 1 alone (the conditions call starts only after phase-1 state commits; no waterfall blocking paint); with a stale S3 paint showing, the phase-1 swap replaces it per D4's ladder (stale clears, revalidating persists until the patch).
**AC-3.2:** A phase-1 response that self-describes complete (warm-key/kill-switch case, D6/D7) skips the conditions call entirely — no second request on the wire.
**AC-3.3:** While pending, per-card condition blocks render the existing `not-fetched` six-state treatment (wave-3 vocabulary; no new fabricated "loading conditions" per-card copy) — the pending signal lives in the feed-level status line + `revalidating`, not in the VM (D2).
**AC-3.4:** The patch updates cards **in place** (keyed by canonical_id): order unchanged, a set-aside removal animates out with the standard disclosed set-aside surface, and a patch failure keeps the cards usable with the S3-style "Couldn't verify current conditions — try again" note (never a blank, never a fake-clear; retry re-posts the conditions call only).
**AC-3.5:** `writeFeedCache` and `feedSnapshot.current` are written ONLY from the composed feed (D4); `VITE_TWO_PHASE=0` restores today's single-call flow byte-identically.

### S4 — Eval-replay gate for the split (D3)

**AC-4.1:** `evals/replay.py` gains the `phase1_silence`, `two_phase_composition`, and `phase_order_stable` criteria (code predicates per D3), run over the existing scenario bundles' recorded worlds; every existing single-pass criterion keeps running unchanged.
**AC-4.2:** The composition check compares the composed output structurally (trail set, per-kind fact source+value, six-state dispositions incl. the sourced/unsourced attribution contract, warnings, set-asides) — a two-phase drift from single-pass truth reds CI with a named violation, not a rate.
**AC-4.3:** `make eval-replay` stays hermetic (no network/keys) and is green with the criteria active before the build wave's first PR merges.

---

## Phase-1 latency budget (the <1.5s claim, attributed)

intent parse ~0.3s · scout + maps-fields graph reads ~0.3–0.5s (B4 discipline: independent reads overlap) · Valhalla prefilter ~0.2–0.3s · taste rank ~0.5–0.8s **with the A2 fast-curate model** (`ADVENTURE_MODEL_CURATE` — config-only companion lever, quality spot-check gate per the ladder) or ~1.5–2.5s without. **The <1.5s p75 target assumes A2 lands with (or before) this epic; without A2 the honest phase-1 target is <2.5s.** Record the measured verdict per the Wave-1 protocol either way. The maps read (`_fetch_maps_by_canonical`) attaches to phase-1 cards — this is where B4's skipped maps-overlap is naturally absorbed (the read overlaps the conditions fan-out by construction: it happens while phase 2 is in flight).

## Operator levers

- `ADVENTURE_TWO_PHASE_ENABLED` (server kill switch, D6) · `VITE_TWO_PHASE` (client, build-time)
- `ADVENTURE_MODEL_CURATE` — the A2 fast judge, the phase-1 budget's biggest single lever
- Existing: `ADVENTURE_ANON_FEED_CACHE_TTL_S`, `ADVENTURE_FEED_WARM_INTERVAL_S`, `ADVENTURE_LIVE_PROBE_MAX_WORKERS` — all compose per D7

## Definition of Done

- [ ] All ACs covered by at least one passing test; `make check` + `make eval-replay` green (S4 criteria active)
- [ ] Frontend: `cd frontend && npm ci && npm run test && npm run build` green (manual gate — no frontend CI)
- [ ] Post-merge measured verdict vs the SLO table (fresh-key <1.5s-to-cards p75 with A2, cold-everything <8s; browser time-to-cards, same protocol as Wave 1), recorded in this file
- [ ] Merge-sensitive seams called out per PR: `orchestration/engine.py`, `api/app.py` + `api/schemas.py`, `frontend/src/data/PlannerProvider.tsx`
- [ ] Epic index row synced (`python scripts/gen_epic_index.py --check` clean)
