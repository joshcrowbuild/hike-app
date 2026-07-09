# Epic 039 — Feed first-paint latency (Wave 1)

**Status:** REVIEW (2026-07-08 · PRs #151 S1 · #152 S2 · #153 S3; adversarial review done, 3/3 confirmed findings fixed; measurement gate pending post-merge)
**Phase:** A
**Spec refs:** roadmap R5 (cost/latency — first measured baseline) · CLAUDE.md rules #1/#3/#5/#6 · design record [`../research/feed-first-paint-latency-wave1.md`](../research/feed-first-paint-latency-wave1.md)

---

## Capability statement

An anonymous visitor sees trail cards in ~1s on a typical load instead of ~8s — without a single stale fact ever presented as current.

## Architectural context

**Builds on:** the probe `TTLCache` precedent (Epic 013, `orchestration/adapters/registry.py` — in-process TTL caching is the settled rule-#3-compliant cost lever); the `stale-degraded` condition-silence primitive (design-system honesty primitives — fully built, produced by nothing until S3); the in-memory `feedSnapshot` ref (UX assembly plan).
**Enables:** the future two-phase-render epic (cards first, live conditions streamed in); a real R5 cost/latency measurement loop.
**Does NOT include:**
- Two-phase render (future epic; these designs must not and do not preclude it).
- Parallelizing the engine's sequential graph reads (superseded by two-phase later).
- **S4 — skipping the LLM taste-rank for anonymous: DEFERRED.** Two load-bearing tests (`test_anonymous_feed_has_no_degrade_notice`, `test_anonymous_judge_failure_still_raises`) encode "anonymous gets a real taste rank" as deliberate product semantics; reversing that is a product decision, not a latency lever. See design record §S4.
- Any caching for non-anonymous viewers (rule #5 posture: private paths stay uncached in Wave 1).

**Measured baseline** (live API, 2026-07-08): `POST /plan` = **8.8s** with cold probe caches, **3.7–4.0s** warm floor (k=1 ≈ k=10). Attribution: live-probe fan-out ~3–5s (cold only) · LLM taste-rank ~1.5–2.5s (every call — dominates the warm floor) · ~6 sequential Aura round trips ~1.5–2s (three of them personal-context reads that run even for anonymous) · intent-parse LLM ~0.3s. Frontend blocks first paint entirely on this one request.

---

## Stories

### S1 — Anonymous fast-path (skip personal-context reads)

**Given** an anonymous viewer
**When** `plan()` runs
**Then** the beliefs/profile/episodes graph reads are skipped entirely, with behavior otherwise byte-identical — no degrade notice (a deliberate skip is not a degrade).

**AC-1.1:** For `viewer_id=="anonymous"`, `plan()` issues ZERO belief/profile/episode Cypher reads — a spy session recording every runner query sees no `MATCH (b:Belief)`/`(pp:PhysicalProfile)`/`(e:Episode)` statement.
**AC-1.2:** For `viewer_id=="anonymous"`, the returned Feed (cards, notices, set_aside) is identical to the pre-skip behavior given the same inputs; in particular notices contains NO `PERSONAL_CONTEXT_UNAVAILABLE_NOTICE` (deliberate skip is not a degrade; `context_degraded` stays False).
**AC-1.3:** For a non-anonymous `viewer_id`, all three reads STILL run and `assemble_context` is still called (regression guard: the skip is anonymous-only).
**AC-1.4:** `use_personal_judge` stays False for anonymous, so the plain cloud `runtime.judge` is still invoked (preserves `test_anonymous_feed_has_no_degrade_notice`) and an anonymous judge failure still re-raises (preserves `test_anonymous_judge_failure_still_raises`).

### S2 — Engine-layer anonymous plan cache (freshness re-rendered per serve)

**Given** two identical anonymous `/plan` requests (same query, 3-decimal-rounded origin, k) within the TTL
**When** the second arrives
**Then** it is served from an in-process cache of the *computed plan* (facts with absolute timestamps), with `feed_card()` re-run per serve so every displayed age is honest at serve time — never a cached rendered string.

> **Design crux (adversarial-panel verdict):** `present.py` bakes relative ages into `FeedLine.text` and regular condition lines carry no absolute timestamp on the wire — so a response-layer cache would re-serve stale copy as fresher. The cache therefore lives at the engine layer, stores `CachedPlan` (not `Feed`/`FeedResponse`), and re-renders presentation per serve.

**AC-2.1:** With `feed_cache_ttl_s>0`, two identical anonymous `plan()` calls for the same (query, 3-decimal-rounded origin, k) run `_compute_plan` (parse_intent + rank_plan) exactly once; the second is served from cache (spy provider/judge invoked on call 1 only; `FeedCache.stats.hits` increments).
**AC-2.2:** The cached path re-renders freshness per serve — a plan cached at t0 (fact with fixed fetched_at) and served at t0+delta via an injected clock renders `_age` against serve-time now, so the displayed line age reflects delta, never the frozen capture-time age.
**AC-2.3:** `viewer_id != 'anonymous'` never reads or writes the feed cache (a non-anonymous call after an anonymous one recomputes; `stats.hits` unchanged) — Rule #5.
**AC-2.4:** `feed_cache_ttl_s==0` makes `plan()` a no-op vs today — `runtime.feed_cache` is None, no cache object wired, no behavior change.
**AC-2.5:** A `plan()` that raises inside `_compute_plan` (e.g. anonymous judge ConnectionError) is never stored — the next identical call misses and re-raises (`stats.misses` increments, hits does not).
**AC-2.6:** `FeedCache` honors TTL expiry (entry past `ttl_s` is a miss + evicted on read) and the FIFO size cap (inserting beyond `max_entries` evicts the oldest; len never exceeds cap), verified with an injected clock.
**AC-2.7:** A cache hit returns a Feed equal to a freshly computed Feed for the same inputs in cards/order/notices/set_aside (given fixed live facts), differing only in the re-rendered age copy — order and set-aside semantics preserved.
**AC-2.8:** Single-flight — N concurrent identical anonymous requests invoke `_compute_plan` exactly once; all N receive the same CachedPlan/Feed; the per-key gate is released on hit-after-wait, success, and exception paths (no leak/wedge).
**AC-2.9:** On a feed-cache hit, PlanMetrics is emitted with `feed_cache_hit=True` and `est_tokens=0`, `est_cost_usd=0`, `live_calls=0`, `cache_misses=0` — no fabricated spend for a call that ran no LLM or probe (cost NOT recomputed from cached card text).
**AC-2.10:** `feed_cache_ttl_s` (default 300.0) and `feed_cache_max_entries` (default 512) are read from `ADVENTURE_ANON_FEED_CACHE_TTL_S` / `ADVENTURE_ANON_FEED_CACHE_MAX_ENTRIES` in `Settings.from_env`, with 0 disabling.

> **PO sign-off recorded (2026-07-08):** ships **ENABLED**, TTL default **300s**. Safe because every live adapter's `ttl_seconds` is ≥600s (valhalla 600 · streamflow 1800 · weather/air/fire/nps 3600 · ridb 86400), so a cached serve can never present staler facts than the probe TTLCache already permits — and ages re-render per serve. `ADVENTURE_ANON_FEED_CACHE_TTL_S=0` is the operator kill switch.

### S3 — Frontend stale-while-revalidate (honesty-first stale paint)

**Given** a returning anonymous visitor whose last feed for the exact same scope+tuning is cached in localStorage and within the age cap
**When** Home mounts
**Then** the FIRST committed render paints that feed instantly with every live/ephemeral fact neutralized (no warnings, no asserted condition lines; every card in the `stale-degraded` condition-silence state; only an honest fetch-time age shown), and the normal `/plan` revalidation runs behind it.

**AC-3.1:** Flash-free instant stale paint: for an anonymous viewer with a cached feed matching the exact feedKey and within MAX_STALE_MS, useFeed's FIRST committed render is `status='ready'` with `stale=true` and `revalidating=true` — the skeleton 'loading' state is never committed before the paint (satisfied by the lazy useState initializer, not the effect).
**AC-3.2:** Revalidate-behind + write-through: after a stale paint, `client.plan()` is called once; on a successful non-empty resolve useFeed transitions to the FRESH feed with `stale=false`, `revalidating=false`, and the fresh (un-neutralized) feed is persisted under feedKey.
**AC-3.3:** Staleness honesty (rule #1): the stale-painted feed carries no warnings and no asserted condition lines; every card exposes `conditionSilence.state==='stale-degraded'`; feed-level notices/setAside/heldBack are emptied and readiness is off — no stale hazard or frozen per-fact age is ever repainted as current. The only age shown is `staleAsOf`, derived from the stored fetch timestamp.
**AC-3.4:** Age cap / kill switch: a cached entry older than `VITE_ANON_FEED_STALE_MAX_MS` is not painted (normal skeleton load); `VITE_ANON_FEED_STALE_MAX_MS=0` disables both read and write; unset defaults to 6h.
**AC-3.5:** Anonymous-only + invalidation + degrade: a non-anonymous viewer never reads or writes the cache; a stored entry is ignored on any mismatch of viewer/grants, tuning (incl. originCoords), k, or SCHEMA_VERSION; corrupt JSON returns null and a quota-throwing setItem is swallowed — both degrade silently to the skeleton load without throwing.
**AC-3.6:** Write-gate: only a successful, non-error, non-empty feed is persisted; `feed.error` and `cards.length===0` feeds are never written (no stale 'nothing holds' or error is ever repainted).
**AC-3.7:** Revalidation error keeps stale usable: a `plan()` rejection WHILE a stale feed is painted leaves `status='ready'` with the stale feed, `revalidating=false`, `revalidateError` set, and a working retry — never the full-screen error state; a rejection with NO stale paint still yields `status='error'`.
**AC-3.8:** Calm disclosure + a11y: while stale-painted, Home renders a `role='status'` `aria-live='polite'` note "Showing your last visit (<age>) — checking current conditions…" that clears when the fresh feed lands; the results wrapper does NOT set aria-busy while a usable stale feed is shown.
**AC-3.9:** Detail unaffected: `feedSnapshot.current` is written only on a fresh resolve, never from the stale seed, so useCard/Detail never resolve a card from the neutralized feed.

---

## Operator levers (no code — Render env)

- `ADVENTURE_LIVE_PROBE_MAX_WORKERS`: **8 → 16**. Bounds total in-flight (point,kind) probes per `/plan` (`verifier.py` ThreadPoolExecutor). At k=10 × 6 condition kinds ≈ 60 tasks, 16 workers roughly halves the cold fan-out wall-clock; point-major task order keeps the per-source concurrency well under courtesy limits. See design record for the per-source math.
- `ADVENTURE_ANON_FEED_CACHE_TTL_S=0` — S2 kill switch (post-merge).
- `VITE_ANON_FEED_STALE_MAX_MS=0` — S3 kill switch (build-time; needs a frontend rebuild).

---

## Definition of Done
- [ ] All ACs covered by at least one passing test
- [ ] Backend: `make check` green. Frontend (S3): `cd frontend && npm ci && npm run test && npm run build` green — **frontend has NO CI job; this gate is manual**
- [ ] Multi-dimension adversarial review run per story branch; every CRITICAL fixed before the PR goes out, MODERATE+ documented in the PR
- [ ] One PR per story into `main` (PR template; merge-sensitive seams called out: `orchestration/engine.py` [S1+S2], `api/` [S2], `frontend/src/data/PlannerProvider.tsx` [S3]; S1 merges before S2 — S2 rebases its `plan()` split over S1's guard)
- [ ] Epic index row synced (`python scripts/gen_epic_index.py --check` clean)
