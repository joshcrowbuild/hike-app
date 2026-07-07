# Epic 035 — OSM on-trail water-source overlay (ingest + persist + read)

**Status:** REVIEW
**Phase:** 1 (personal-intelligence app; additive corpus enrichment)
**Spec refs:** `docs/research/discovery.md` item **#3** (OSM water sources — BUILD-NOW) ·
CLAUDE.md **Rule #1** (source-or-silence) · **Rule #3** (graph holds slow/structural only) ·
**Rule #4** (access control at the query layer) · **Rule #6** (enrichment degrades-and-discloses)

> Line numbers below were read on **2026-07-07** and **may drift** — always re-grep the named
> symbol before editing, never trust a bare line number.

---

## Capability statement
The corpus gains an **on-trail water overlay**: `amenity=drinking_water` / `natural=spring` /
`man_made=water_well` / `man_made=water_tap` POIs are fetched from OSM (the pipe we already
run), persisted as world-public `:WaterSource` nodes, and readable by proximity to a point —
so a later Detail-card follow-on can show "spring 400 m off the trail" **without** ever making
a potability ("safe to drink") claim. A top backpacking need we entirely miss today.

## Architectural context

**Builds on:**
- `ingestion/fetch/osm.py` — the Overpass transport with mirror failover
  (`_OVERPASS_MIRRORS`, `osm.py:26-30`) and the trail `fetch()` whose query is at
  **`osm.py:44-49`** (`way["highway"~"path|footway|track|bridleway|steps"]["name"]` — trail
  ways ONLY; no POIs, no water).
- `ingestion/fetch/trailheads.py` — the **exact precedent** for this epic: a sibling
  Overpass **node** fetch that imports `_OVERPASS_MIRRORS` from `osm.py`, runs its own
  `node[...]` union query, returns a frozen `TrailheadFeature` dataclass, fails over across
  mirrors, and returns `[]` on all-mirror failure (`trailheads.py:19-78`). Water is the same
  shape with different tags.
- `graph/load.py` `load_trailhead` (`load.py:754-802`) — the precedent **world/public**
  node loader: an idempotent `MERGE (h:Trailhead {trailhead_id: $id}) SET …point…` with
  `ingest_version` defaulting to `_today()` (`load.py:846`). No `owner_id` — world nodes are
  unowned and need no scope clause (module docstring, `load.py:1-14`).
- `graph/queries.py` `candidate_trails_near` (`queries.py:66-94`) / `candidate_trails_near_direct`
  (`queries.py:97-122`) — the precedent **world-node read builder**: a pure
  `(cypher, params)` function using `point.distance(node.point, point($origin)) <= $radius_m`
  and `ORDER BY distance_m ASC LIMIT …`. World nodes only → **inherently public, no owner
  scope** (contrast the owned-read builders below `queries.py:202`, which carry
  `owner_scope(var)`).

**Enables:** a scoped Detail-card water follow-on (surface the overlay per-trail with an
honest "seasonal / filter-required / unverified" disclosure) and a future
`pipeline.py`/standalone-script wiring that ingests water per region. **Neither is in this
epic** (see Does-NOT-include).

