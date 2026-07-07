# Epic 026 — Classify OSM sac_scale/surface/access tags at ingest into path_grade/psurface/foot_access

**Status:** DONE ✅
**Phase:** 1 (corpus ingestion — Stage 3 pipeline)
**Spec refs:** CoMaps borrow plan §A1 (wave 2) · CoMaps `generator/osm2type.cpp` (DeterminePathGrade + DetermineSurfaceAndHighwayType) · Decision Log §27 (OSM = geometry spine) · CLAUDE.md Rule #1 (source-or-silence)

> Line numbers in this doc were read on 2026-07-06 and **may drift** — re-grep the named
> symbols (`is_trail_worthy`, `Feature`, `load_canonical_trail`, `_load_matches`,
> `consolidate_osm_segments`) if an anchor no longer matches.

---

## Capability statement
The ingest pipeline classifies each OSM way's `sac_scale`/`trail_visibility`,
`surface`/`smoothness`/`tracktype`, and `foot`/`access` tags into three normalized,
source-or-silence properties — `path_grade`, `psurface`, `foot_access` — carried through
conflation/consolidation and persisted on every `CanonicalTrail`, so a later phase can
surface trail difficulty, tread quality, and foot-access without a re-fetch.

## Architectural context
**Builds on:**
- Epic 023 (length/gain at ingest) — this epic extends the SAME `Feature` dataclass
  (`ingestion/conflate/match.py`) and the SAME `load_canonical_trail` loader
  (`graph/load.py`) that 023 adds length/gain to. **This PR must merge AFTER Epic 023**
  to avoid a three-way collision on those two files.
- The existing `way_type` plumbing (fetch → `Feature.way_type` → consolidation-dominant →
  `load_canonical_trail(way_type=…)` → `CanonicalTrail.way_type`) is the exact template
  this epic copies for three more fields.
- CoMaps `generator/osm2type.cpp` `DeterminePathGrade` (line ~822) and
  `DetermineSurfaceAndHighwayType` (line ~601) as the algorithm reference (read-only C++).

**Enables:**
- Phase-D D1 (difficulty/surface badge on Detail, Curator screen) — **gated separately**
  on the unresolved A1.5 effort-vs-technical taxonomy collision. Not this epic.

**Does NOT include (scope fence — all consumer wiring is OUT):**
- **No Curator use** of the three new fields (no screen, no filter, no de-rank). Explicitly
  do **NOT** wire `foot_access` into the `orchestration/curator.py:219-295` roadlike
  name-regex demotion — see binding correction A1.4 below.
- **No Detail badge / no API field / no frontend.** This chunk is **ingest + persist ONLY**.
  A `CanonicalTrail` gains three properties nobody reads yet; that is intended.
- **No `DetermineSurfaceAndHighwayType` highway-type rewrite.** Port ONLY the surface
  classifier's tail + word-lists, NOT its path/footway/cycleway conversion block
  (`osm2type.cpp` ~683–766). See binding correction A1.2.
- **No schema.cypher change.** `CanonicalTrail` is schemaless-property (the loader SETs
  arbitrary props); no index/constraint is added for these three.

---

## Binding verifier corrections (from the borrow plan — embedded because the builder cannot read the plan)

- **A1.1 (load-bearing):** `DeterminePathGrade` returns ONLY one of `{"difficult", "expert", ""}`.
  **There is NO `"normal"`.** Empty-on-absent is **REQUIRED**: a way with no `sac_scale`
  and no `trail_visibility` (and/or `highway != "path"`) MUST return `""`. A missing tag
  must **NEVER** render as `"Easy"` or any positive grade downstream — Rule #1
  (source-or-silence) holds ONLY with empty-on-absent. This same empty-on-absent posture
  applies to `psurface` and `foot_access`: absent/unrecognized → `""`, never a fabricated
  default.
- **A1.2:** Port ONLY the surface classifier **tail + word-lists**, NOT
  `DetermineSurfaceAndHighwayType`'s highway-type rewrite. The C++ function does two jobs:
  (1) rewrites `highway=path/footway/cycleway` based on surface/smoothness (lines ~683–766)
  and (2) derives a `paved_good|paved_bad|unpaved_good|unpaved_bad|""` string
  (lines ~767–820). Port ONLY (2) plus its word-lists (~624–658) and the compound-value
  `Has` tokenizer (~663–673). Do NOT change any `highway` value — our `way_type` is fixed
  upstream and must not be rewritten here.
