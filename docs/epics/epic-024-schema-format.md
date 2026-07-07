# Epic 024 — Integer `schema_format` on Meta + API-startup compatibility gate on /health

**Status:** DONE ✅
**Phase:** 0 (spine hardening)
**Spec refs:** comaps-borrow-plan.md item A4-lite (wave 1) · CLAUDE.md Rule #1 (source-or-silence) · "fail loud at boundaries, degrade gracefully at the surface" · CoMaps `libs/platform/mwm_version.hpp` (borrowed pattern)

---

## Capability statement
The graph carries a distinct **integer** `schema_format` stamp on its `:Meta` node, and the API validates that stamp at startup so that an **old API pointed at a newer-schema graph refuses to serve** — surfacing the mismatch on `/health` (degrade-and-disclose) instead of silently reading a graph whose shape it no longer understands.

## Architectural context
**Builds on:**
- `graph/schema.cypher:22-24` — the `:Meta {id:"schema"}` node already stamps a semver **string** `schema_version` ("0.2.0"). This epic adds an **integer** `schema_format` alongside it.
- `api/app.py` `_graph_stats()` (around `:294-346`) already reads `m.schema_version AS sv` through a scoped session and surfaces it on `/health.graph.schema_version` and `/status.corpus.schema_version` (`GraphStats`, `api/schemas.py:188-204`; `HealthResponse`, `:256-261`; `StatusResponse`, `:264-279`).
- `api/app.py` warm-up path `_warm_plan_path()` (`:104-133`) + `_warmup_loop()` (`:136-152`) already implement **degrade-and-disclose**: a failing startup dependency raises inside the warm round, `/health` returns 503 with the disclosed cause in `detail` (`:399-410`), and the process keeps running / recovers without a redeploy. This epic reuses that exact path to "refuse".

**Enables:**
- Safe forward migration: when the graph shape changes incompatibly, `schema.cypher` bumps `schema_format`; any still-running old API deployment self-reports incompatible on `/health` rather than serving mis-shaped reads.
- The foundation for the deferred B2 composite build-ID / manifest-vintage work (OUT of scope here).

**Does NOT include (scope fence — do NOT build these):**
- **NO** touching, renaming, or repurposing `ingest_version`. See the BINDING CORRECTION below — `ingest_version` is the region-scoped **prune anchor** and must stay byte-for-byte as it is.
- **NO** composite `{region}-{osm_date}-{usfs_vintage}-{dem_sha}-{code_sha}` build-ID, and **NO** manifest vintage population. That is deferred to B2 (operator-discipline plumbing whose UX only pays off once F1 lands). Keep this chunk to `schema_format` + the startup validation only.
- **NO** `/plan`-path gating logic beyond what the existing warm-up readiness gate already provides. Do not add schema checks inside the per-request `/plan` handler.
- **NO** changes to the semver `schema_version` string's value or meaning; the two coexist.

---

## BINDING VERIFIER CORRECTIONS (from the borrow plan — embedded because the builder cannot read the plan)

**(A4.1) Do NOT touch or replace `ingest_version`.** `ingest_version` is the **region-scoped PRUNE ANCHOR**. In `graph/load.py` the stale-trail prune keys off it:
- `graph/load.py:315` — `_REGION_PRED = "(node.ingest_version = $region_id OR node.ingest_version STARTS WITH $prefix)"` where `$prefix = f"{region_id}-"`.
- `graph/load.py:320` — `_REGION_VERSION_PRED = f"{_REGION_PRED}\n  AND node.ingest_version <> $iv"`.

The `{region_id}-` separator anchor is load-bearing (a bare `STARTS WITH region_id` would let region `"shen"` prune region `"shenandoah-gwj"` — a silent cross-region wipe). **Add `schema_format` as a SEPARATE property on the `:Meta` node, keep every `ingest_version` occurrence and the `{region_id}-` prefix intact, and produce ZERO diff to `graph/load.py`.** `schema_format` lives on `:Meta`; `ingest_version` lives on data nodes (`:Area` / `:CanonicalTrail` / `:SourceRecord` / `:Segment` / `:Trailhead`). They are unrelated and must not be conflated.

**(A4.4) The startup `schema_format` check must DEGRADE-AND-DISCLOSE on `/health`, NEVER crash the process.** Fail-loud at the boundary is **not** the same as crashing the server. The incompatibility must surface as a disclosed `/health` 503 (the existing warm-up disclose path) — never a `sys.exit`, `os._exit`, or an unhandled exception that kills the uvicorn worker. A graph the API cannot *read* (unreachable / blip), and a graph missing `schema_format` entirely (a legacy graph applied before this epic), must NOT trigger the refusal — those degrade-and-disclose but keep serving (source-or-silence: refuse only on a *confirmed* newer stamp).

