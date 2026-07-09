# Feed first-paint latency — Wave 1 design record (Epic 039)

*Recon + adversarial design output, 2026-07-08. Produced by an ultracode round: 5 read-only recon agents over the seams, then per-story design panels (2 independent proposals each, adversarially judged with in-repo verification). This document is the builders' spec; the epic's ACs are extracted verbatim into [`../epics/epic-039-feed-first-paint-latency.md`](../epics/epic-039-feed-first-paint-latency.md).*

**Status:** IMPLEMENTED (Epic 039 — measured verdict below) · **Owner:** PO session

## Measured baseline (live API, 2026-07-08)

- `POST /plan`: **8.8s** cold probe caches · **3.7–4.0s** warm floor (k=1 ≈ k=10)
- Empty query (intent LLM skipped): 3.67s → intent parse ≈ 0.3s
- `GET /trail/{id}` (one graph read through Render): 0.53–0.67s
- Attribution: probe fan-out ~3–5s (cold only) · LLM taste-rank ~1.5–2.5s (every call) · ~6 sequential Aura reads ~1.5–2s (3 are personal-context reads that run even for anonymous) · intent ~0.3s

## PO decisions recorded

1. **S2 ships ENABLED, TTL 300s** (`ADVENTURE_ANON_FEED_CACHE_TTL_S`, 0 disables). Safe: every adapter TTL ≥600s, ages re-render per serve.
2. **S4 (skip anonymous LLM rank): DEFERRED** — see §S4 below.
3. Two-phase render: future epic; Wave-1 designs must not preclude it (both judges verified non-preclusion).
4. Operator lever (no code): `ADVENTURE_LIVE_PROBE_MAX_WORKERS` 8 → 16 on Render.

## Latency SLOs & the mitigation ladder (PO, 2026-07-08)

**Two metrics, deliberately decoupled — the production posture.** *Perceived first paint* (usable cards on screen) and *fresh-data time* (today's verified conditions present). No production app serves live-verified third-party data sub-second on a cold path; the honest architecture paints instantly and verifies visibly behind (exactly rule #3's "fetched JIT and overlaid"). Chasing sub-1s on the fresh path would mean faking freshness — refused. Chasing it on the perceived path is the roadmap.

**SLOs (measured at p75 unless noted; "fail" = missing any of these post-deploy):**

| Metric | Wave-1 target | End-state target |
|---|---|---|
| Perceived first paint, returning anonymous visitor | **< 1.0s** (S3 stale paint) | < 0.5s |
| `POST /plan`, cache hit | **< 1.0s** | < 0.7s |
| `POST /plan`, cache miss (fresh key) | < 4.0s | **< 1.5s to cards** (two-phase; conditions stream in ≤ 4s) |
| First-ever visit, cold everything | < 8s with honest progress copy | < 2.5s to cards (CWV "good" LCP) |
| p99 blank-screen time | never > 10s without staged copy (already built) | same |
| Cold-start (instance spin-up) visible to users | tolerated on hobby tier | **eliminated** (paid keep-warm — table stakes for production) |

**Verdict protocol:** post-merge measurement (same origin/query/k as baseline, plus browser time-to-cards). Each SLO judged pass/fail in the epic doc. A miss engages the ladder below at the lowest tier that plausibly closes the gap — one tier at a time, re-measure between tiers.

**Mitigation ladder:**

*Tier A — config only (hours, no PRs):*
- A1. `ADVENTURE_LIVE_PROBE_MAX_WORKERS` 8→16 (queued).
- A2. **Fast judge model for the `curate` tier** (`ADVENTURE_MODEL_CURATE` is already config): ranking 10 short names is not a hard task; a Haiku-class model cuts the ~1.5–2.5s rank to ~0.5–0.8s on every miss. Gate: spot-check ordering quality vs the current model on a handful of frames before adopting.
- A3. Raise `ADVENTURE_ANON_FEED_CACHE_TTL_S` toward 600 (the min adapter TTL) — higher hit rate, staleness still bounded by the probe cache's own floor.
- A4. Verify Render ↔ Aura region alignment (cross-region RTT multiplies every sequential graph read) and the Render plan tier (spin-down cold starts are disqualifying for production; keep-warm is the fix, not code).

*Tier B — engine work (the Wave-2 epic, days):*
- B1. **Two-phase render** — the architectural fix and the only route to sub-1.5s *fresh-key* cards: `/plan` returns corpus-backed, ranked cards immediately (graph-only), live conditions patch in per-card behind (second call or SSE), wearing the existing silence/hedge primitives while pending. Kills the cold-path number for first-time visitors and every retune.
- B2. Rank-order cache keyed by (candidate-id set, profile hash): LLM re-ranks only when the candidate set actually changes, not on every TTL expiry.
- B3. Structured facets on the wire (the `buildQuery.ts` lossy-seam backend ask): tuning-built queries skip the intent-parse LLM entirely (~0.3s every miss, plus one fewer failure mode); the LLM parses only free-text prompts.
- B4. Overlap the remaining graph reads (corroboration/maps) with the probe fan-out; they are independent of it.
- B5. Default-frame warmer: after deploy and on a TTL cadence, self-request each region's default frame so the in-process cache is never cold for the common path (primes S2; no persistence, rule #3 intact).

