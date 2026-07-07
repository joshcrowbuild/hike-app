# Epic 027 — Per-facet leveled ingest-diff check + stats on /health (within-run)

**Status:** REVIEW
**Phase:** A/B (ingest-safety tooling)
**Spec refs:** CoMaps borrow plan §B1 (verifier corrections — **reproduced verbatim-in-substance below** as B1.1–B1.4; the source `docs/research/comaps-borrow-plan.md` is not in the tree, so the inlined B1 text is authoritative and self-sufficient) · `docs/strategy/path-to-complete.md:136,154` (Phase-A/B ingest safety) · CLAUDE.md Rules #3/#6 · depends on Epic 024 (composite build-ID / `data_version` axis — this epic MERGES AFTER 024)

> **Line numbers below were read on 2026-07-06 and WILL drift.** Every anchor names the
> function/symbol too — re-grep the symbol, do not trust the bare number.

---

## Capability statement
After a re-ingest, the pipeline compares the new run against the region's pre-load corpus **per facet** (per source, per `way_type`, per elevation-presence, per named/unnamed) — not just on the single global trail total — so a class-specific collapse (NPS silently returns half, a `trail_filter` change over-drops one `way_type`, the whole elevation layer goes null) is **caught and blocks the prune** even while the total count stays comfortably above the 50% floor; the per-facet deltas are written to a `stats.json` surfaced on `/health`, sorted by `|delta|`.

## Architectural context

**Builds on:**
- The existing **within-run** scalar guard: `verify_before_prune` (`ingestion/pipeline.py:411-471`) and `prune_stale_trails` Guard 2 (`graph/load.py:385-517`) already compare each region's current-version count against its **pre-load total** (`pre_load_count`, snapshotted at `ingestion/pipeline.py:736` via `count_region_trails`, `graph/load.py:371-382`). This epic **extends that scalar snapshot into a facet-keyed dict** — the same comparison, done per class.
- The abs-AND-rel leveled-threshold pattern from CoMaps `tools/python/maps_generator/checks/default_check_set.py:61-73` (`make_default_filter`: `norm(r.diff) > threshold.abs AND get_rel(r) > threshold.rel`) and `:112-114` (per-type tuned `low/medium/hard` matrix). Port the **pattern**, not the substrate (CoMaps diffs two immutable `.mwm` directories — that substrate does not port; see binding correction B1.2).
- `/health`'s existing graph gauges (`api/app.py:_graph_stats`, ~`:294-352`; `GraphStats` model `api/schemas.py:188-204`) — `has_elevation` reuses the exact `total_gain_m IS NOT NULL` definition already used there (`api/app.py:311-312`).

**Enables:** the human-readable per-re-ingest regression report the roadmap's "prune doesn't self-heal and you can't see why" gap needs; the finer tier under the coarse `ADVENTURE_PRUNE_MIN_RATIO` floor; the facet-keyed shape that the deferred **persisted** cross-run baseline (F1-coupled) will later snapshot.

**Does NOT include (explicitly deferred — do NOT build):**
- **The persisted, facet-keyed baseline SNAPSHOT across runs.** This epic is **within-run only**: pre-load facets vs. this-run facets, exactly like the existing `pre_load_count` scalar. There is **no frozen prior baseline on disk or in the graph**, and you must not create one (binding correction B1.3). The cross-run persisted baseline is the F1-coupled bulk-of-effort piece, sequenced later.
- **`scripts/gen_state.py` wiring** / `state.json` integration. Out of scope. Surface on `/health` only.
- **Removing or weakening `ADVENTURE_PRUNE_MIN_RATIO` or `verify_before_prune`'s raising ABORT.** "Demote the ratio to a coarse floor" means it is no longer the *only* multi-trail defense — it **stays in place unchanged** as the coarse floor, and the `IngestVerificationError`-raising gate stays as the catastrophic backstop (binding correction B1.4). This epic only *adds* a finer tier above them.
- **The full composite cross-product** of the facet dimensions (source × way_type × has_elevation × named). This epic computes **marginal per-dimension buckets** (one bucket set per dimension), matching CoMaps' single-dimension per-type diff. See Design Decision 1.