---

## Semantics (the contract the ACs pin)

`schema_format` is an **opaque monotonic integer**, independent of the semver `schema_version` string. Initial value for the current graph shape: **`1`**. It is incremented (to `2`, `3`, …) only on a **breaking** change to the graph shape that an older API could mis-read. The API declares the single format it understands as a module constant `EXPECTED_SCHEMA_FORMAT`.

Comparison at startup, given `graph_format` (read from `:Meta.schema_format`) and `EXPECTED_SCHEMA_FORMAT`:

| Case | Meaning | Behavior |
|---|---|---|
| `graph_format == EXPECTED` | compatible | serve normally (200) |
| `graph_format < EXPECTED` | graph older than code (normal deploy order: code first, migrate later) | serve normally (200); tolerated |
| `graph_format > EXPECTED` | **graph NEWER than this API understands** | **REFUSE**: warm round fails, `/health` 503 with both numbers disclosed |
| `schema_format` absent / null | legacy graph (pre-this-epic) or property unset | serve normally (200); disclose `schema_format: null`; do NOT refuse |
| graph unreachable / read errored | can't confirm anything | existing degrade path; do NOT refuse on the *schema* dimension |

---

## Stories

### S1 — Integer `schema_format` stamped on the `:Meta` node

**Given** `graph/schema.cypher` seeds a `:Meta {id:"schema"}` node with a semver string `schema_version`,
**When** the schema is applied (fresh `ON CREATE` or re-applied `ON MATCH`),
**Then** the `:Meta` node also carries an **integer** `schema_format` property, and no data-node `ingest_version` or region-prune logic is altered.

**AC-1.1:** `graph/schema.cypher` sets `m.schema_format = 1` (an **integer literal**, not a string, not `"1"`) on the `MERGE (m:Meta {id:"schema"})` node (currently `:22-24`), in **both** the `ON CREATE SET` and `ON MATCH SET` branches, so re-applying an already-created graph populates the property.
**AC-1.2:** `schema_format` is a **distinct** property from `schema_version`; the existing `schema_version` semver string assignment ("0.1.0" on create / "0.2.0" on match) is unchanged in value and both properties coexist on the node.
**AC-1.3:** `git diff` touches **no line of `graph/load.py`**; every `ingest_version` occurrence and the `_REGION_PRED` / `_REGION_VERSION_PRED` predicates (`:315`, `:320`) and the `{region_id}-` prefix are byte-for-byte unchanged. The existing prune tests (`tests/test_load.py`, `tests/test_load_neo4j.py`) still pass unmodified.
**AC-1.4:** A DB-free test asserts `schema.cypher` contains an integer `schema_format` assignment on `:Meta` and that the file still parses via `apply_schema.split_statements` into ≥30 executable statements (reuse the pattern in `tests/test_apply_schema.py:58-65` — `split_statements` is imported from `scripts/apply_schema.py`, which is where the static integer-literal check belongs). A `@pytest.mark.neo4j` test asserts the integer round-trips on `:Meta`: seed `:Meta` via `scoped_session` in the manual-seed style of `tests/test_graph_stats_neo4j.py::test_graph_stats_counts_via_count_subquery` (there is no established in-test full-schema-apply helper — `test_apply_schema` only *splits*, and `test_graph_stats_neo4j` seeds `:Meta` by hand), then read `MATCH (m:Meta {id:"schema"}) RETURN m.schema_format` and assert it equals the integer `1` (Python type `int`, not `"1"`). Only drive a full-file apply (via `scripts/apply_schema`) instead if it is trivial in-test; the static split test already proves the integer literal is in the file, so seed-and-read is sufficient for the value assertion.

### S2 — API declares and surfaces the graph's `schema_format`

**Given** the API reads `:Meta` stats on `/health` and `/status`,
**When** it queries the graph,
**Then** it also reports the graph's `schema_format`, and declares the single format it itself understands.