*Tier C — platform (only if A+B still miss):*
- C1. Payload diet on `/plan` (geometry/elevation arrays dominate; simplify polylines for feed cards, full fidelity stays on Detail).
- C2. Edge caching is **refused** for rendered `/plan` responses (frozen ages = rule #1 violation). Post-two-phase, the corpus-cards half is slow data and MAY be edge-cached; the conditions half never is.

**Standing decision:** if Wave-1 measurement passes its targets, Wave 2 (Tier B) is still the path to the end-state column — sequenced as its own designed epic, not an emergency.

---

## S1 — Anonymous fast-path (merged design)

## S1 — Skip personal-context reads for anonymous viewers

**Target:** `orchestration/engine.py` `plan()`, the personal-context assembly block at lines 515–525 (the try/except wrapping `fetch_beliefs`/`fetch_profile`/`fetch_relevant_episodes`/`assemble_context`).

**Problem confirmed in repo:** for `viewer_id == "anonymous"` all three Cypher reads run unconditionally, each scoped to `owner_id/member_id == "anonymous"`, match nothing, and return `[]`/`None`; `assemble_context([], None, [])` then returns `""` (context_assembly.py:163). Net result today: `personal_context == ""`, `context_degraded == False`, `combined_profile == intent.profile or None`, `use_personal_judge == False`. The three Aura round trips are pure waste on the anonymous path.

**Semantics (behavior-preserving):** gate the whole assembly block on `viewer_id != "anonymous"`. `personal_context` and `context_degraded` are already initialised to `""`/`False` before the block, so skipping the block leaves the anonymous path **byte-identical** minus the reads. Critically, the skip must **NOT** set `context_degraded` — a deliberate skip is not a degrade, so `PERSONAL_CONTEXT_UNAVAILABLE_NOTICE` (only appended when `context_degraded == True`, line 565–566) is never emitted. `use_personal_judge` stays `False`, so the plain cloud `runtime.judge` still ranks and the anonymous judge-failure re-raise at line 548–549 is untouched.

**Precise diff shape** (minimal-churn: wrap the existing try/except in one `if`, indent unchanged):

```python
    candidate_ids = [p.candidate.canonical_id for p in planned]
    personal_context = ""
    context_degraded = False
    # Anonymous viewers have no private overlay to assemble — skip the three
    # owner-scoped Neo4j reads entirely (they return empty for
    # owner_id=="anonymous" anyway). A deliberate skip is NOT a degrade:
    # context_degraded stays False so PERSONAL_CONTEXT_UNAVAILABLE_NOTICE is
    # never emitted (Rule #6 enrichment-skip vs. Rule #1 disclosure distinction).
    if viewer_id != "anonymous":
        try:
            beliefs = fetch_beliefs(viewer_id, runtime.session.run)
            profile = fetch_profile(viewer_id, runtime.session.run)
            episodes = fetch_relevant_episodes(viewer_id, candidate_ids, runtime.session.run)
            personal_context = assemble_context(beliefs, profile, episodes)
        except Exception:
            log.exception("personal-context assembly failed; serving the anonymous-quality feed")
            context_degraded = True
```

Nothing downstream changes: `combined_profile`, `use_personal_judge`, the judge selection, and the notice logic all read the same values they read today on the anonymous path. `candidate_ids` stays computed above the guard (cheap list comp; harmless when unused). The top-of-function imports of the four `context_assembly` symbols stay as-is (module imports, no runtime cost on the skip path).

**Why gate on the literal `"anonymous"` and not an `"overlay expected"` flag:** the existing `use_personal_judge` guard on line 540 already keys on `viewer_id != "anonymous"`, so this skip uses the exact same predicate the engine already trusts as the private/shared boundary — no new concept, no new seam. (If a future anonymous-but-device-personalised mode appears, it will introduce its own viewer identity and naturally fall on the non-anonymous branch.)

**Merge-sensitivity:** `orchestration/engine.py` is a named merge-sensitive seam — one logical change, call it out in the PR Merge-Risk section. Diff is ~8 lines.

---

## S2 — Engine-layer anonymous plan cache (judge-merged design)

**Panel verdict:** engine-layer proposal won 8.5 vs 6.5. Proposal 1 wins on the single most load-bearing axis: correctness under the binding freshness rule. Verified in-repo: present.py:146 renders the freshness as a relative string into FeedLine.text, and schemas.py:38 puts that exact string on the wire for every condition line (only warnings carry an absolute observed_at). Therefore an API-layer full-FeedResponse cache (Proposal 0) freezes the relative-age copy and re-serves stale lines as fresher — strictly worse than the existing probe TTLCache, which re-renders age on every engine run. Proposal 1's engine/Feed-layer cache re-runs feed_card per serve so _age recomputes against serve-time now, keeping displayed freshness honest at any TTL — the whole point of the source-or-silence product. The merged design keeps Proposal 1's layer + re-render mechanism and 3-decimal key, and grafts in Proposal 0's superior single-flight (refcounted per-key gate with finally-decrement), PlanMetrics honesty (feed_cache_hit=True, est_tokens/est_cost/live_calls zeroed, never recomputed from cached text), FIFO/size-cap/env-var discipline, failure-never-cached rule, and explicit two-phase-render non-preclusion. Default TTL set to 300s (mid the PO's 120-600s band) rather than Proposal 1's inert 0, because a 0 default makes S2 a no-op that misses the Wave-1 ~1s goal; 300s is safe precisely because displayed age stays honest via re-render and underlying fact age extends by at most feed_ttl beyond the probe TTL.

# Epic 039 · S2 — Anonymous ranked-plan cache at the engine/Feed layer (freshness re-rendered per serve)

## Decision & decisive rationale
Cache at the **engine/Feed layer**, not the API response layer. Verified in-repo: `orchestration/present.py:146` renders each condition line's freshness as a relative string (`_age()` → "just now"/"Xm ago") **into `FeedLine.text` at render time** (`now` defaults to `datetime.now(timezone.utc)` at present.py:138), and `api/schemas.py:38` (`FeedLineResponse.text`) carries that baked string verbatim on the wire. Regular condition lines carry **no** absolute timestamp on the wire; only `CardWarningResponse.observed_at` (schemas.py:58) does. Consequence: caching the fully-rendered `FeedResponse` (the API-layer approach) freezes the relative-age copy and re-serves a t0 line as "just now" up to TTL later — strictly worse than the probe TTLCache (which re-renders age on every engine run via `feed_card`→`summarize_fact`). That would violate the PO binding "never worse staleness than the probe TTLCache already permits" and Rule #1's freshness-honesty spirit.

