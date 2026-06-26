# Epic 005 — Valhalla Drive-Time Integration

**Status:** DONE ✅ — **delivered via Epic 013** (track-c, 2026-06-24); this doc is its sub-spec
**Phase:** 0 (spine) — drive time is a Phase-0 Verifier-overlay deliverable (decision-log §22); origin is single-user, no auth needed

> **Superseded-by note:** Epic 013 folds Valhalla in as a `drive_time` LiveAdapter behind the seam from the start (no standalone drive-time path to collide). The adapter (`ValhallaAdapter` + `fetch_matrix`/`fetch_isochrone`), the origin-relative Scout pre-filter (`orchestration/drive_time.py`), the `Intent.time_budget_s` field, the `valhalla_base_url`/`drive_speed_kmh` config, the ranking term, and the degrade-and-disclose path all shipped under Epic 013. The stories/ACs below are the design sub-spec they were built against.
**Spec refs:** Stage 4 §3 (Scout spatial query) · Stage 4 §5 (live adapters — the Valhalla line) · decision-log §5 (origin = runtime parameter) · §22 (drive time in Phase 0) · §27 (Valhalla self-hosted, native isochrones) · Rules #1, #2, #3, #10

> **Index reconciliation:** `epics/README.md` row 005 is titled "Valhalla drive-time **pre-Scout filter**" at `BACKLOG`/Phase 1. That title is wrong twice: (a) drive time is computed *after* Scout's spatial over-fetch and only prunes inward (Decision 1.4 — routing is the expensive fine filter, the point index is the cheap coarse one), and (b) decision-log §22 puts drive time in the Phase-0 spine, not Phase 1. The row should read "Valhalla drive-time integration (post-Scout prune + ranking input)", Phase 0, `DEFINED`. Correcting the index is part of this epic's DoD.

---

## Capability statement

A plan request resolves each candidate trail's **real road drive time from the request's origin** — and uses it to bound the Scout result set, inform ranking, and label each card — so the feed answers *"hikes within N minutes of where I am,"* not *"hikes within N straight-line metres,"* while degrading honestly to crow-flies distance when the router is down.

## Architectural context

**Builds on:** `orchestration/adapters/valhalla.py` (`fetch(origin, trailhead, base_url) → VerifiedFact | None` — **one source × one target** `sources_to_targets` call, source-or-silence on failure), `orchestration/engine.py` (`plan` / `plan_from_origin` / `rank_plan` / `feed_card`), `orchestration/scout.py` (`Candidate` carries `trailhead_id` + `point`; the spatial radius traversal), `orchestration/config.py` (`Settings`), `orchestration/intent.py` (`Intent.radius_m`).

**Enables:** travel-mode planning (decision-log §5 — "travel mode falls out for free"), an honest drive-time line on every feed card, and the §3 coarse→fine cost discipline (verify only candidates actually reachable in time).

**Does NOT include:** the *non-batch* adapter `fetch` itself (already exists); transit/walk/bike costing modes (auto only for Phase 0); persisting drive times as graph nodes (forbidden — Rule #3: drive time is origin-relative and ephemeral); per-segment turn-by-turn routing; a Valhalla *deployment* recipe beyond the config seam + dev compose stub (ops, not engine).

**Why an epic separate from the adapter:** the adapter is a pure `(origin, trailhead) → fact|None` leaf (Stage 4 §5). The hard parts are all *engine-side* — drive time is **origin-relative, not a point condition**, so it cannot ride the `verify(lat, lon, probes)` point-probe loop. It needs its own wiring into Scout's result set and the Curator's ordering, a degrade path, and (per the findings below) **three small enabling changes to existing code**: a batch/isochrone adapter call, an `Intent` time-budget field, and a ranking distance term. Those are scoped as stories here, not assumed away.

**Legend:** `decided` — settled, build it · `recommend-confirm` — proposed default, flag at build · `open` — needs a call before coding.

---

## 1. Design decisions (read before the stories)

- **1.1 — Drive time is computed at the engine layer, never as a point-probe.** `decided`. `verify(lat, lon, probes)` answers "what is true *at this location*"; drive time is a function of *(origin, trailhead-point)*. It is computed in `plan_from_origin`, which already holds the runtime origin, and folded into the candidate's facts. **Why:** keeps the point-probe contract `(lat,lon) → fact` clean and keeps the origin out of the per-candidate probe signature.

- **1.2 — Origin comes from the runtime parameter; the target is `candidate.point`.** `decided` (decision-log §5). `plan(query, origin, runtime)` threads the origin through; `plan_from_origin` already extracts each candidate's coordinate via `_latlon(candidate.point)` (engine.py). Drive time = matrix from `origin` to `_latlon(candidate.point)`, recomputed each request, **never written to the graph** (Rule #3 — a trail's drive time is meaningless without an origin). **Hazard to fix (S2):** engine.py currently *falls back to the query origin* when `candidate.point is None` (so it can probe *somewhere*). Routing that fallback would produce an origin-to-origin **"0 min"** — a fabricated fact. The drive-time path must therefore key on the candidate's *own* point and **skip** drive time entirely when `point is None`, independent of the probe fallback.