- **A1.4:** Do **NOT** retire the `orchestration/curator.py:219-295` roadlike name-regex
  with `foot_access`. That demotion keys on the trail **NAME** precisely because access
  tags are absent for the `track`s it targets — `foot_access` would be `""` for BOTH a
  fire road (keep) and an access road (demote), so it cannot replace the name signal.
  Leave curator.py untouched.

---

## Stories

### S1 — Stop discarding classification tags at OSM fetch

**Given** `ingestion/fetch/osm.py` reads `tags = el.get("tags", {})` (line ~72) and
already has every OSM tag in hand, but constructs `Feature(…)` (lines ~79–91) using only
`name`/`geom`/`source`/`ref`/`way_type` — dropping `sac_scale`, `trail_visibility`,
`surface`, `smoothness`, `tracktype`, `foot`, `access`
**When** the fetch builds each `Feature`
**Then** it calls the new `ingestion/classify.py` classifiers on `tags` and passes the
three results into `Feature(path_grade=…, psurface=…, foot_access=…)`.

- **AC-1.1:** `ingestion/fetch/osm.py` passes the way's full `tags` dict to
  `classify_path_grade`, `classify_surface`, and `classify_foot_access`, and threads the
  three return values into the `Feature(…)` constructor. No tag beyond those the
  classifiers consume needs to be retained on `Feature`.
- **AC-1.2:** A fetched way carrying `sac_scale=alpine_hiking` (with `highway=path`)
  produces a `Feature` with `path_grade == "expert"`; a way with `highway=path` +
  `surface=asphalt` produces `psurface == "paved_good"` (the `highway` tag is REQUIRED —
  the ported surface guard returns `""` when `highway` is empty, see AC-2.2); a way with
  `foot=no` produces `foot_access == "no"`. (Test via a stubbed Overpass JSON response
  through `fetch`, or
  via a direct unit test on the classifiers if wiring `fetch` end-to-end is heavy — at
  least one test must exercise the osm.py wiring, not only the classifiers in isolation.)
- **AC-1.3:** A fetched way with NONE of the classification tags produces a `Feature`
  with `path_grade == ""`, `psurface == ""`, `foot_access == ""` (empty-on-absent; no
  fabricated default).

### S2 — New `ingestion/classify.py` module (port CoMaps classifiers)

**Given** no classification module exists (`ingestion/classify.py` is new)
**When** the module is created
**Then** it exposes three pure, side-effect-free functions over a `tags: Mapping[str, str]`
input, each returning a normalized string (empty-on-absent).

- **AC-2.1 — `classify_path_grade(tags) -> str`** ports `DeterminePathGrade`
  (`osm2type.cpp` ~822):
  - Returns `""` unless `tags.get("highway") == "path"`. (A non-`path` way — `footway`,
    `track`, `bridleway`, `steps` — has NO path grade.)
  - Returns `""` when both `sac_scale` and `trail_visibility` are absent/empty.
  - Returns `"expert"` when `sac_scale ∈ {alpine_hiking, demanding_alpine_hiking,
    difficult_alpine_hiking}` OR `trail_visibility ∈ {horrible, no, very_bad}`.
  - Returns `"difficult"` when `sac_scale == demanding_mountain_hiking` OR
    `trail_visibility ∈ {bad, poor}`.
  - Returns `""` for every other value (`hiking`, `mountain_hiking`, `excellent`, `good`,
    `intermediate`, `unknown`, unrecognized). **Never returns `"normal"` or any positive
    grade.** (Binding correction A1.1.)