**Fix (the core of this design):** cache the layer *below* presentation and re-render per serve. Store `CachedPlan` (the ranked `planned` trails carrying facts with their **absolute `fetched_at`**, plus `notices`, `set_aside`); on every serve rebuild the `Feed` by re-running `feed_card()` — so `_age` recomputes against serve-time `now` and the displayed freshness is always honest, at any TTL.

## What is cached / re-rendered / stays per-request
- **Cached (`CachedPlan`, viewer-independent for anonymous):** `planned: tuple[PlannedTrail, ...]` (the LLM taste-rank output with each trail's verified live facts + absolute `fetched_at` + frozen confidences), `notices: tuple[str, ...]` (= `batch.notices`; for anonymous `context_degraded` is always False so no personal-context notice), `set_aside: tuple[SetAsideTrail, ...]` (cause+source text, no wall-clock content). Verified: no viewer field exists on `PlannedTrail`/`FeedCard`/`FeedLine`/`SetAsideTrail`/`Feed`; for `viewer_id=="anonymous"` the personal-context reads return empty and `combined_profile` reduces to `intent.profile` (query-derived only) — so the plan is a pure function of (query, origin, k, process-fixed config) and safe to share cross-visitor (Rule #5 by construction + anonymous-only gate).
- **Re-rendered per serve:** the relative-age freshness copy, by re-running `feed_card()` (hence `summarize_fact` with a fresh `now`) over the cached `planned`. Pure string formatting — no I/O, no LLM, no graph read.
- **Stays per-request (outside the engine cache):** the maps/terrain read (`api/app.py` `_fetch_maps_by_canonical`, outside `engine.plan()`) re-attaches to the cached cards' stable `canonical_id`s — corpus/world data, kept fresh; the anonymous-only gate; probe facts (their own registry TTLCache — the feed cache nests above it).

## Mechanism / placement in plan() (engine.py — MERGE-SENSITIVE)
Split the current `plan()` body into:
- `_compute_plan(query, origin, runtime, *, k, viewer_id) -> CachedPlan` = today's body (parse_intent → plan_from_origin → context assembly → rank_plan → notices/set_aside) returning `CachedPlan` instead of `Feed`. **The anonymous outcome must stay byte-identical:** keep `context_degraded=False` for anonymous (S1's skip, if landed first, must not flip it), preserve `use_personal_judge=False` → plain cloud judge, and **keep the anonymous judge-failure re-raise (engine.py:548)** — because it re-raises from inside `_compute_plan`, `put` is never reached, so failures are never cached.
- `_render_feed(query, cached) -> Feed` = `Feed(query=query, cards=[feed_card(p) for p in cached.planned], notices=cached.notices, set_aside=cached.set_aside)` — the ONLY place `feed_card` runs, so age is always serve-time.

`plan()` becomes a thin wrapper:
```
def plan(query, origin, runtime, *, k=10, viewer_id="anonymous") -> Feed:
    fc = runtime.feed_cache
    key = _anon_key(query, origin, k) if (fc and viewer_id == "anonymous") else None
    if key is not None:
        cached = fc.get(key)          # stats.hits/misses updated inside
        if cached is not None:
            return _render_feed(query, cached)   # honest re-rendered age
    # single-flight (below) wraps the compute+put for concurrent identical misses
    cached = _compute_plan(query, origin, runtime, k=k, viewer_id=viewer_id)
    if key is not None:
        fc.put(key, cached)           # only on success → never caches a failure
    return _render_feed(query, cached)
```
The cache check is **before** `parse_intent`, so a hit also skips the ~0.3s intent LLM. Keying on the raw query means two queries with identical parsed intent won't share an entry — accepted (measured intent cost small).