- **1.3 — Matrix for per-candidate time; isochrone for radius pruning — both require new adapter calls.** `recommend-confirm`. Stage 4 §5 names both ("drive-time isochrone / matrix"); §27 confirms Valhalla's native isochrones are *why* it was chosen. But the **current adapter does neither at scale**: `fetch` is one source × one target. Two endpoints, two jobs, two new functions (S4):
  - **Matrix** (`sources_to_targets`, one source × **K** targets) — exact drive time *per surviving candidate*. The adapter's existing body already posts to `/sources_to_targets`; extend it (or add `fetch_matrix`) to accept a *list* of targets and return a list of facts, so K candidates cost **one** HTTP call, not K. This is the value shown on the card.
  - **Isochrone** (`/isochrone`, new `fetch_isochrone`) — one polygon of "everywhere reachable in ≤ T minutes," computed *once per request*, used to **prune candidates before the Verifier** (the expensive stage). Point-in-polygon test runs in Python.
  - **Phase-0 fallback if isochrone is deferred:** the matrix-only path — one K-target matrix call over all Scout candidates, then drop those over budget. Correct, slightly more compute. The isochrone is the optimization (Stage 4 §3 coarse→fine), **not** a correctness requirement.

- **1.4 — Crow-flies radius stays the outer bound; drive time refines inward.** `decided`. Scout's existing `radius_m` straight-line query (Neo4j point index) runs first and is a **generous over-fetch**; drive-time pruning only ever *removes* candidates Scout returned — never reaches outside the spatial radius. **Why:** the point index is the cheap coarse filter, routing is the expensive fine filter; ordering them coarse→fine is the Stage 4 §3 cost discipline. The default radius must over-fetch enough that a fast-highway origin isn't clipped (a 40 km crow-flies radius can be 35 min on a back road or 25 min on an interstate — see 1.5).

- **1.5 — Time budget derives from the radius via a configurable speed; an explicit time budget is parsed when stated.** `recommend-confirm`. The user expresses tolerance as a radius (decision-log §5: "usual drive tolerance as default radius"). Convert `radius_m` → a drive-time budget via a configurable assumed road speed (default ~60 km/h ⇒ 40 km ≈ 40 min). **"Within 45 minutes" path requires an `Intent` change (S3):** `Intent.radius_m` is *metres-only* today (`intent.py` `PARSE_SYSTEM` defines it as "int drive radius in metres"); the time path needs a new `time_budget_s: int | None` field + a prompt update. When `time_budget_s` is set, use it directly as the budget; otherwise derive from `radius_m`. **Why a default speed, not a hard map:** keeps Phase 0 legible; the isochrone gives the *real* reachable set, the speed assumption only sizes the over-fetch and the matrix-only fallback.