**AC-2.1:** `api/app.py` defines a module-level constant `EXPECTED_SCHEMA_FORMAT: int = 1`, with a comment naming `graph/schema.cypher`'s `Meta.schema_format` and the bump contract (bump both together only when the graph shape breaks backward compatibility).
**AC-2.2:** The `_graph_stats()` Cypher additionally returns `m.schema_format AS sf`; `GraphStats` (`api/schemas.py:188-204`) gains `schema_format: int | None = None`, populated from that read. It is surfaced on `/health` as `.graph.schema_format` and on `/status` as `.corpus.schema_format`.
**AC-2.3:** When `:Meta.schema_format` is **absent** (legacy graph), the read yields `None` and `GraphStats.schema_format` is `None` — no exception, `/health` still returns its normal 200 shape. When the graph is unreachable, `_graph_stats()` still degrades to `graph=null` exactly as today (Rule #1).

### S3 — Startup compatibility gate: refuse a newer-schema graph via degrade-and-disclose

**Given** the warm-up path already gates `/health` readiness and discloses a failing dependency,
**When** the graph's `schema_format` is confirmed **greater** than `EXPECTED_SCHEMA_FORMAT`,
**Then** the warm round fails with a disclosed cause, `/health` returns 503 naming both numbers, and the process never crashes.

**AC-3.1:** The warm-up path (`_warm_plan_path`, `api/app.py:104-133`) reads `:Meta.schema_format` (via a scoped session, same shape as `_graph_stats`) and, when the read returns an integer **strictly greater** than `EXPECTED_SCHEMA_FORMAT`, raises a distinct, clearly-named exception (e.g. `SchemaFormatError`) so the existing `_warmup_loop` records it into `state.error` and `/health` returns 503 with that message in `detail` (`:405-410`).
**AC-3.2:** The refusal fires **only** on a confirmed `graph_format > EXPECTED`. All of: `graph_format == EXPECTED`, `graph_format < EXPECTED`, `schema_format` absent/`None`, and a graph read that raises/blips → warm-up proceeds (no refusal) and, when the rest of the stack is healthy, `/health` serves 200. A read error on the schema probe is swallowed-and-logged (degrade), never converted into the refusal.
**AC-3.3:** The incompatibility path **never crashes the process**: no `sys.exit` / `os._exit` / unhandled raise escaping the warm-up thread. After an incompatible read, the app still answers other routes (assert `/status` still responds and `/health` returns a disclosed 503, not a dropped connection).
**AC-3.4:** The disclosed 503 `detail` string includes **both** the graph's `schema_format` value and the API's `EXPECTED_SCHEMA_FORMAT` value, so an operator can see which side is behind (e.g. `"graph schema_format 2 is newer than this API supports (1); deploy the matching API version"`).

---

## Test plan (mirror existing layout)
- **DB-free** (`pytest -m "not neo4j"`, the default `make test` leg):
  - `tests/test_apply_schema.py` — extend or add a sibling assertion for AC-1.4's static check (integer `schema_format` present + file still splits).
  - `tests/test_api_warmup.py` — add hermetic cases for S3 mirroring its `_WarmGraph` / `_StubSession` / `_install_free_stack` doubles: a stub `scoped_session().run(...)` returning `schema_format = EXPECTED+1` → warm round raises `SchemaFormatError`, `state.error` names both numbers, `/health` is 503 disclosing both; `= EXPECTED` and `= None` → warm round proceeds; a raising `run` → proceeds (no refusal). Add AC-2.3's `schema_format=None` path here or in `tests/test_api_endpoints.py`.
- **DB-backed** (`@pytest.mark.neo4j`, the `integration (neo4j)` CI leg):
  - `tests/test_graph_stats_neo4j.py` — extend `test_graph_stats_counts_via_count_subquery` (or add a sibling) to seed `m.schema_format` and assert `stats.schema_format == 1` (AC-1.4 read side + AC-2.2). Reuse the `clean_graph` fixture.
  - A `@pytest.mark.neo4j` test that seeds `Meta.schema_format = EXPECTED+1` and drives the real `_warm_plan_path` (or the schema-probe helper) to assert it refuses.

## Definition of Done
- [ ] All ACs covered by at least one passing test
- [ ] `make check` green (`ruff format --check` + `ruff` + `mypy` + `pytest -m "not neo4j"`)
- [ ] `@pytest.mark.neo4j` tests pass against a local `make db-up` graph (loopback bolt only)
- [ ] Targeted self-review agent run over the diff; every CRITICAL fixed
- [ ] Merge-sensitive seams (`api/app.py`, `graph/schema.cypher`) called out explicitly in the PR body
- [ ] Epic file copied into `docs/epics/` and a row added to `docs/epics/README.md` (status `IN_PROGRESS` → `REVIEW` when the PR opens)
- [ ] Committed and pushed on `claude/schema-format`; PR opened into `main`