### Binding verifier corrections (from the borrow plan §B1 — the builder cannot read that file; they are reproduced here verbatim-in-substance)
- **B1.1 — drop the scale framing.** Our current gate is NOT a single global constant: `verify_before_prune` already compares each region against its own `pre_load_count`, so the "50-trail-vs-2000-trail scale" example is **already handled for the total**. The genuine new value is per-**CLASS** granularity, not per-region scale. Do not re-pitch or re-solve scale.
- **B1.2 — pattern, not substrate.** CoMaps diffs two immutable `.mwm` directories (old-vs-new is free per build); that substrate does not port. Port only the `norm(diff)>abs AND get_rel>rel` leveled-filter *idiom*. `statistics.py` lives under `generator/`, not `checks/` — ignore it.
- **B1.3 — NO persisted cross-run baseline exists today, and you do not build one.** The comparison is within-run: pre-load facet counts vs. this-run facet counts. Extend the scalar `pre_load_count` into a facet-keyed dict; nothing is frozen to disk as a prior.
- **B1.4 — do NOT subsume the hard-ABORT gate.** Keep `verify_before_prune` (`ingestion/pipeline.py:411-471`, raises `IngestVerificationError`) as the catastrophic backstop. The facet suite is the finer tier: **report all buckets at the most-sensitive ("strict") level for visibility, but hard-gate (skip) the prune only on a "hard" abs+rel breach** — else noisy per-region churn blocks the pipeline. The facet check can only ever BLOCK a prune, never permit one.

### Design decisions (baked in so an unattended builder does not thrash)
1. **Facets are marginal per-dimension buckets, not the composite cross-product.** For a single-region run, `region` is the file scope (one `stats.json` per region), and the in-file bucket dimensions are `source`, `way_type`, `has_elevation`, `named`. Each bucket key is `"{dimension}={value}"`. This honors the `{region, source, way_type, has_elevation, named}` key set as the *dimension list* while staying tractable and matching CoMaps' per-type (single-dimension) diff. The full cross-product is deferred (Open Question 1).
2. **Bucket-value definitions** (all queryable from properties that already exist):
   - `source=<s>` — one bucket per distinct `SourceRecord.source` reached via `(:CanonicalTrail)<-[:SAME_AS]-(:SourceRecord)`. **Multi-valued:** a trail joined to `{OSM, USFS}` counts +1 in `source=OSM` and +1 in `source=USFS` (the bucket answers "how many trails does this source corroborate" — exactly the signal that catches "NPS returns half").
   - `way_type=<w>` — `t.way_type` (null → value `""`).
   - `has_elevation=true|false` — `t.total_gain_m IS NOT NULL` (the same gauge `/health` already uses, `api/app.py:311-312`).
   - `named=true|false` — `t.name IS NOT NULL AND trim(t.name) <> ""`. Near-constant `true` today (load requires a name), cheap and future-proofs the placeholder-name case; consistent with the borrow plan's empty-for-common-case philosophy.