## New module orchestration/feed_cache.py (with its own tests, before callers)
Model directly on `orchestration/adapters/registry.py::TTLCache` (Rule #3: in-process, size-capped, TTL'd, never a graph node):
- `FeedCache(ttl_s: float, max_entries: int, *, clock=time.monotonic)` with a `threading.Lock` guarding `_store` + `stats`; expired-on-read eviction; FIFO cap `self._store.pop(next(iter(self._store)))` once `len >= max_entries` (identical discipline to registry.py:194-196).
- `get(key) -> CachedPlan | None`, `put(key, plan)`, `stats: FeedCacheStats(hits, misses)` with a `snapshot()` (mirror `ProbeStats`).
- `CachedPlan(planned, notices, set_aside)` — frozen dataclass.
- **Single-flight (grafted from Proposal 0, more rigorous):** on a miss, under the main lock get-or-create a per-key gate `(lock, waiters)`, increment `waiters`, release the main lock, acquire the gate lock, **re-check `get` under the gate** (another thread may have filled it → hit). Else run `_compute_plan` **outside the main lock** (the slow part — same rule TTLCache uses so distinct keys never serialize), `put`, and in a `finally` decrement `waiters` under the main lock and delete the gate at 0. Only identical `(query,origin,k)` requests serialize; distinct requests run fully parallel. Every path (hit-after-wait, compute success, compute exception) must hit the finally or a gate leaks / a key wedges.
- Module singleton `default_feed_cache()` (mirrors `registry.default_cache()`), constructed from Settings and injected via `Runtime.feed_cache` so tests inject a fake with a fake clock. Correct because Render runs a single uvicorn worker (Dockerfile CMD, no `--workers`; render.yaml free tier) — same posture the probe TTLCache already relies on.

`Runtime` gains `feed_cache: FeedCache | None = None`. `build_runtime` wires `default_feed_cache()` when `settings.feed_cache_ttl_s > 0`, else `None` (0 disables → None → total no-op, fully reversible).

## Cache key
`_anon_key(query, origin, k) = (query, round(lat, 3), round(lon, 3), k)`, gated to `viewer_id == "anonymous"` (Rule #5: no private identity can enter the key by construction).
- **3-decimal rounding (~111m)** deliberately matches the probe layer's own resolution (registry.py:150 rounds points to 3 decimals). Within one 3-decimal cell the probe TTLCache already returns identical facts AND identical drive-time, so the ranked order and every fact are identical — keying at that resolution introduces **no aliasing beyond what registry.py already permits**. Region picker origins are fixed canonical coords, so real-world hit rate is high; rounding only absorbs coordinate jitter.
- `k` (1..20) changes the candidate cap in scout → required in key.
- **Region NOT in the key (minimal diff):** the cache is a per-process singleton; the process serves one fixed `settings.region`/`live_region` and dies (empty cache) on redeploy/restart, so region is invariant over the cache's whole life. Add a code comment stating this invariant; flag stamping region as an open question for if multi-region-per-process ever lands (would require threading region through Runtime — deferred to keep the diff small).

## TTL / size / config (env-tunable, 0 disables)
- New `Settings` field `feed_cache_ttl_s: float = 300.0`, read in `from_env` as `float(e.get("ADVENTURE_ANON_FEED_CACHE_TTL_S", "300"))` — mirrors the `live_probe_max_workers` precedent (config.py:102/229). **0 disables.** Default 300s sits mid the PO's 120-600s band; a 0 default would make S2 an inert no-op that misses the Wave-1 ~1s goal. **Flag for PO sign-off** (conservative alternative: 120s).
- Companion `feed_cache_max_entries: int = 512` from `ADVENTURE_ANON_FEED_CACHE_MAX_ENTRIES` (whole ranked plans heavier than single facts → smaller cap than registry's 4096); FIFO evict.

### Freshness argument (Rule #1)
Two layers: (1) the **displayed** age is re-rendered per serve, so the shown "Xm ago" is honest at any TTL — this is the exact property the probe TTLCache already has, preserved. (2) The only real effect is the underlying fact isn't re-probed for up to `feed_ttl` beyond its own `probe_ttl`; worst-case fact age = `probe_ttl + feed_ttl`. Min live TTL is 600s (drive-time, non-safety); safety TTLs are streamflow 1800s and weather/air/fire/alerts 3600s. At `feed_ttl=300s`, weather worst case 3900s vs 3600s permitted (~8%), drive-time 900s vs 600s. Because the *displayed* age stays honest, the user always sees the true age and can judge — fully Rule-#1-compliant. Keeping `feed_ttl <= 600s` (the min adapter TTL) also means a fresh /plan within the window would hit the still-warm probe and return the same fact, so cross-request behavior is consistent.

## Metrics honesty (grafted from Proposal 0 — api/observability.py + api/app.py, MERGE-SENSITIVE)
Add `feed_cache_hit: bool = False` to `PlanMetrics`. On a **hit**: report `feed_cache_hit=True`, `latency_ms=<real fast value>`, and **zero** `est_tokens`/`est_cost_usd`/`live_calls`/`cache_hits`/`cache_misses` — do NOT recompute cost from cached card text, or the telemetry fabricates spend that never happened. The API reads `FeedCache.stats` before/after (or checks the returned hit flag) to set this. On a miss the existing metrics block is unchanged.

## Edge cases
- viewer != anonymous → bypass entirely (never keyed/read/written; Rule #5).
- ttl == 0 → `runtime.feed_cache is None` → byte-identical no-op.
- compute raises (500 / anonymous judge failure) → propagates, nothing stored, next request retries.
- concurrent identical requests → single-flight computes once; waiters served from store.
- cold Render instance (post-idle) → empty cache, first request pays full latency (warm-path optimization, not a cold-start fix).
- rate limiter → a cache hit still passes the slowapi per-IP limiter (abuse guard upstream of and independent of the cache).

## Two-phase-render compatibility (out of Wave 1, must not preclude)
Caching `CachedPlan` keyed on inputs (not the FeedResponse shape) leaves the future cards-first/conditions-streamed split free: `feed_card` can be split into card-vs-condition rendering inside `_render_feed` without touching the cache. A later API-response cache (sub-100ms hits) can layer on top of this one but would then re-own the age-restaging problem — noted, not built.

## Rule-compliance summary
- #1: every reused fact keeps its live source + absolute `fetched_at`; displayed age re-rendered honest per serve; TTL bounded; failures never cached.
- #2: stores the existing ranked order verbatim; no re-ranking, confidence never enters key/eviction.
- #3: in-process, size-capped, TTL'd, never a graph node — registry.py precedent.
- #5: anonymous-only gate on read AND write; key cannot contain a private identity; non-anonymous bypasses entirely.
- #6: enrichment posture unchanged; disabled cleanly via TTL=0; a hit disclosed in metrics.

## AGENTS.md / merge risk
`orchestration/engine.py` and `api/app.py`+`api/observability.py` are merge-sensitive seams — call out in the PR, keep the `plan()` compute/render split mechanical, preserve the exact anonymous outcome. One logical change, independently shippable/reversible (TTL=0 or delete module + revert wrapper). `make check` green before handoff.

### Builder notes (binding)

- DO NOT cache the rendered Feed/FeedResponse. The whole correctness of this story rests on caching CachedPlan (facts with absolute fetched_at) and re-running feed_card() per serve. Verified: present.py:146 bakes the relative age ('just now'/'Xm ago') into FeedLine.text at render time, and schemas.py:38 FeedLineResponse.text carries that baked string on the wire — regular condition lines have NO absolute timestamp on the wire (only CardWarningResponse.observed_at does). A rendered-response cache would re-serve stale lines as fresher, worse than the probe TTLCache. AC-2.2 must lock this in; add a code comment warning against caching rendered strings.
- The plan() compute/render split is on a MERGE-SENSITIVE seam (engine.py). Keep _compute_plan byte-identical to today's body for the anonymous path: context_degraded stays False, use_personal_judge stays False, and the anonymous judge-failure MUST keep re-raising (engine.py:548). Because it re-raises from inside _compute_plan, put() is never reached — that is how failures stay uncached; do not add a try/except that swallows it.
- Single-flight gate: decrement waiters and delete the gate in a finally on EVERY path (hit-after-wait, compute success, compute exception), or a gate leaks or a key wedges. Run _compute_plan OUTSIDE the main lock (only inside the per-key gate), exactly like TTLCache runs adapter.probe() outside its lock — otherwise distinct keys serialize and the fan-out becomes a queue.
- Metrics on a hit must ZERO est_tokens/est_cost/live_calls — do not recompute cost from cached card text (that fabricates spend). This touches api/observability.py + api/app.py, both merge-sensitive; keep the diff to adding feed_cache_hit and the zeroing branch.
- Key uses round(lat,3)/round(lon,3) to MATCH registry.py:150 exactly (same spatial cell as the probe cache), not a finer rounding — finer rounding lowers hit rate without adding correctness, since within a 3-decimal cell the probe facts and drive-time are already identical.
- Region is intentionally NOT in the key (per-process fixed-region singleton, dies on redeploy). Add a code comment asserting this invariant; do not thread settings.region through Runtime for this story. Flag stamping region as an open question in the PR if multi-region-per-process is ever contemplated.
- Verify one residual risk before relying on 'fully static cached presentation': summarize_fact's hedge comes from planned.confidences (verify-time), frozen at capture. If confidence.compute has a wall-clock/freshness input, a cached card's hedge could be one bucket stale (bounded by feed_ttl, presentation-only, never affects ranking per Rule #2). Check orchestration/confidence.py; if it uses date.today()/now, note it in the PR and consider whether it's acceptable at the chosen TTL.
- Default TTL=300.0 ships the cache ENABLED (needed to hit the Wave-1 ~1s goal; a 0 default makes S2 inert). This is a behavior change on a merge-sensitive path — call it out in the PR and get explicit PO sign-off on the value (conservative fallback 120s). 0 remains the operator kill-switch.
- This story assumes S1 (skip personal-context reads for anonymous) may or may not have landed. The cache stores whatever _compute_plan produces for anonymous either way; the two stories compose but do not depend on each other. Do not couple them.
- Frontend has NO CI coverage, but this story is backend-only — no frontend files touched. Keep it that way (S3 owns the frontend). Use commit trailer 'Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>' per the repo doc (development-process.md), NOT the task prompt's 'Claude Fable 5'.

---

## S3 — Frontend stale-while-revalidate (judge-merged design)

**Panel verdict:** honesty-first proposal won 8.5 vs 7. Proposal 1 wins on the criterion the PO explicitly called out as the crux — 'stale hazard warnings must never read as current.' Verified against the actual code, the two proposals are near-identical on the mechanical spine (anonymous-only localStorage single-slot cache, versioned envelope, kill-switch, savedTrails house-style degrade), and both remove the perceived wait for returning anonymous visitors. They diverge on rule #1. Proposal 0 repaints the stored feed as-is and relies on a banner + a short (15-min) age cap to excuse frozen hazards and frozen relative ages; I confirmed this is genuinely unsafe-adjacent because mapFeed drops the raw observed_at (so ages can't be re-humanized) and a cleared safety warning still paints as a prominent current-looking hazard. Proposal 1 makes honesty structural: it neutralizes every live/ephemeral fact on paint via a pure toStalePaint transform and shows only the stale-degraded silence primitive (which is fully implemented and, today, produced by nothing — so S3 becomes the roadmap-requested first producer) plus an honest fetch-time age. That posture also lets the age cap be set for relevance, not safety. The one place Proposal 0 is genuinely better is flash-avoidance: Proposal 1's in-effect hydration would commit a skeleton frame before swapping (its own AC-3.1 says it must not), whereas Proposal 0's lazy useState initializer paints ready on the first commit. The merged design is Proposal 1's honesty-first mechanism with Proposal 0's lazy-seed initializer grafted in (used in BOTH the initializer and the retune re-hydration via one shared helper), plus Proposal 0's explicit empty/error write-gate. GO for Wave 1: frontend-only, reversible via kill-switch, independently shippable, composes with S1/S2, and delivers the biggest perceived-latency win for return visits while staying rule-#1-clean.

## S3 — Frontend stale-while-revalidate for the anonymous Home feed (honesty-first, flash-free)

Paint the previous session's anonymous Home feed from localStorage on the first commit (no skeleton), then revalidate behind it. Honesty is structural, not disclosed-around: the repainted feed carries NO live/ephemeral assertions — every warning, condition line, and feed-level guardrail disclosure is stripped and replaced by the already-built `stale-degraded` silence primitive; the only age shown is derived from the real fetch timestamp. A client-local cache of a derived feed — same rule-#3/#6 posture as `savedTrails.ts` and the probe TTLCache; never a graph write/node.

### New module: `frontend/src/data/feedCache.ts` (mirrors savedTrails.ts house style)

```
const STORAGE_KEY = 'adventure-planner:anon-feed-cache'   // single namespaced slot; new key overwrites
const SCHEMA_VERSION = 1                                   // bump on ANY FeedVM shape change (no build-hash exists)
```

Envelope (JSON round-trip safe — verified FeedVM has no Date/fn/Map/Set): `{ v: number; key: string; savedAt: number; feed: FeedVM }`. **Store the TRUE fresh feed** (warnings included) — neutralization happens on read, so the cap and honesty rules govern presentation, not storage.

**One shared key helper (single source of truth), used by BOTH the cache and useFeed's effect dep so they can never diverge:**
```
export function feedKey(input: PlanInput, scope: ScopeContext): string =
  JSON.stringify({ t: input.tuning, k: input.k, v: scope.viewerId, g: scope.grantedIds })
```
`input.tuning` already contains `originCoords` (verified types.ts:63), so a one-off "near me" fix yields a distinct key — a stored feed from one geolocation can never repaint for another.

**Age cap / kill switch:** `MAX_STALE_MS` from `import.meta.env.VITE_ANON_FEED_STALE_MAX_MS`, default **21_600_000 (6h)**, `0` disables read AND write (S2's 0-disables convention). Build-time baked (Vite), same limitation as `VITE_USE_MOCK` — document it. **Ruling on the cap (PO asked):** because `toStalePaint` strips every live/ephemeral fact and discloses `stale-degraded`, the cap is NOT the safety mechanism — the transform is. The persisted content that actually paints is slow/structural (names, distances, geometry — legitimately Rule-#3 graph-class data). So the cap is set for *relevance* (catch a same-day return visit), not for bounding hazard staleness. 6h is defensible on that basis; hazards are honest regardless of the cap.

**`readFeedCache(key, nowMs): { feed: FeedVM; savedAt: number } | null`** — returns non-null only when EVERY guard passes, else null (conservative drop-on-any-doubt):
1. `typeof localStorage !== 'undefined'`
2. `MAX_STALE_MS > 0` (kill switch)
3. `try { JSON.parse }` — corrupt/foreign value → null
4. `entry.v === SCHEMA_VERSION` → else null (shape drift)
5. `entry.key === key` → else null (viewer/grant/tuning/k mismatch)
6. `nowMs - entry.savedAt <= MAX_STALE_MS` → else null (cap)
7. shape sanity: `entry.feed && Array.isArray(entry.feed.cards)` → else null

Note: the anonymous-only gate lives at the CALLER (useFeed), not inside read — read is a pure key match. useFeed only calls read/write when `scope.viewerId === 'anonymous'`.

**`writeFeedCache(key, feed)`** — caller invokes only for anonymous AND only on a successful, non-empty, non-error resolve (grafted from Proposal 0 — do not persist error/empty feeds; a stale "nothing holds" is confusing). `try { localStorage.setItem(...) } catch {}` — quota/serialization failure is swallowed.

**`toStalePaint(feed: FeedVM): FeedVM`** — pure, tested, applied ON READ:
- Per card: `conditionLines: []`, `warnings: []`, `enrichment: undefined`, `conditionSilence: { state: 'stale-degraded', detail: <staleAsOf label> }`. Keep `id`, `name`, `distanceMi`, `geo` (slow/structural, safe to repaint — verified rendered by the `stale-degraded` branch of ConditionBlock at RecommendationCard.tsx:118).
- Feed level: `notices: []`, `setAside: []`, `heldBack: []`, `readiness: { on: false, state: 'off' }`, keep `query`, keep `dataSource: 'live'` (it IS live-derived, just cached — the sample-strip is for mock only).
- Preserve card count/order so the fresh feed swaps in without layout jump.

**`staleAgeLabel(savedAt, nowMs)`** = `relativeAge(new Date(savedAt).toISOString(), nowMs)` — honest because `savedAt` is a real fetch timestamp (NOT the dropped per-fact `observed_at`), reusing existing age.ts.

**`resetFeedCacheForTests()`** — mirrors `resetSavedTrailsForTests` (savedTrails.ts:86) for hermetic tests.

### useFeed changes (PlannerProvider.tsx) — lazy-seed (no flash) + in-effect re-hydrate (retune)

Extend `FeedState` with honest state signals (NOT VM fields — the VM stays honest via `stale-degraded`): `stale: boolean`, `revalidating: boolean`, `staleAsOf?: string`, `revalidateError?: FeedError`.

**Shared hydrate helper** so mount and retune behave identically:
```
function hydrateStale(input, scope): { feed: FeedVM; staleAsOf: string } | null {
  if (scope.viewerId !== 'anonymous') return null
  const hit = readFeedCache(feedKey(input, scope), Date.now())
  if (!hit || hit.feed.cards.length === 0) return null
  return { feed: toStalePaint(hit.feed), staleAsOf: staleAgeLabel(hit.savedAt, Date.now()) }
}
```

**1. Lazy initializer (grafted from Proposal 0 — eliminates the skeleton flash; verified necessary because effects run after paint):**
```
const [state, setState] = useState(() => {
  const seed = hydrateStale(input, scope)
  return seed
    ? { status: 'ready' as const, feed: seed.feed, stale: true, revalidating: true, staleAsOf: seed.staleAsOf }
    : { status: 'loading' as const, stale: false, revalidating: false }
})
```

**2. Effect (keyed on `key` + nonce) handles mount revalidation AND retune re-hydration:**
- Re-read `const seed = hydrateStale(input, scope)`.
  - If `seed`: `setState({status:'ready', feed:seed.feed, stale:true, revalidating:true, staleAsOf:seed.staleAsOf})` and SKIP the loading-copy ladder (no reassure/coldstart timers — cards are already shown).
  - Else: existing behavior — `setState({status:'loading', stale:false, revalidating:false}); setLoadingStage('initial')` + the two ladder timers.
- Then `client.plan(input, scope)` exactly as today.
  - On resolve, non-error: `feedSnapshot.current = { scopeKey, tuning, feed }` (UNCHANGED); if anonymous AND `feed.cards.length > 0` → `writeFeedCache(feedKey, feed)`; `setState` ready/empty with `stale:false, revalidating:false`.
  - On revalidation error WHILE stale is showing: keep the stale feed, `revalidating:false`, set `revalidateError` — never blank good cards to the error screen.
  - On cold error (no stale seed): existing `status:'error'` branch, unchanged.

**`feedSnapshot.current` is written ONLY on a fresh resolve (as today) — deliberately NOT primed from the stale seed**, so `useCard`/Detail never resolve a card from the neutralized (stripped-condition) feed and never present a stripped card as authoritative. S3 stays scoped to Home. (Resolves the recon "reuse ref vs. separate module" question: separate module, ref contract for Detail unchanged, fully reversible.)

### Home.tsx disclosure + a11y

Home reads `{ stale, revalidating, staleAsOf, revalidateError }`. Because a stale paint renders in the `ready` branch (Home.tsx:174-233), the disclosure must render alongside ready content, above the card stack, reusing `state-note` styling (no new tokens):
- revalidating: `<p className="state-note" role="status" aria-live="polite">Showing your last visit ({staleAsOf}) — checking current conditions…</p>` — clears (unmounts) when the fresh feed lands.
- `revalidateError` set: `<p className="state-note" role="status">Couldn’t refresh — showing your last visit. Conditions may have changed.</p>` + a "Try again" button wired to `reload` (idempotent).
- **`aria-busy` stays `status === 'loading'` only** (grafted from Proposal 1's correct a11y reasoning): a usable stale feed is perceivable, not busy — the polite status line carries the "updating" signal instead.

Because `toStalePaint` empties `warnings`, `splitFeedWarnings(cards)` (Home.tsx:98) yields empty banner/perCard cleanly, and each card's ConditionBlock renders the `stale-degraded` silence (verified path RecommendationCard.tsx:118 → cardParts.tsx:265).

### Rule-compliance argument
- **#1 source-or-silence:** no stale live fact is ever asserted as current — warnings/lines/notices/heldBack/setAside are stripped and replaced by the disclosed `stale-degraded` silence; the only age shown is the honest fetch-time `staleAsOf`; loud, calm disclosure while refreshing; revalidation lands in ~4s warm/~9s cold.
- **#3 graph = slow/structural only:** localStorage cache of a derived feed, single-slot, env-TTL-capped, never a graph node — same posture as savedTrails + probe TTLCache.
- **#5 private-by-default:** read AND write gated on `scope.viewerId === 'anonymous'` at the caller; a non-anonymous viewer's feed never enters localStorage (no shared-machine/cross-device leak).
- **#6 degrade-and-disclose:** enrichment (a perceived-perf optimization); every failure mode (corrupt/quota/cap/kill-switch/revalidation error) degrades to the skeleton load or keeps the stale view with disclosure — never a dependency.
- **Two-phase render non-preclusion:** the stale paint is a single whole-FeedVM swap decoupled from condition-line timing; a future cards-first/conditions-streamed fresh path simply replaces the stale feed in phases.

### Edge cases
- Retune during a stale window: effect re-hydrates for the new key; tuning mismatch → miss → skeleton.
- Empty fresh result after a non-empty stale paint: transitions to `status:'empty'` with the fresh (empty) feed — honest.
- SCHEMA_VERSION drift after a FeedVM change: `v` mismatch → dropped → skeleton (conservative drop-on-doubt).
- Reduced motion: the instant stale cards were already "present," so the reveal-stagger simply does not apply on the seed paint (no new motion).

### Builder notes (binding)

- FLASH IS REAL: do NOT hydrate only inside the effect. useFeed's initial useState is {status:'loading'} and React commits that before useEffect runs, so an effect-only seed paints a skeleton frame first. Use the lazy useState initializer (grafted from Proposal 0) so the FIRST commit is already 'ready'. The effect still re-hydrates on key change (retune) via the same hydrateStale helper — use ONE helper in both places.
- ONE key helper: extract feedKey(input, scope) and use it for BOTH the cache key AND useFeed's effect dep (currently the inline JSON.stringify at PlannerProvider.tsx:181). If they drift, a cached feed can paint under the wrong frame. This also aligns S3's client key with S2's server request identity (recon's shared-key-derivation ask).
- HONESTY IS THE TRANSFORM, NOT THE BANNER: never repaint the stored warnings or the frozen observedAgo strings. Verified: relativeAge buckets to min/hour/day and mapFeed drops raw observed_at, so a repainted age is unfixable and a cleared hazard would render as a current-looking red WarningBlock. toStalePaint must empty warnings/conditionLines/notices/setAside/heldBack and set conditionSilence.state='stale-degraded' per card. The stale-degraded primitive is already fully built and rendered (cardParts.tsx:258-289 → RecommendationCard.tsx:118) and is currently produced by nothing — S3 is its first producer.
- Store the TRUE fresh feed; neutralize only on read. This keeps the write path a straight persist and makes the cap/honesty presentation-time concerns.
- feedSnapshot.current stays written ONLY on a fresh resolve — do NOT prime it from the stale seed, or useCard/Detail would resolve a card from the stripped feed and present it as authoritative.
- aria-busy must stay tied to status==='loading' only. A perceivable stale feed is not busy; carry the 'updating' signal via the role=status polite line instead.
- Write-gate: persist only a successful, non-error, non-empty feed (grafted from Proposal 0) — never a stale 'nothing holds' or an error.
- Env var VITE_ANON_FEED_STALE_MAX_MS is baked at build time (Vite), like VITE_USE_MOCK — document that changing the cap/kill-switch needs a rebuild. There is no frontend/.env.example today; do not create one — document in the frontend README or an inline comment.
- Bump SCHEMA_VERSION on ANY FeedVM shape change; readFeedCache must drop on any parse/version/shape doubt so an incompatible object can never reach card render.
- FRONTEND HAS NO CI (confirmed .github/workflows/ci.yml has no node/vitest job). S3 is frontend-only, so its correctness rests entirely on manually running: cd frontend && npm ci && npm run test && npm run build (tsc --noEmit) before handoff. make check (backend) will not catch a broken frontend.
- PlannerProvider.tsx is the merge-sensitive frontend data seam — keep the change a localized extension of useFeed (do NOT touch mapFeed or the wire contract) and call it out in the PR Merge-Risk section.
- Commit trailer: repo standard is 'Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>' (development-process.md) — the launch prompt's 'Claude Fable 5' trailer contradicts the repo; follow the repo doc.
- This is Epic 039 material per product-docs recon (repo tops out at 038, UX lane claims 019-026); verify no newer ~/.hike-lanes queue has reserved 039 before authoring the epic file, and run scripts/gen_epic_index.py after adding the README row.

---

## S4 — Skip the anonymous LLM taste-rank: DEFERRED

Defer stands; the PO prior is correct and no strong counter-argument survives. (1) Skipping the LLM taste-rank for anonymous is a PRODUCT-SEMANTICS change, not a latency lever: two load-bearing tests — test_anonymous_feed_has_no_degrade_notice (asserts the cloud judge was invoked) and test_anonymous_judge_failure_still_raises (asserts a ConnectionError propagates because the anonymous judge is exercised) — encode a deliberate decision that anonymous DOES get an LLM taste rank. Overturning S4 means rewriting them, which is out of a latency wave's scope and not silently reversible. (2) The deterministic pre-order (rank_plan: drive-time sort or scout distance order, then pure _apply_demotion of roadlike/boundary/over-length ids) is a fine FALLBACK — it already runs when the judge is absent/fails — but making it the anonymous DEFAULT flattens the primary anonymous surface to distance/drive-time order for every query where the cloud judge currently reorders on taste. The north-star is taste-ranked cards; trading that for speed on the most-visited (anonymous) surface is exactly the quality-first product's worst trade, and Rule #2 (confidence never penalizes rank) gives no cover for it. (3) The measured ~1.5–2.5s taste-rank cost is fully addressed by S2 (anonymous feed cache) + single-flight: the LLM runs once per (query,origin,k) per TTL window, not per request, so the warm floor drops toward the ~1s goal WITHOUT changing feed order. S2 amortizes the exact cost S4 would eliminate, and only the first cold miss pays it — an acceptable cold-path cost that the probe-worker bump (below) and a warm cache further blunt. Skipping the LLM would buy latency the cache already buys, at the price of order quality the cache preserves. No s4_design_md — verdict is defer.

---

## Operator note — probe fan-out concurrency

Env var: ADVENTURE_LIVE_PROBE_MAX_WORKERS (orchestration/config.py:102 default 8, read at config.py:229; flows via build_runtime -> runtime.probe_max_workers -> plan_from_origin -> verify_batch's ThreadPoolExecutor at verifier.py:148-149, which caps TOTAL in-flight (point,kind) probes for one /plan). Current default: 8. Recommended Render value: 16 (pure env change, no code). Per-source sanity: verify_batch fans out over 6 non-drive condition kinds — nws, airnow, firms, usgs_water, ridb, nps_alerts (valhalla/drive_time is excluded from the fan-out). At k=10 with distinct rounded trailhead points that is up to ~60 (point,kind) tasks. The task list is POINT-MAJOR ordered ([(key,kind) for key in groups for kind in kinds], verifier.py:137-139), so at any instant the in-flight window spans consecutive tasks and per-single-source concurrency is bounded by ~ceil(workers/6): 8 workers -> ~2 concurrent hits to any one source; 16 workers -> ~3. Three concurrent requests to a single third-party source is polite and well under any of these sources' rate limits. Benefit: ~60 tasks drain in ~4 waves instead of ~8, roughly halving the cold probe fan-out (measured ~3-5s cold). This is a COLD-ONLY win — the registry TTLCache (orchestration/adapters/registry.py) short-circuits repeats so warm /plan calls are unaffected; it pairs with the S2 anonymous feed cache rather than replacing it. Do not go far past 16 on the free-tier single instance: gains flatten (fewer waves left to cut) and per-source concurrency creeps up (24 workers -> ~4). Set ADVENTURE_LIVE_PROBE_MAX_WORKERS=16 in the Render service env; tune down if any source starts rate-limiting.


---

## Measurement verdict (2026-07-08, post-merge, live production)

Method: curl timings against the deployed API (same origin/query/k discipline as the baseline) + page-local timing on hike-app.vercel.app (same-origin iframe + MutationObserver — tool-driven polling was shown to inflate readings and was discarded).

| SLO (p75 targets) | Target | Measured | Verdict |
|---|---|---|---|
| Perceived first paint, returning anonymous visitor | < 1.0s | **0.385s** (stale paint, disclosure "Showing your last visit (3m ago) — checking current conditions…" shown at paint, cleared exactly at fresh swap) | **PASS** (already near the 0.5s end-state target) |
| `POST /plan`, cache hit | < 1.0s | **0.22–0.73s** (n=4, two keys; hit/miss card order byte-identical) | **PASS** |
| `POST /plan`, fresh-key miss, warm probes (retune) | < 4.0s | **3.53–3.93s** (n=3; ~0.3–0.5s under baseline via S1; LLM rank dominates as predicted) | **PASS** (thin margin — Tier A2/B1 are the next levers) |
| First-ever visit, cold everything | < 8s w/ staged copy | 7.0–9.4s API (2 regions) · 8.9s browser time-to-cards | **MARGINAL** — unchanged from baseline by design (Wave 1 never targeted it; the staged progress copy covers it; Wave 2 two-phase render is the fix) |
| Cold-start spin-down visible | tolerated (hobby tier) | unchanged | hosting decision, open |

Baseline for comparison: 8.77s cold / 3.67–3.95s warm floor on every load. **Typical returning-visitor experience: ~8.8s → ~0.3–0.4s (≈25×).** TTL behavior verified live: a revalidate that landed just past the 300s server TTL recomputed in 3.7s and re-warmed the key — exactly the designed degrade.

Residual gaps feeding the ladder: (A1) `ADVENTURE_LIVE_PROBE_MAX_WORKERS=16` on Render — operator click, pending; (A2) fast `curate`-tier model — cuts the retune path ~1.5–2s, needs a quality spot-check first; (B1) two-phase render — the only honest fix for the cold-everything row; to be designed as its own epic.