**Does NOT include:**
- **No `api/app.py`, no response schema, no frontend.** Deliberately kept off the shared
  `api/app.py` seam (D2's file) — the Detail-card surface is a scoped follow-on. This epic
  ships **three primitives + tests only**: fetch → store → read.
- **No `ingestion/pipeline.py` edit and no standalone ingest runner.** The pipeline is an
  AGENTS.md merge-sensitive seam and is shared by several concurrent wave-1 lanes; this lane
  stays **disjoint** from it. Like Epic 026's classified tags ("persisted for a later phase;
  nothing reads them yet"), the loader + reader exist and are unit-tested; wiring them into a
  live per-region ingest is the follow-on. (Nothing calls `load_water_source` in the shipped
  pipeline yet — that is intentional and must be disclosed in the PR body.)
- **No potability / "safe to drink" claim, in any layer** (Rule #1 — the binding guard below).
- **No `NEAR`/`HAS_WATER` persisted edge to trails.** Trail association is done at **read
  time** by proximity (`water_sources_near`), not by a persisted edge — so no spatial join is
  needed inside `load` and no pipeline wiring is required this sprint.
- **No `graph/schema.cypher` edit.** A `:WaterSource` uniqueness constraint + point index
  belong in the wiring follow-on (schema.cypher is a shared merge-sensitive file; keep this
  lane's files disjoint). `MERGE` on `water_id` is idempotent **without** a constraint, and
  `point.distance` works **without** an index (a full scan of a small overlay); both are
  correct today, just unindexed — the `:WaterSource` constraint/index is the wiring follow-on
  (see Does-NOT-include, above).

### Binding decisions & guards (authoritative — the builder cannot read the research brief)

1. **Sibling fetch function, NOT a change to the trail `fetch()`.** The scope names
   "extend the Overpass query at `osm.py:46`", but that query lives inside `fetch()`, which
   returns trail `Feature`s backed by Shapely **LineStrings** (`osm.py:70-71` drops anything
   with `< 2` coords). A water POI is a **single node** (1 coord) — it cannot be a LineString
   Feature. Therefore add a **new sibling function `fetch_water(bbox, *, client, timeout)` in
   the same file `ingestion/fetch/osm.py`**, mirroring `trailheads.py` exactly (own `node[...]`
   union query, own frozen dataclass, `_OVERPASS_MIRRORS` failover, `[]` on failure). This
   literally extends the OSM-fetch path the scope names while leaving the geometry-spine
   `fetch()` (merge-sensitive, central) untouched — a safety win. State this decision in the
   PR body.
2. **Rule #1 — never a potability claim, positive OR negative.** Surface **location + water
   type + seasonality only**. Do **not** map OSM's `drinking_water=yes/no/conditional` tag to
   any boolean "potable/safe/drinkable" field — capturing it invites a downstream dev to
   render "safe to drink". It is **deliberately omitted** this sprint (a "do not drink" is also
   an unverifiable claim). The no-potability substring guard is scoped to **three surfaces
   only**: (a) the `load_water_source` Cypher template, (b) the `water_sources_near` Cypher
   template, and (c) the `WaterSource` dataclass field names — none may contain
   `potable` / `drinkable` / `safe` / `drink`. **Exemption:** `drinking_water` is the legitimate
   OSM POI *category* — the `amenity=drinking_water` tag in `fetch_water`'s query and the
   `water_type="drinking_water"` classification value — NOT a potability claim; it appears
   (correctly) in the fetch query, the `water_type` param *value*, and test fixtures, all of
   which are **outside** the guard's scope (a param value lands in `$params`, never in the
   Cypher *string*). A test asserts absence across the dataclass field **names** **and** the two
   emitted Cypher strings — it must **not** scan fixtures or the fetch-query source (that would
   falsely trip on the required `drinking_water` literal).
3. **Rule #3 — a WaterSource is slow/structural, correctly persisted.** A spring/tap/well is a
   static POI (it does not move or expire like weather/streamflow/AQI). Persisting it as a node
   is on the **right** side of Rule #3 — it is NOT the fast/ephemeral JIT-overlay class. Note
   this in the module docstring so the distinction is explicit.
4. **Rule #4 / Rule #6 — world-public read, degrade-and-disclose.** `:WaterSource` carries no
   `owner_id` (world/public, like `:Trailhead`), so `water_sources_near` is a plain world read
   with **no** owner-scope clause — exactly like `candidate_trails_near`. On any fetch failure
   `fetch_water` returns `[]` (never fabricates); absence of water is silence, never an error.
5. **Deterministic water-type mapping.** A node may carry more than one matching tag. Classify
   `water_type` by a fixed priority: `amenity=drinking_water` → `"drinking_water"`, else
   `natural=spring` → `"spring"`, else `man_made=water_well` → `"water_well"`, else
   `man_made=water_tap` → `"water_tap"`. Document the order; a test pins it.

### License & attribution
- **OSM data is ODbL** — we already comply (same class as the trail geometry we ingest).
  Any user-facing water surface (the follow-on Detail card, out of scope here) must carry the
  **"© OpenStreetMap"** attribution. Set `WaterSource.source = "OSM"` and persist it as
  `w.source = "OSM"` so the attribution provenance travels with the node from day one.
- **No source code is ported** in this epic (it rides our own existing Overpass transport), so
  no file header attribution is required. The dependency is OSM **data**, not third-party code.

---

## Stories

### S1 — Fetch OSM water POIs (sibling `fetch_water` in `ingestion/fetch/osm.py`)

**Given** `ingestion/fetch/osm.py` fetches trail **ways** only (`osm.py:44-49`) and
`trailheads.py` proves the sibling-node-fetch pattern,
**When** a caller passes a region bbox,
**Then** it gets back a list of `WaterSource` records for the four water POI tags in the bbox.

**AC-1.1:** A new frozen dataclass `WaterSource` is declared in `ingestion/fetch/osm.py` with
fields: `osm_id: str`, `water_type: str`, `name: str | None`, `lat: float`, `lon: float`,
`seasonal: str | None` (the raw OSM `seasonal` tag value, or `None`). `@dataclass(frozen=True)`.
**No** field named or aliasing `potable`/`drinkable`/`safe` exists (Guard 2). A test asserts
the exact field set (e.g. via `dataclasses.fields`).
**AC-1.2:** `fetch_water(bbox, *, client=None, timeout=60.0) -> list[WaterSource]` issues one
Overpass `node` union query over the four tags — `amenity=drinking_water`, `natural=spring`,
`man_made=water_well`, `man_made=water_tap` — clipped to `bbox` (south, west, north, east),
using `_OVERPASS_MIRRORS` failover (mirror the exact loop shape of `trailheads.py:51-63`).
**AC-1.3:** `water_type` is classified by the fixed priority in Guard 5. A node tagged both
`natural=spring` and `man_made=water_well` classifies as `"spring"` (spring wins). A test pins
the priority with a multi-tag node.
**AC-1.4:** `osm_id` is `f"node/{el['id']}"` (mirror `trailheads.py:70` **exactly** — this pins
the idempotency-key format so the `water:osm:{osm_id}` caller contract in AC-2.4 is stable
across re-ingests). `name` is `tags.get("name")` (fall back to `tags.get("official_name")` like
`trailheads.py:71`), or `None`; `seasonal` is `tags.get("seasonal")` or `None`. `lat`/`lon`
come from the node's own `el["lat"]`/`el["lon"]` (nodes, not ways — no `geometry` array). A
test covers a named node, an unnamed node (`name is None`), and a `seasonal=yes` node.
**AC-1.5:** On all-mirror failure (non-200 / exception on every mirror) `fetch_water` returns
`[]` and logs a warning — never raises, never fabricates (Rule #6). A test drives a
`MockTransport` returning `500` and asserts `[]`.
**AC-1.6:** A node carrying **none** of the four tags (should not occur given the query, but
guard defensively) is skipped rather than crashing; a node missing `lat`/`lon` is skipped. A
test includes a tagless / coord-less element and asserts it is dropped, not raised on.

### S2 — Persist the overlay (`load_water_source` in `graph/load.py`)

**Given** `graph/load.py` upserts world/public nodes idempotently (the `load_trailhead`
precedent, `load.py:754-802`),
**When** a `WaterSource` is loaded,
**Then** an idempotent world-public `:WaterSource` node exists with its location, type,
seasonality, source, and ingest version — and **no** potability property.

**AC-2.1:** `load_water_source(runner, water_id, *, water_type, lat, lon, name=None,
seasonal=None, source="OSM", ingest_version=None) -> None` emits **one** `MERGE (w:WaterSource
{water_id: $water_id}) SET …` via the injected `Runner` (same signature discipline as every
`load_*` in the file). `ingest_version` defaults to `_today()` (`load.py:846`).
**AC-2.2:** The SET clause writes `w.water_type`, `w.point = point({latitude:$lat,
longitude:$lon})`, `w.source`, `w.ingest_version`, and — only when non-`None` — `w.name` and
`w.seasonal` (mirror `load_trailhead`'s optional-clause style, `load.py:773-780`). A test with a
list-appender runner asserts the emitted Cypher `MERGE`s on `WaterSource` + `water_id` and the
params carry `water_type`/`lat`/`lon`.
**AC-2.3:** The node is **world/public**: no `owner_id`, no scope clause (it goes through the
plain world-layer `runner`, never `ScopedSession.run_write`). The emitted Cypher contains
neither `owner_id` nor `$viewer_id`. A test asserts their absence.
**AC-2.4:** Idempotency — calling `load_water_source` twice with the same `water_id` emits a
`MERGE` (not `CREATE`) both times, so a monthly re-run rewrites in place. The `water_id` caller
contract is `"water:osm:{osm_id}"`; with `osm_id` pinned to `f"node/{el['id']}"` (AC-1.4) this
is `"water:osm:node/{id}"` — stable across runs. A test constructs one from a fetched
`WaterSource` and asserts the **exact** MERGE key string, so a future pipeline-wiring follow-on
cannot silently change the key format and orphan prior nodes.
**AC-2.5 (Rule #1 guard):** The emitted Cypher contains **none** of `potable`, `drinkable`,
`safe`, `drink` (case-insensitive substring). A test asserts this over the generated Cypher
string.

### S3 — Read the overlay by proximity (`water_sources_near` in `graph/queries.py`)

**Given** `graph/queries.py` is the single sanctioned author of graph Cypher, with world reads
carrying **no** owner scope (`candidate_trails_near`, `queries.py:66-94`),
**When** a caller wants water near a point,
**Then** a pure `(cypher, params)` builder returns nearby `:WaterSource` nodes, nearest first.

**AC-3.1:** `water_sources_near(lat, lon, radius_m, *, limit=50) -> tuple[str, dict[str, Any]]`
is a **pure function** (no driver, no I/O) returning `(cypher, params)`, unit-testable without a
database — matching every builder in the module.
**AC-3.2:** The Cypher matches `(w:WaterSource)` where
`point.distance(w.point, point($origin)) <= $radius_m`, returns `water_id`, `water_type`,
`name`, `point`, `seasonal`, `source`, and `distance_m`, `ORDER BY distance_m ASC LIMIT $limit`
(mirror `candidate_trails_near_direct`, `queries.py:102-116`). `params` carries
`origin = {"latitude": lat, "longitude": lon}`, `radius_m`, `limit`.
**AC-3.3 (Rule #4):** World-public read — the builder emits **no** `owner_scope`/`$viewer_id`
clause (a `:WaterSource` is unowned, like `:Trailhead`). A test asserts `$viewer_id` and
`owner_id` are absent from the emitted Cypher, and that a docstring states "World nodes only →
inherently public, no owner scope" (matching the module's world-read convention).
**AC-3.4 (Rule #1 guard):** The emitted Cypher contains none of `potable`/`drinkable`/`safe`/
`drink`. A test asserts it.

---

## Definition of Done
- [ ] All ACs covered by at least one passing test in **`tests/test_osm_water.py`** (network-free:
      `httpx.MockTransport` for `fetch_water` — mirror `tests/test_fetch.py:20-22`'s `_osm_response`
      helper; list-appender `Runner` for `load_water_source` — mirror `tests/test_load.py`; pure-function
      assertions for `water_sources_near`). **No `@pytest.mark.neo4j`** needed — every assertion is on the
      emitted Cypher / returned dataclasses.
- [ ] The **Rule #1 no-potability guard** is a real test: assert `potable`/`drinkable`/`safe`/`drink` appear
      in **none** of the `WaterSource` field names, the `load_water_source` Cypher, or the `water_sources_near`
      Cypher.
- [ ] `make check` green (`ruff format --check` + ruff + mypy + `pytest -m "not neo4j"`); no field is `Any`-typed.
- [ ] **Inertness disclosed in the PR body:** nothing in the shipped pipeline calls `load_water_source` yet —
      the three primitives are additive and unit-tested; live per-region ingest + the Detail-card surface + a
      `:WaterSource` schema constraint/index are the follow-on (Does-NOT-include). State this so "on-trail water
      overlay" is not read as already-live.
- [ ] **Attribution disclosed:** `source="OSM"` persisted on every node; the follow-on user surface owes a
      "© OpenStreetMap" (ODbL) credit. No source code ported → no file-header attribution required.
- [ ] Targeted self-review agent run over the diff; every CRITICAL fixed, MODERATE+ documented.
- [ ] Committed and pushed on `claude/osm-water-overlay`; PR opened into `main`; epic copied into
      `docs/epics/` and a row added to `docs/epics/README.md` (status `REVIEW`); `scripts/gen_epic_index.py`
      re-run to sync status cells.