- **AC-2.2 — `classify_surface(tags) -> str`** ports the TAIL of
  `DetermineSurfaceAndHighwayType` (`osm2type.cpp` ~767–820) + its word-lists (~624–658)
  + the compound-value `Has` tokenizer (~663–673), and NOTHING of the highway-rewrite
  block (~683–766) (binding correction A1.2):
  - Reads `surface`, `smoothness`, `surface:grade` (float, default 2), `tracktype`,
    `highway`, `4wd_only`.
  - `4wd_only ∈ {yes, recommended}` → `"unpaved_bad"`.
  - Returns `""` when `highway` is empty OR both `surface` and `smoothness` are empty.
  - Otherwise derives `isPaved`/`isGood` per the C++ tail and returns exactly one of
    `{"paved_good", "paved_bad", "unpaved_good", "unpaved_bad"}`.
  - `Has(list, value)` matches compound values (`concrete:plates`, `sand/dirt`,
    `gravel;grass`) by tokenizing on `;:/` and matching if ANY part is in the list.
  - **Word-lists — ported VERBATIM from `osm2type.cpp:624-661` (embedded here so the port
    does not depend on the out-of-repo tmp clone being readable):**
    - `pavedSurfaces = {asphalt, cobblestone, chipseal, concrete, grass_paver, stone,
      metal, paved, paving_stones, sett, brick, bricks, unhewn_cobblestone, wood}`
    - `badSurfaces = {cobblestone, dirt, earth, soil, grass, gravel, ground, metal, mud,
      rock, stone, unpaved, pebblestone, sand, sett, brick, bricks, snow, stepping_stones,
      unhewn_cobblestone, grass_paver, wood, woodchips}`
    - `veryBadSurfaces = {dirt, earth, soil, grass, ground, mud, rock, sand, snow,
      stepping_stones, woodchips}`
    - `veryBadSmoothness = {very_bad, horrible, very_horrible, impassable, robust_wheels,
      high_clearance, off_road_wheels, rough}`
    - `midSmoothness = {unknown, intermediate}`
    - `goodPathSmoothness` is part of the SKIPPED rewrite block and is NOT needed here.
  - Test-anchored parity cases (each an AC-verifiable row). **The `highway` tag is
    load-bearing: the ported tail's first guard is `if highway=="" or (surface=="" and
    smoothness==""): return ""` (`osm2type.cpp:772`), so any row without a `highway` tag
    returns `""`.** Every row below that expects a non-empty result carries a `highway`:
    - `{highway:path, surface:asphalt}` → `paved_good`
    - `{highway:path, surface:ground, surface:grade:1}` (very-bad surface, grade<2) →
      `unpaved_bad`
    - `{highway:path, surface:compacted}` alone → `unpaved_good`
    - `{highway:path, smoothness:impassable}` (no surface) → `unpaved_bad`
    - `{highway:path, surface:concrete:plates}` (compound, `concrete` ∈ pavedSurfaces) →
      `paved_good`
    - `{highway:track, smoothness:bad}` (no surface) → `unpaved_bad`
    - `{4wd_only:yes}` → `unpaved_bad` (early-return at C++ line 620-621, BEFORE the
      highway guard — so this row legitimately needs no `highway`)
    - `{surface:asphalt}` with NO `highway` → `""` (locks in the guard — a surface with no
      highway is silent, not `paved_good`)
    - no `surface` AND no `smoothness` (e.g. `{highway:path}`) → `""` (the guard's second
      arm)
- **AC-2.3 — `classify_foot_access(tags) -> str`** derives a normalized pedestrian-access
  enum, empty-on-absent (Rule #1). Priority: the `foot` tag wins over the `access` tag
  (foot is pedestrian-specific); if `foot` is absent, fall back to `access`. Normalize the
  chosen raw value to exactly one of:
  - `"yes"`  ← `{yes, designated, permissive, destination, official}`
  - `"permit"` ← `{permit}`
  - `"private"` ← `{private, customers, agricultural, forestry, delivery}`
  - `"discouraged"` ← `{discouraged}`
  - `"no"` ← `{no}`
  - `""` ← neither `foot` nor `access` present, OR the value is unrecognized (silence,
    never fabricate — an unknown access token is NOT coerced to `"yes"`).
  - **Provisional-enum note:** unlike `path_grade`/`psurface`, `foot_access` has NO CoMaps
    port — the bucket membership above (e.g. `destination`/`customers` placement, `permit`
    as its own bucket) is our own judgment call. It is internally consistent and testable,
    but the borrow-plan A1 canonical enum (open question 2) may pin membership differently;
    a later reconciliation PR to the persisted values is expected, not a surprise. Ship as
    specified.
- **AC-2.4:** All three functions are pure (no I/O, no logging that changes output), accept
  a plain `Mapping[str, str]`, and are total (never raise on a missing/garbage tag —
  `surface:grade="banana"` falls back to the default, does not crash).

### S3 — Carry the fields through `Feature`, consolidation, and persist on `CanonicalTrail`

**Given** `Feature` (`ingestion/conflate/match.py:80-96`) is a frozen dataclass with
`name/geom/source/ref/way_type`; `consolidate_osm_segments`
(`ingestion/pipeline.py:157`) merges connected same-named OSM ways into ONE `Feature`
(building it at line ~207 with only `name/geom/source/ref/way_type` — dropping any new
field); and `load_canonical_trail` (`graph/load.py:189-251`) SETs `CanonicalTrail`
properties via the `_UNSET`-sentinel upsert template (the `way_type` param at
lines ~223–228 is the exact pattern to copy)
**When** a trail is loaded
**Then** its `path_grade`, `psurface`, `foot_access` are persisted on the `CanonicalTrail`,
having survived consolidation via an explicit merge rule.

- **AC-3.1:** `Feature` gains three fields — `path_grade: str = ""`, `psurface: str = ""`,
  `foot_access: str = ""` — with `""` defaults so every existing positional/keyword
  `Feature(…)` construction (in `ingestion/`, `tests/`) still compiles unchanged.
- **AC-3.2:** `load_canonical_trail` gains three keyword params `path_grade`, `psurface`,
  `foot_access`, each defaulting to the module's `_UNSET` sentinel and each SET on the node
  via the same conditional-clause pattern as `way_type` (explicit `None`/`""` still SETs,
  so a re-ingest that loses a tag clears the stale value — source-or-silence).
- **AC-3.3:** Both `load_canonical_trail(…)` call sites in
  `ingestion/pipeline.py:_load_matches` (the auto-accept branch ~line 538 and the
  unmatched-spine branch ~line 603) thread the fields from the spine `Feature`
  (`m.a.path_grade`/`…` and `feat.path_grade`/`…` respectively).
- **AC-3.4 (consolidation merge rule):** the merged `Feature` built inside
  `consolidate_osm_segments` (pipeline.py ~line 207) carries a defined combination of its
  component members' fields, NOT `""`:
  - `path_grade`: **most-severe wins** — `expert` > `difficult` > `""`. (A merged trail is
    as hard as its hardest segment; never under-report difficulty — this is a safety
    signal per Rules #2/#7, degrade toward MORE caution.)
  - `foot_access`: **most-restrictive wins** — `no` > `private` > `permit` > `discouraged`
    > `yes` > `""`. (Never over-promise access across a merged run.)
  - `psurface`: **worst-quality wins** — any `*_bad` outranks any `*_good`, and among equal
    quality `unpaved_*` outranks `paved_*`, both outrank `""`. (Report the roughest tread
    a merged trail contains.)
  - A single-member component (or the `len(group) == 1` / `len(comp) == 1` early-returns)
    keeps its member's fields unchanged.
- **AC-3.5:** An end-to-end pipeline test: two connected same-named OSM ways, one
  `sac_scale=hiking` (→ `path_grade=""`) and one `sac_scale=demanding_mountain_hiking`
  (→ `path_grade="difficult"`), consolidate into one `Feature` with
  `path_grade == "difficult"`, and a `load_canonical_trail` call (captured via a
  list-appender runner) carries `path_grade="difficult"`.

---

## Definition of Done
- [ ] All ACs covered by at least one passing test (`tests/test_classify.py` for S2;
      extensions to `tests/test_pipeline.py` / `tests/test_load.py` for S1/S3;
      an osm.py-wiring test for AC-1.2).
- [ ] `make check` green (`ruff format --check` + `ruff check` + `mypy` + `pytest -m "not neo4j"`).
- [ ] Targeted self-review agent run over the diff; every CRITICAL fixed.
- [ ] `curator.py` NOT touched (A1.4); no `highway` value rewritten (A1.2); no `"normal"`
      or positive-grade default anywhere (A1.1).
- [ ] Epic file copied into `docs/epics/`; a row added to `docs/epics/README.md` index.
- [ ] Committed and pushed; PR opened into `main` titled with the "FOR REVIEW" convention,
      stating it must merge AFTER Epic 023 and naming the ingestion-pipeline-entrypoint
      merge-sensitive seam.