3. **Pre snapshot** = ALL region trails across any `ingest_version` (the `_REGION_PRED` membership predicate, `graph/load.py:315`), grouped by each dimension, taken **before** `_load_matches` (right beside the existing `pre_load_count` at `ingestion/pipeline.py:736`). **Post snapshot** = current-`ingest_version` trails only (`ingest_version = $iv`), grouped by each dimension, taken **after** load + enrichment (so `has_elevation` reflects this run) and **before** the prune. This mirrors the existing `pre_load_count` (total, any version) vs `n_cur` (current version) comparison — the facet version of the identical logic.
4. **Diff & breach**: for each bucket key present in either snapshot, `delta = post - pre`; `rel_pct = abs(delta) * 100 / pre` with `pre == 0 → 100.0` (mirrors CoMaps `get_rel`, `check.py:39-47`). A bucket "breaches level L" iff `abs(delta) > abs_L AND rel_pct > rel_L` (the ported `make_default_filter` predicate). `breached_level` = the **coarsest (largest-threshold / least-sensitive) level the bucket breaches**, or null. Because the thresholds nest (`low=(100,50)` demands the biggest change, `strict=(10,10)` the smallest), any bucket that breaches `low` necessarily also breaches `medium`/`hard`/`strict`; reporting the coarsest level it clears makes `breached_level` **monotonically encode severity** — `low` = most severe, `strict` = mildest — by the severity order `low > medium > hard > strict`. This is a deliberate inversion of a naive "most-sensitive breached" (which would collapse every non-null bucket to `strict` and destroy the severity signal `worst_breached_level` and the `|delta|`-sorted feed depend on). Consequence: `breached_hard(rows)` (AC-1.6) == the buckets whose `breached_level ∈ {low, medium, hard}` (i.e. they clear the `hard` pair or coarser), so a bucket in `breached_hard` never reports `breached_level='strict'`.
5. **stats.json write is best-effort** (like `_persist_review_band`, `ingestion/pipeline.py:804-834`): a write failure is logged and swallowed, never a pipeline dependency (Rule #6 spirit). **The prune-block decision is computed in memory and must NOT depend on the file write succeeding.**

---

## Stories

### S1 — Leveled abs+rel facet-diff engine (`ingestion/checks/`)

**Given** two facet-count dicts (pre-load and this-run), each mapping `"{dimension}={value}" → count`,
**When** the diff engine runs them through the leveled abs+rel threshold matrix,
**Then** it yields one result row per bucket (`dimension`, `value`, `pre`, `post`, `delta`, `rel_pct`, `breached_level`), and reports which buckets breach at the "hard" level.

- **AC-1.1:** A new package `ingestion/checks/` exists with a pure-stdlib module (e.g. `ingestion/checks/facet_diff.py`) exposing the leveled threshold matrix and a diff function. No new third-party dependency is added.
- **AC-1.2:** The breach predicate is `abs(delta) > abs_threshold AND rel_pct > rel_threshold` — the abs-AND-rel gate ported from `default_check_set.py:61-73`. A test asserts a bucket over abs but under rel does NOT breach, and vice-versa (both conditions required).
- **AC-1.3:** `rel_pct` is computed as `abs(delta) * 100 / pre`, with `pre == 0` yielding `100.0` (ported `get_rel`, `check.py:43-45`). A test covers the `pre == 0` (new bucket) and `pre > 0` cases.
- **AC-1.4:** Four sensitivity levels `low`, `medium`, `hard`, `strict` are defined with `(abs, rel)` pairs, tuned down from CoMaps' `types` matrix (`default_check_set.py:112`, `low=(500,30) medium=(100,20) hard=(100,10)`) for regional (~1500-trail) scale. Starting matrix (the builder MAY retune the numbers, but MUST keep four ordered levels and the `hard < low` sensitivity ordering): `low=(100,50)`, `medium=(50,30)`, `hard=(25,20)`, `strict=(10,10)`. A test asserts `hard` is more sensitive than `low` (breaches on a smaller delta). The **severity order is the inverse of sensitivity**: `low > medium > hard > strict` (a `low` breach demands the biggest change, so it is the most severe); `breached_level` reports the coarsest level cleared per Design Decision 4, so it monotonically encodes severity.
- **AC-1.5:** The diff function returns rows for **every** bucket present in either snapshot (a bucket that vanished entirely — `post = 0`, `pre > 0` — appears with `delta = -pre`). A test covers a disappeared bucket and an appeared bucket.
- **AC-1.6:** A `breached_hard(rows) -> list[row]` (or equivalent) returns the buckets whose `abs(delta)`/`rel_pct` exceed the `hard` `(abs, rel)` pair — the set that gates the prune. Covered by a test with a mixed set (some breach hard, some only strict, some none). A separate test asserts the `breached_level` severity encoding: a bucket over the `low` `(abs, rel)` pair reports `breached_level='low'` (NOT `'strict'`), a bucket that clears only `strict` reports `'strict'`, and every bucket returned by `breached_hard` has `breached_level ∈ {low, medium, hard}` (never `'strict'`).

### S2 — Graph facet-count queries (`graph/load.py`)

**Given** a region and (optionally) a specific `ingest_version`,
**When** the pipeline snapshots facet counts before and after the load,
**Then** two read-only functions return `dict[str, int]` keyed `"{dimension}={value}"`.

- **AC-2.1:** `graph/load.py` gains `count_region_facets(runner, *, region_id) -> dict[str,int]` (pre-load: all region trails via `_REGION_PRED`, `graph/load.py:315`) and `count_version_facets(runner, iv, *, region_id) -> dict[str,int]` (post-load: current-version trails, `ingest_version = $iv`). Both are **read-only** (issue no writes) — the module docstring's world-layer/no-scope note (`graph/load.py:1-14`) and the access-control invariant (Rule #4) are preserved; these read only unowned `CanonicalTrail`/`SourceRecord` world nodes. **Do NOT reuse `_scalar_count`** (`graph/load.py:70`): it extracts a single scalar from `row[0]` only and cannot parse the grouped, multi-row result (`... AS value, count(...) AS n`) these facet queries return. Add a small `_grouped_counts(rows_or_result) -> dict[str,int]` helper that mirrors `_scalar_count`'s dual-shape duck-typing (`.single`/iterable `Result` vs materialized `list[dict]`) but **iterates every row**, keying `"{dimension}={value}" → n`.
- **AC-2.2:** The four dimensions (`source`, `way_type`, `has_elevation`, `named`) are counted with the value definitions in Design Decision 2. `has_elevation` uses `total_gain_m IS NOT NULL` (identical to `api/app.py:311-312`). A test with a **new grouped fake `Runner`** (the `list[dict]` shape, returning canned multi-row grouped rows keyed `{value, n}` per dimension) asserts each dimension produces the expected bucket keys. Do NOT reuse `_make_prune_runner` (`tests/test_load.py:22`): it matches on the `RETURN count(cur)`/`RETURN count(node)` substrings and returns a single-row `[{"n": ...}]`, which does not match the grouped `... AS value, count(...) AS n` queries; write a fresh grouped fake-Runner in the S2 tests.
- **AC-2.3:** The region-membership predicate is the SAME separator-anchored `_REGION_PRED` (`graph/load.py:315`) the prune/verify path uses — a bare `STARTS WITH region_id` (which would let "shen" match "shenandoah") is NOT introduced. A test asserts the query carries the `$prefix = "{region_id}-"` param.
- **AC-2.4:** `source` is multi-valued as specified (a trail with N sources contributes to N `source=*` buckets); the count reflects distinct `SourceRecord.source` per trail. Covered by a test.

### S3 — Wire the facet check into the pipeline + hard-gate the prune (`ingestion/pipeline.py`)

**Given** the pipeline has loaded a re-ingest and passed `verify_before_prune` (no raise),
**When** it evaluates the facet diff before pruning,
**Then** it writes `stats.json` and skips the prune iff any bucket breaches at "hard".

- **AC-3.1:** A pre-load facet snapshot is taken via `count_region_facets` immediately beside the existing `pre_load_count = count_region_trails(...)` (`ingestion/pipeline.py:736`), and a post-load snapshot via `count_version_facets(...)` after enrichment (after `ingestion/pipeline.py:762-765`) and before the prune (`ingestion/pipeline.py:784`).
- **AC-3.2:** The facet check runs **after** `verify_before_prune(...)` returns without raising (`ingestion/pipeline.py:776-783`) and **before** `prune_stale_trails(...)` (`ingestion/pipeline.py:784-786`). It does NOT replace, weaken, or wrap `verify_before_prune`; that raising gate is untouched (B1.4).
- **AC-3.3:** If any bucket breaches at the `hard` level, `prune_stale_trails` is **NOT called**; `counts["pruned"] = 0`, a new `counts["prune_blocked_facets"]` records the count of hard-breaching buckets, and the offending buckets (dimension=value, delta, rel_pct) are logged at WARNING. A test asserts a hard breach skips the prune call entirely.
- **AC-3.4:** If no bucket breaches at `hard`, `prune_stale_trails` runs exactly as today (unchanged call at `ingestion/pipeline.py:784-786`, `pre_load_count` still passed). A test asserts a healthy re-ingest (near-zero deltas) still prunes.
- **AC-3.5:** The facet check can only BLOCK a prune, never permit one `verify_before_prune` or the ratio guard would have blocked — it is purely additive (it runs after the raising gate and does not alter `prune_stale_trails`'s own Guards 1/2). Asserted by a test showing the ratio/empty guards still fire independently.
- **AC-3.6:** `stats.json` is written **best-effort** to `{stats_dir}/{region_id}.json` (see S4) with the buckets sorted by `abs(delta)` descending; a write failure (e.g. read-only FS) is logged and swallowed and does NOT affect the prune-block decision (which is computed in memory). Mirrors `_persist_review_band` (`ingestion/pipeline.py:804-834`). A test asserts a write failure does not raise and does not change the prune outcome.
- **AC-3.7:** `stats.json` schema: `{"region", "ingest_version", "generated_at" (ISO-8601), "prune_blocked" (bool), "buckets": [{"dimension", "value", "pre", "post", "delta", "rel_pct", "breached_level" (str|null)}]}` with `buckets` sorted by `abs(delta)` desc. Covered by a test on the serialized structure.

### S4 — Surface the diff on `/health` (`api/app.py`, `api/schemas.py`)

**Given** a `stats.json` on the API host for the served region,
**When** a client hits `/health`,
**Then** the response includes a compact facet-diff summary (top buckets by `|delta|`, worst breached level, prune-blocked flag), or null when the file is absent.

- **AC-4.1:** The stats path is resolved from a single shared helper so writer (pipeline) and reader (api) agree: default dir `data/ingest_stats`, env override `ADVENTURE_INGEST_STATS_DIR`, file `{region_id}.json`. The helper lives in `ingestion/checks/` (stdlib-only) and is imported by both sides (api already imports from `ingestion.*`, `api/app.py:70-71`). A test asserts writer and reader resolve the identical path for a given region.
- **AC-4.2:** `HealthResponse` (`api/schemas.py:256-261`) gains an optional `ingest_diff` field (a new small Pydantic model: `region`, `generated_at`, `prune_blocked`, `worst_breached_level` (str|null), `top_deltas` (list of the top ≤5 buckets by `|delta|`)). `/health` (`api/app.py:394-418`) populates it from `{stats_dir}/{_settings.region}.json`.
- **AC-4.3:** When the file is absent or unreadable, `ingest_diff` is `null` — degrade-and-disclose, never a 500 (Rule #1), mirroring `_graph_stats`'s `except: return None` (`api/app.py:349-352`). A test hits `/health` with no stats file and asserts `ingest_diff` is null and status is still 200/ok.
- **AC-4.4:** `top_deltas` is sorted by `abs(delta)` descending (the borrow plan's "sorted by |delta|"). A test asserts ordering.
- **AC-4.5:** Reading the file must not block or slow the Render readiness path meaningfully: it is a single small-JSON read with a caught exception; no graph query is added to `/health` for this feature. (The graph reads in `/health` are unchanged.)

---

## Definition of Done
- [ ] All ACs covered by at least one passing test (DB-free unit tests for S1/S2 via fake `Runner`; API tests via `TestClient` for S4; pipeline-wiring test for S3 with a fake runner/monkeypatched load).
- [ ] `make check` green (`ruff format --check` + `ruff check` + `mypy ingestion orchestration graph api evals` + `pytest -q -m "not neo4j"`).
- [ ] `ADVENTURE_PRUNE_MIN_RATIO` and `verify_before_prune`'s raising ABORT are demonstrably unchanged (kept as coarse floor + catastrophic backstop; B1.4).
- [ ] No persisted cross-run baseline was introduced (B1.3); no `scripts/gen_state.py` change.
- [ ] Targeted self-review agent run over the diff; every CRITICAL fixed.
- [ ] Epic file copied into `docs/epics/`; a row added to `docs/epics/README.md` index.
- [ ] Committed, pushed on `claude/facet-ingest-diff`, PR opened into `main` — **merges AFTER Epic 024**.
- [ ] Merge-sensitive api seams named in the PR: `ingestion/pipeline.py`, `api/app.py` (`/health`), and **`api/schemas.py`** (`HealthResponse` — this epic ADDS an optional `ingest_diff` field). If any concurrent wave lane also edits `api/schemas.py` `HealthResponse` or the `api/app.py` `/health` handler, the sequencer must serialize this lane after it rather than launch both blind (see Open Question 5).

## Open questions
1. **Composite cross-product vs. marginal buckets.** This epic ships marginal per-dimension buckets (Design Decision 1). The full `{source × way_type × has_elevation × named}` cross-product is deferred with the persisted baseline — confirm marginal is sufficient for the within-run tier.
2. **`named` signal is near-constant today** (load requires a name). It is included cheap for future placeholder-name trails; confirm it earns its bucket or drop it to three dimensions.
3. **Host-locality of `stats.json`.** `/health` on the Render API host only sees the file if ingestion wrote to a shared/co-located disk. Cross-host surfacing is the deferred persisted-baseline concern; within-run scope surfaces host-local + degrades to null (Rule #1) elsewhere.
4. **Threshold tuning.** The starting `(abs, rel)` matrix (AC-1.4) is scaled from CoMaps by eye; real re-ingest deltas across the four live regions should calibrate it before the "hard" bar is trusted to block a prune in CI.
5. **api-seam collision with concurrent lanes.** S4 edits `api/schemas.py` (`HealthResponse`, adding the optional `ingest_diff` field) and the `api/app.py` `/health` handler — both merge-sensitive api seams. If another wave lane touches `HealthResponse` or `/health`, the sequencer must serialize this lane after it (not launch both concurrently). `api/schemas.py` is a required touch-point even though it is not in the sequencer's headline file list.