- **1.6 — Drive time informs ranking via an explicit distance/effort term — never via confidence.** `decided` (Rule #2). **Mechanism to build (S5):** `rank_plan` today ranks purely by an LLM `rank_ids(items, …)` over `(id, name)` pairs — there is **no** distance/effort term, and `feed_card`'s distance is `candidate.distance_m` (crow-flies). This epic adds drive time as an explicit, legible ordering input (e.g. surfaced into the rank prompt or applied as a deterministic tie-break/penalty *outside* the confidence score). The Valhalla `VerifiedFact` carries `confidence_inputs={"authority": "derived", "freshness": "live"}` purely so its card line is phrased as a *derived* estimate, exactly as the adapter already stamps. **Why:** confidence governs *honesty of phrasing*, never *rank* (confidence.py docstring; Rule #2). A long drive lowers *position*, not *trust*.

- **1.7 — Valhalla unreachable ⇒ degrade-and-disclose, never block.** `decided` (Rule #1, Stage 4 §5). If the router errors / times out / rate-limits, the adapter returns `None` (it already does). The engine then: (a) keeps every candidate Scout found — falling back to the crow-flies radius as the *only* bound; (b) omits the drive-time line rather than fabricating one; (c) attaches a single disclosure that drive time is unavailable this run. **Why:** drive time is enrichment, not a gate — a router outage must not empty the feed (same "degrades-and-discloses" posture Rule #6 mandates for watch data; the principle generalizes to any non-authoritative live source).

---

## 2. Stories

### S1 — Self-hosted Valhalla wiring (config + seam)

**Given** a deployment with a self-hosted Valhalla reachable at a base URL
**When** the engine builds its runtime from `Settings`
**Then** the base URL is read from config (never hardcoded) and a drive-time computer is available to the engine; when no base URL is configured, drive time is simply absent (nothing fabricated)

**AC-1.1:** `Settings` exposes `valhalla_base_url: str | None`, read from `VALHALLA_BASE_URL` (default `None`); `.env.example` documents it.
**AC-1.2:** `Settings` exposes the road-speed assumption `drive_speed_kmh: float` (default `60.0`, via `DRIVE_SPEED_KMH`) used by Decision 1.5; absence of the var yields the documented default, never a crash.
**AC-1.3:** When `valhalla_base_url` is `None`, the engine runs end-to-end with **no** drive-time line on any card and **no** drive-time pruning — byte-for-byte the current feed (parity with the verifier's "missing key ⇒ probe simply absent" pattern).
**AC-1.4:** When `valhalla_base_url` is set, `build_runtime` wires a drive-time computer onto `Runtime` (new optional field, e.g. `Runtime.drive_time`), bound to that base URL via the Valhalla adapter; the URL is sourced from `Settings`, never a literal in engine code (Rule #10). The computer's signature takes the origin + the list of candidate **coordinates** (not `trailhead_id`s — the adapter routes on lat/lon) and returns one fact per coordinate, aligned by index.
**AC-1.5:** Drive time is **not** added to `build_probes` (it is origin-relative, not a `(lat,lon)` point probe — Decision 1.1); `verify()`'s signature and the point-probe contract are unchanged.

### S2 — Origin-to-trailhead drive time on each candidate

**Given** a configured Valhalla and a plan request with a runtime origin
**When** `plan_from_origin` produces candidates that survive the guardrail filter
**Then** each surviving `PlannedTrail` carries a drive-time `VerifiedFact` from the **request's origin** to that candidate's own point, sourced and timestamped

**AC-2.1:** Drive time is computed with `origin = the runtime (lat, lon)` passed to `plan` / `plan_from_origin` — **not** a stored or default origin (decision-log §5; Decision 1.2).
**AC-2.2:** The per-candidate target is `_latlon(candidate.point)`. When `candidate.point is None`, drive time is **omitted** for that candidate — the engine does **not** route to the query-origin probe fallback (that would yield a fabricated origin-to-origin "0 min" — Decision 1.2 hazard). A test asserts a `point=None` candidate gets a card with **no** drive-time line and is **not** assigned a 0-minute time.
**AC-2.3:** `PlannedTrail` is `@dataclass(frozen=True)` — the drive-time fact is folded into the `facts` dict **at construction time** in `plan_from_origin` (under key `"drive_time"`), not mutated onto an already-built instance. A test that the existing `feed_card` renders the line with **no** special-casing (it already iterates `planned.facts`).
**AC-2.4:** The fact's `source` is `"Valhalla (self-hosted)"` and `fetched_at` is the call time (as the adapter already stamps) — every drive-time figure on a card carries source + timestamp (Rule #1).
**AC-2.5:** The computed drive time is **never written to Neo4j** — no Cypher in this path creates or sets a drive-time property/node (Rule #3). A test asserts the graph is unchanged after a `plan()` call.

### S3 — Time budget: derive from radius, parse when stated

**Given** a plan request expressing tolerance as a metre radius or as a time ("within 45 minutes")
**When** the engine computes the drive-time budget
**Then** a stated time is used directly, otherwise the radius is converted via the configured speed

**AC-3.1:** `Intent` gains `time_budget_s: int | None = None`; `intent.py` `PARSE_SYSTEM` is updated to extract it ("within N minutes/hours" → seconds), and malformed/absent output yields `None` (the existing robustness contract — any bad output → empty `Intent`, never a crash).
**AC-3.2:** When `intent.time_budget_s` is set, it is the budget directly. When it is `None`, the budget = `radius_m / (drive_speed_kmh in m/s)` (Decision 1.5). Both paths are tested.
**AC-3.3:** `radius_m` remains the **distance** field (unchanged semantics); the time path never overwrites or reinterprets it. A request with neither field falls back to `DEFAULT_RADIUS_M` and its derived budget.

### S4 — Isochrone vs. matrix usage (batch adapter calls)

**Given** K candidates from Scout
**When** the engine resolves drive times
**Then** it uses **one isochrone call** to prune and **one K-target matrix call** for exact per-candidate times (or the documented matrix-only fallback), never a per-candidate routing call in a loop

**AC-4.1:** The adapter is extended for batch: a matrix call accepting **one source × a list of K targets** returns K facts in one HTTP round-trip (the existing `fetch` one-to-one stays for callers that want it). A test asserts K candidates ⇒ exactly **one** `/sources_to_targets` POST, not K.
**AC-4.2:** A new `fetch_isochrone(origin, time_budget_s, base_url) → polygon | None` (same source-or-silence contract) issues **at most one** `/isochrone` request per `plan()` call; candidates are then tested point-in-polygon in **Python** (no per-candidate Valhalla round-trip).
**AC-4.3:** A candidate outside the isochrone polygon (or, in the matrix-only path, whose matrix time > budget) is excluded from the Verifier stage and the feed; a candidate inside / ≤ budget is retained. Boundary candidates are treated as *included* (≤, not <).
**AC-4.4:** Pruning happens **after Scout, before the Verifier loop**, so a pruned candidate incurs **no** live-condition probes (the Stage 4 §3 coarse→fine lever — verify few, not all). A test asserts no probe is invoked for an out-of-budget candidate.
**AC-4.5:** If the isochrone endpoint is unavailable but matrix is reachable, the engine falls back to the matrix-only path (compute all K times, drop over-budget) and still produces a correct feed (Decision 1.3 fallback).
**AC-4.6:** Total routing cost is bounded by candidate count: N Scout candidates ⇒ ≤1 isochrone + ≤1 matrix call, independent of N. A test covers the count.

### S5 — Drive time as a ranking input (never via confidence)

**Given** candidates carrying drive-time facts
**When** the Curator orders the feed
**Then** drive time influences position via an explicit distance/effort term, and never enters the confidence score

**AC-5.1:** `rank_plan` is extended to surface drive time into ordering (e.g. include the per-candidate drive minutes in the `rank_ids` item payload, or apply a deterministic drive-time penalty/tie-break around the LLM order). A test that, all else equal, a closer-by-road candidate is not ranked below a far one solely due to road distance.
**AC-5.2:** Drive time is **not** passed into `confidence` / `compute` for any candidate; a long drive never lowers a candidate's `Confidence` (Rule #2; confidence.py docstring). A test asserts a far candidate and a near candidate with identical fact freshness/authority get identical confidence.
**AC-5.3:** When drive time is absent (router down, or `point is None`), ranking falls back to today's behavior (LLM order over `(id, name)` / crow-flies `distance_m`) with no crash and no penalty applied to the missing-time candidate (absence ≠ "far").

### S6 — Graceful degrade-and-disclose when Valhalla is unreachable

**Given** a configured Valhalla that errors, times out, or rate-limits mid-request
**When** the engine attempts to resolve drive times
**Then** the feed is still produced — bounded only by the crow-flies radius — with drive-time lines omitted (never fabricated) and a single honest disclosure

**AC-6.1:** When the adapter returns `None` (any failure), `plan()` still returns a non-empty feed for an origin that has candidates — the outage does not empty or crash the feed (Rule #1, Decision 1.7).
**AC-6.2:** On router failure, **no** candidate is dropped for being "too far by road" — the crow-flies `radius_m` becomes the sole bound (never silently lose a reachable trail because the router was down).
**AC-6.3:** No fabricated drive time appears anywhere — affected cards simply have no drive-time line (source-or-silence — Rule #1).
**AC-6.4:** A single, legible disclosure surfaces once (a feed-level or card-level warning, e.g. "Drive times unavailable this run") rather than per-card spam; phrased as a *capability gap*, not an error.
**AC-6.5:** A **partial** failure (matrix returns times for some targets, `None`/missing for others) degrades per-candidate: candidates with a time get a line and are budget-checked; candidates without a time keep their card, get no line, and are **not** pruned (absence of a drive time is never "too far").
**AC-6.6:** The failure path makes no retry storm — an outage costs at most the configured call(s) per request, then degrades (it "never blocks the feed", Stage 4 §5).

---

## 3. Definition of Done

- [ ] All ACs covered by at least one passing test (mocked Valhalla responses — success, over-budget, total outage, partial failure — per Stage 4 §5's "mocked-response integration tests, degrade-and-disclose on outage").
- [ ] `make check` green (ruff + mypy + pytest).
- [ ] Targeted review agent run — verify: **Rule #3** (no drive time persisted to the graph), **Rule #1** (no fabricated time on any path, including the `point=None` / origin-fallback hazard), **Rule #2** (drive time never enters `confidence`, only the explicit ranking term), origin sourced from the runtime parameter (decision-log §5), config-only base URL (Rule #10). CRITICALs fixed.
- [ ] End-to-end: a `plan()` against the Shenandoah+GWJ pilot origin produces cards with sourced drive-time lines; the same call with Valhalla mocked-down still produces a feed with the disclosure.
- [ ] `epics/README.md` row 005 corrected (title → "Valhalla drive-time integration (post-Scout prune + ranking input)", Phase → 0) and status advanced.
- [ ] Committed and pushed.

---

## 4. Implementation notes

**Config additions** (`orchestration/config.py` + `.env.example`):

```python
valhalla_base_url: str | None = None        # VALHALLA_BASE_URL
drive_speed_kmh: float = 60.0               # DRIVE_SPEED_KMH — radius→time-budget assumption (Decision 1.5)
```

**Adapter additions** (`orchestration/adapters/valhalla.py`, same source-or-silence contract):

- Extend the matrix path to a **one-source × K-targets** call returning a list of `VerifiedFact | None` aligned to the targets (the body already posts `sources` + `targets` to `/sources_to_targets` — make `targets` the candidate list). Keep `fetch` (one-to-one) for any single-pair caller.
- Add `fetch_isochrone(origin, time_budget_s, base_url) → polygon | None` (POST `/isochrone`, one location + the time contour). Point-in-polygon test lives in the engine (Python) — no extra round-trip per candidate.

**Runtime + engine seam** (`orchestration/engine.py`):

- Add optional `drive_time` to `Runtime`, wired in `build_runtime` **only** when `valhalla_base_url` is set (AC-1.4). When unset, every drive-time step is skipped (AC-1.3).
- In `plan_from_origin`: after Scout, before the Verifier loop, build the candidate-coordinate list from `_latlon(candidate.point)` (dropping `None`s — Decision 1.2), prune by isochrone/matrix (S4), then **construct** each surviving `PlannedTrail` with the drive-time fact already in `facts["drive_time"]` (S2 — `PlannedTrail` is frozen, so fold it in at construction, never mutate).

**Intent** (`orchestration/intent.py`): add `time_budget_s: int | None`, extend `PARSE_SYSTEM` to extract a stated time, parse defensively (S3).

**Ranking** (`rank_plan`): thread drive minutes into the ordering as an explicit term — never into `confidence` (S5; Rule #2).

**Why drive time rides `facts["drive_time"]`, not a new field:** `feed_card` already iterates `planned.facts` and renders each via `summarize_fact` with its `Confidence`. Keying drive time as just another verified fact means the card line, the hedged phrasing, and the source/timestamp stamp all come for free — and the source-or-silence guarantee (a `None`/absent fact is simply not shown) applies unchanged (Rules #1, #2).
