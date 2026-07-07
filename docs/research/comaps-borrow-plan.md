# Adventure Planner ← CoMaps: The Borrow Program

**Synthesis of 25 verified proposals · adversarially checked · sequenced to `docs/strategy/path-to-complete.md` phases**
Status legend per item: **ADOPT-NOW** (Phase A, buildable) · **PHASE-D/E** (sequenced later) · **DEFER** (gated on an open decision). Every "adapt" verdict below carries the verifier's corrections inline — read them before scoping.

---

## 1. Executive summary

CoMaps (the Organic Maps fork) has solved, at planet scale and in battle-tested C++, a set of problems we are about to hit at regional scale: folding raw OSM tags into deterministic difficulty/surface/access facts, gating a build against class-specific data collapse, versioning a corpus so a bad ingest can never corrupt what is served, and handing a planned route off to the user's own device. This program borrows **patterns and format specs — never running code** — because their substrate is an immutable on-disk `.mwm` file graph and ours is a live-`MERGE` Neo4j property graph with a private personal overlay, a difference that reshapes almost every port. The near-term core is cheap and honest: capture the OSM difficulty/surface/access tags we already fetch-then-discard, capture authoritative agency length/gain, fix a dead-computed Duration that never reaches the screen, and give `/health` a build-ID that actually means something. The mid-term unlocks a real verdict surface (MARGINAL for borderline seasonal closures, an honest per-segment ETA, a two-axis difficulty badge) and the Phase-E table-stakes reach (trail search, water/shelter enrichment, named long-trail identity, GPX export as our entire on-trail answer). The two biggest-sounding ideas — a versioned-artifact corpus that retires the prune machinery, and a full offline search ranker — are correctly **deferred**: they are gated on the Aura DB-tier decision (Open Decision #3) and on an unwritten epic, and neither makes a currently-rendered claim truer.

A recurring correction from the verifiers, worth stating once up front: **CoMaps `DeterminePathGrade` returns only `{difficult, expert, empty}` — there is no `normal`.** Easy trails and good-visibility hiking fold to *empty*. Every difficulty proposal that said "normal/difficult/expert" was wrong; the empty-for-the-common-case shape is exactly the source-or-silence behavior we want, but the taxonomy must be labeled correctly or a missing tag will read as "Easy."

---

## 2. The plan, by wave

### WAVE A — Phase A substrate correctness (`path-to-complete.md:124-146`)
*The honest-substrate layer. Note: Phase A's own BLOCKING items are the `_build_canonical_id` slug-collision audit, the 1643→1458 conflation-delta audit, corroboration-off-constant-1, and MIN-fused confidence. Nothing below is a Phase-A blocker; these are substrate-completeness wins schedulable alongside that work, and several are explicitly "prep just ahead of Phase D."*

---

**A1 · Classify OSM tags at ingest → `path_grade` + `psurface` + `foot_access` on `CanonicalTrail`**
*(consolidates proposals "Capture-and-classify", "Two-axis difficulty", "Two-axis difficulty on Detail", "Tag-driven access classification")*

- **Borrow:** `generator/osm2type.cpp:822-848` (`DeterminePathGrade` folds `sac_scale`+`trail_visibility`); `osm2type.cpp:772-819` + word-lists (the surface-classification *tail* → `paved_good/paved_bad/unpaved_good/unpaved_bad`, incl. `;:/` compound tokenizer, `4wd_only`, `smoothness`/`tracktype` fallbacks); `generator/road_access_generator.cpp:53-159` (foot access enum + barrier mapping); `data/mapcss-mapping.csv:556-562` (Feb-2026 raw-`sac_scale` deprecation naming the tag forms to normalize).
- **Build:** stop discarding tags at `ingestion/fetch/osm.py:79-91` (the tags are already in `el['tags']` from Overpass `out geom`, line 72); extend the frozen `Feature` dataclass (`ingestion/conflate/match.py:81-96`) with `path_grade`/`psurface`/`foot_access`; new `ingestion/classify.py`; persist via the `way_type` upsert template pattern (`graph/load.py:203-233`) as `t.path_grade`/`t.psurface`/`t.foot_access` on `CanonicalTrail`.
- **Gets us:** a deterministic, LLM-free, source-backed difficulty/surface/access triple computed from tags we already fetch. Two *distinct* difficulty axes hikers actually mean: technical/exposure grade (a flat class-3 scramble stops reading "Easy") vs. physical effort.
- **Deprecates (guarded — see corrections):** narrows the frontend `√(2·climb·miles)` estimate (`frontend/src/data/summary.ts:94-117`) to the *effort* sub-axis only; supersedes the dead `transform.normalize_surface`/`normalize_allowed_use` vocab (`ingestion/transform.py:44-66`, called nowhere).
- **Unlocks:** substrate for the Phase-D difficulty guardrail (D1); a grade-aware ranking *screen* input; capability-calibrated difficulty (the flagged competitive white-space, `competitive-lateral-review.md:49`).
- **Effort:** M. **Verdict:** ADAPT (high).
- **Verifier corrections — load-bearing:**
  1. `DeterminePathGrade` returns `{difficult, expert, empty}`, **not** `{normal, difficult, expert}`. "normal" is the surface function's `surfaceGrade=2` default (`osm2type.cpp:605`), a different function. Adopt the empty-for-common-case shape; a missing tag must never render "Easy."
  2. Port **only** the surface classifier tail + word-lists, **not** `DetermineSurfaceAndHighwayType`'s primary highway-type rewrite (`osm2type.cpp:687-770`) — that is a CoMaps render concern.
  3. `is_trail_worthy` does **not** read `sac_scale`/`trail_visibility`/`surface` (it reads name/highway/access/foot/footway/ref/tiger). The "no extra fetch" claim holds; the attribution was wrong.
  4. **Do NOT retire** `curator.py:219-295` roadlike/access name-regex with `foot_access`: that heuristic keys on trail *name* (fire-road vs. access-road) *precisely because* OSM `access` tags are absent for tracks — `foot_access` would be empty for both. The "was approximating one question" comment (`curator.py:247-250`) refers to the **spatial boundary** signal (`is_outside_boundary_demoted`, already persisted), not access. Keep the name-heuristics and the `trail_filter.py:32-34,109` hard-drop intact.
  5. **Taxonomy collision, unresolved:** `intent.filters.difficulty` free-text is a *physical-effort* vocab (`_KNOWN_DIFFICULTIES` = easy/moderate/hard/strenuous, `curator.py`) and cannot map onto the *technical* `path_grade` (difficult/expert). `path_grade` needs a **new terrain screen**; the effort field stays separate. Resolve this before D1.
  6. US `sac_scale`/`trail_visibility` coverage is sparse (`docs/research/stage-1-data-sources.md:90`) — most east-coast trails yield empty grade. The durable win is cheap ingest-capture that future-proofs alpine/western regions; near-term badge density is low. `Epic 017`'s reserved field is DEM-derived `max_grade_pct` (physical steepness, USGS 3DEP) — a *complementary, different* signal, not this one.
- **Invariant note:** clean under Rule #3 (slow/structural, graph's home). Rule #1 holds **only** with empty-on-absent. One deliberate tradeoff if `trail_filter` private-drop is later softened to a `foot_access` hedge (see A3): that re-admits private drives — a corpus-pollution decision, not a silent fold.

---

**A2 · Capture authoritative agency length/gain + re-assemble NPS multi-part trails**

- **Borrow:** `generator/feature_merger.cpp:118-278` (endpoint-keyed segment merge discipline — *inspirational only*, see correction); the general CoMaps principle that agency attributes are captured at generation, not re-derived.
- **Build:** wire the four fields the loader already accepts but is never passed — `load_canonical_trail` (`graph/load.py:198-247`) exposes `length_mi`/`length_source`/`gain_ft`/`gain_source`/`is_loop`, but `pipeline.py:538,603` call it without them; read `GIS_MILES` in `ingestion/fetch/usfs.py:94` (its own docstring line 21 names it as known-but-unread); mirror `ingestion/usfs_convert.py:70-116` (`consolidate_by_trail_no`) for NPS to collapse the `nps.py:86-92` MultiLineString explosion; add `length`/`gain` to the frozen `Feature` (`match.py:80-96`) first.
- **Gets us:** a source-backed length even where DEM is absent (authority > derived); one conflation candidate per named NPS trail instead of N fragments sharing an OBJECTID.
- **Deprecates:** the elevation-derived length as the *only* length source (becomes fallback) — **but see correction 1**.
- **Unlocks:** cleaner corroboration counts; better agency-vs-OSM overlap scoring to calibrate the placeholder conflation thresholds (`match.py:99-267`).
- **Effort:** S–M. **Verdict:** ADAPT (high).
- **Verifier corrections:**
  1. "length comes only from 3DEP" is **wrong** — `usgs_3dep.py:187-196` emits gain/profile but **no length**; `t.length_mi` is written **nowhere**. The field is null across the entire corpus, so there is no "3DEP length to deprecate"; the gap is total.
  2. "duplicate-ref SourceRecords" is **wrong** — `_sr_uid(NPS, OBJECTID, name)` is identical per fragment, so `load_source_record` MERGEs them idempotently into **one** SourceRecord. The *real* harm: all N fragments share one `canonical_id`, so `load_canonical_trail` is called N times (`pipeline.py:603-614`) each overwriting `route_geom_wkt` — the surviving node keeps only the **last** fragment's geometry, and the matcher scores N agency features against every OSM candidate (candidate-set inflation).
  3. For **matched** trails the canonical node is built from the OSM spine (`m.a`, `pipeline.py:534-548`) while authoritative length lives on the agency side (`m.b`) — this is a **cross-side copy** (`m.b`→canonical), not pass-through.
  4. `feature_merger` merges by geometry endpoint, **not** by shared agency ref/OBJECTID — inspirational, not a blueprint; the real implementation copies our own `consolidate_by_trail_no`.
- **Invariant note:** length/gain are structural (Rule #3 permits). Must write `length_source` alongside `length_mi` (loader pairs them, `load.py:242`) and **never silently reconcile** conflicting agency-vs-derived lengths (Stage-1 rule: normalize each source independently). Centerline vs. round-trip disagreement is real — record honestly.

---

**A3 · Geometry/null-island validity gate + config-externalized exclusions**
*(the wireable half of the "hygiene.py + FilterElements" proposal)*

- **Borrow:** `generator/filter_elements.cpp:34-205` (JSON id+tag-AND blocklist, node/way/relation sections, `*` wildcard); `data/replaced_tags.txt:44-92` (canonicalization-before-classificator, `|u` update-in-place) — **lowest priority, see correction 4**.
- **Build:** activate the dead `ingestion/hygiene.py:15-47` `valid_lonlat`/`geometry_valid` checks in the load path (`pipeline.py:596-597` today drops only on missing name); new `regions/exclusions.json` migrating the incident-tuned denylists in `ingestion/trail_filter.py:52-93` (`_NAME_DENY`, `_RESIDENTIAL_STREET_SUFFIX`, `_PUBLIC_ROUTE_REF`) out of code into reviewable per-region config.
- **Gets us:** null-island/invalid-geometry reject actually running; a declarative, reviewable exclusion file so map-nonsense triage (TIGER routes, wellness-institution paths, OBX sand-street grids) is tunable without a code change.
- **Deprecates:** `hygiene.py` stops being test-only dead code; hand-tuned regexes migrate to config.
- **Unlocks:** per-region tuning as regions grow; an audit trail of why each element dropped.
- **Effort:** S for the validity half; the aggregate is M. **Verdict:** ADAPT (high).
- **Verifier corrections:**
  1. **The provenance-completeness gate does NOT belong here.** `has_provenance()` requires `source_pk` + `fetched_at`, which appear **nowhere** in `ingestion/` or `graph/` except `hygiene.py`'s own definition — the frozen `Feature` (`match.py:81-95`) carries `source`/`ref`/`way_type` but not those two. As a hard gate today it would reject **100%** of records. It is a dependent of **CDP-03** (capture-at-boundary provenance stamping, `path-to-complete.md:138`), not a standalone wire-up. Split it out and gate it behind CDP-03.
  2. `trail_filter` regexes are **not** dormant — `is_trail_worthy` runs **live at fetch time** (`osm.py:75`). Externalizing is a **migration with pinning tests**, not activation. Pin the current high-precision drops (Snake Rd SR-650, wellness paths, OBX sand-streets) or you lose incident-tuned behavior.
  3. `transform.py` "stops being dead code" is **unsubstantiated** — it's not imported by the pipeline but full-deadness is unverified.
  4. The `replaced_tags` canonicalization table is the **weakest** half — our Overpass ingest is pre-filtered to hiking highways, so we lack CoMaps' planet-scale synonymous-tag problem. Lowest priority.
- **Invariant note:** serves Rules #1/#7. Provenance gate must degrade-and-log per record, never reject a whole region on one bad record.

---

**A4 · Two-axis build identity: schema-format axis + composite build-ID + populate manifest vintage**
*(the cheap, now-portion of the two versioning proposals)*

- **Borrow:** `libs/platform/mwm_version.hpp:16-35` (Format enum v1..v12, validated at open) orthogonal to `mwm_version.cpp:37-46` (DATA version = `YYMMDD` snapshot date, a **separate** read); `libs/storage/storage.cpp:165-191` (monotonic-version commit, `ASSERT_GREATER` — a plain buffer with a version assert, **not** a "signed manifest").
- **Build:** replace `graph/schema.cypher:22-24`'s two-state `Meta.schema_version` (`0.1.0`-on-create/`0.2.0`-on-match — reports `0.2.0` forever, so `/health`'s signal at `api/app.py:345` is meaningless and cannot detect Aura-vs-local drift) with (a) a distinct **integer `schema_format`** validated at API startup so an old API refuses a newer-schema graph, and (b) a **composite build-ID** `{region}-{osm_extract_date}-{usfs_vintage}-{dem_sha}-{code_sha}` stamped on every `CanonicalTrail`; populate `regions/usfs_manifest.json` + `regions/dem_manifest.json` vintage/sha fields.
- **Gets us:** stops conflating "schema changed" with "data refreshed"; makes the corpus reproducible/diffable; a meaningful `/health` staleness signal.
- **Deprecates:** the naive `Meta.schema_version` stamp; the meaningless `/health` schema signal.
- **Unlocks:** schema-drift detection between Render and Aura; the `data_version` axis that the deferred versioned-artifact swap (F1) and the ingest-diff baseline (B1) both need as a coordination key.
- **Effort:** M. **Verdict:** ADAPT (high).
- **Verifier corrections:**
  1. **`ingest_version` is NOT "content-free" — do not replace it.** It is the region-scoped **prune anchor**: `graph/load.py:315` (`STARTS WITH "{region_id}-"`), `:320` (`<> $iv`), `:349-365` (`count_region_versions`), built at `pipeline.py:729-730`. The composite build-ID must **preserve the `{region_id}-` prefix** or region-scoped prune breaks. Add the composite `data_version` + `schema_format` **alongside**; keep (or derive) `ingest_version` as the prune key. Because `code_sha` changes every run, every re-ingest mints a new `iv` — safe **only** because `CanonicalTrail` MERGE is by version-independent `canonical_id`.
  2. Null `vintage`/`sha256` in the manifests is **not** a source-or-silence violation — the files' own comments document null as the deliberate honest "unknown, not assumed fresh" state. The real gap is the absence of a mechanism to **populate and propagate** vintage onto nodes. Reframe accordingly.
  3. Drop "signed" from the storage.cpp manifest description.
  4. The API-startup `schema_format` check must **degrade-and-disclose on `/health`**, not crash the process (fail-loud at the boundary ≠ crash the server).
- **Invariant note:** build-ID/schema-version are slow structural metadata — Rule #3 clean; strengthens source-or-silence at the build level.
- **Sequencing within A4:** `schema_format` + startup validation is small and independently valuable — do it soonest. Composite build-ID + required-vintage gating is operator-discipline plumbing whose headline "data is N days stale" UX only pays off once F1 lands and operators actually record vintages.

---

**A5 · Fix the dead-computed Duration + add estimate disclosure (Half A of the Tobler proposal)**

- **Borrow:** nothing yet — this is fixing **our own dead code**. (The CoMaps Tobler port is D2.)
- **Build:** `api/app.py:608-611` computes flat-Naismith `estimated_duration_min` and attaches it at `:649`, but the live mapper `mapElevationProfile` (`frontend/src/data/http/httpPlanner.ts:136-146`) **silently drops it**, and `Detail.tsx:116-117` reads `enrichment.durationHours` (a formatted *string*) which the live mapper leaves undefined (`httpPlanner.ts:92`) — so a computed Duration **never renders on the real HTTP feed** (only the mock engine populates it). Wire it through and **add an estimate qualifier at the render surface**.
- **Gets us:** a first-class Detail fact users expect, currently dead computed data.
- **Effort:** S. **Verdict:** ADAPT (high).
- **Verifier corrections:**
  1. Not a passthrough: `estimated_duration_min` is a **number** nested on `WireElevationProfile` (`api.ts:126-127`); Detail reads a formatted **string** `enrichment.durationHours` (mock `engine.ts:29`). Wiring needs a number→string transform + a VM-field decision (add `estimatedDurationMin` to the ElevationProfile VM and repoint Detail, OR synthesize `enrichment.durationHours`) — **not** the implied one-line `vm.ts:88` edit.
  2. **Invariant strain the proposal wrongly called "already handled":** `Detail.tsx:117` renders `<DecisionItem label="Duration">` with **no estimate qualifier**. The `estimated_` field name and backend comments disclaim, but the **UI presents it like a stated fact**. The disclosure must be **built at the render layer** to satisfy Rules #1/#7 — it does not exist today.
- **Invariant note:** query-time-derived from stored DEM; nothing new persisted (Rule #3 clean).

---

### WAVE B — Phase A/B ingest-safety tooling (`path-to-complete.md:136,154`)

**B1 · Per-category leveled ingest-diff check suite (dual absolute+relative thresholds)**
*(consolidates "Leveled prune diff suite" + "Per-category ingest-diff health artifact")*

- **Borrow:** `tools/python/maps_generator/checks/default_check_set.py:61-121` (dual abs-AND-rel gate: `norm(diff)>abs and get_rel>rel`, per-check tuned thresholds, low/medium/hard/strict levels); `checks/check_mwm_types.py:41-61` (per-type count diff); `checks/check_sections.py:43-82` (appeared/disappeared facet diff); `generator/statistics.py:70-112` (regex taxonomy-collapse into named buckets).
- **Build:** demote the single global `ADVENTURE_PRUNE_MIN_RATIO` (`graph/load.py:48-67`) from sole multi-trail defense to one row in a leveled matrix; new `ingestion/checks/` diffing a new ingest against a **persisted, facet-keyed baseline** per `{region, source, way_type, has_elevation, named/unnamed}`; emit a `stats.json` surfaced on `/health` + `scripts/gen_state.py` state.json, sorted by `|delta|`.
- **Gets us:** catches class-specific collapses the total-count ratio structurally cannot see — NPS silently returns half, a `trail_filter` change over-drops one `way_type`, or the whole elevation layer goes null, all while total stays above 50%.
- **Deprecates:** `ADVENTURE_PRUNE_MIN_RATIO` as the *only* multi-trail defense (keep it as the coarse floor); generalizes the elevation-coverage≥0.8 check in `verify_before_prune` into one facet-diff framework.
- **Unlocks:** a human-readable regression report per re-ingest (fixes the "prune doesn't self-heal and you can't see why" gap); a CI "strict" diff pass (Phase-B Epic 009 gate); the go/no-go signal that gates F1's pointer flip.
- **Effort:** M. **Verdict:** ADAPT (high).
- **Verifier corrections:**
  1. Our current gate is **not** a single global constant — `verify_before_prune` already compares each region against its own `pre_load_count` (`pipeline.py:739`), so the 50-vs-2000-trail **scale** example is already handled *for the total*. The genuine new value is per-**class** granularity, not per-region scale. Sharpen the pitch and drop the redundant scale framing.
  2. `statistics.py` lives at `tools/python/maps_generator/generator/statistics.py` (the generator's stats config), **not** in `checks/`. And CoMaps diffs two **immutable `.mwm` directories** (old-vs-new is free per build) — that substrate does **not** port; only the *pattern* does (`adopt-pattern` is honest).
  3. **No persisted baseline exists today** — `verify_before_prune` uses the live within-run `pre_load_count`, not a frozen prior. The facet-keyed baseline snapshot is the **central new mechanism and bulk of effort**, not a "risk" footnote. It extends the scalar `pre_load_count` into a facet-keyed dict. Natural once A4/F1 land; otherwise B1 must build its own frozen-snapshot persistence.
  4. **Do NOT** fully subsume `verify_before_prune`'s hard-ABORT gate (`pipeline.py:449-469`, raises `IngestVerificationError`) into advisory facet-diff — keep the raising gate as the catastrophic backstop, add the facet suite as the finer tier. Run all buckets at "strict" for visibility; **hard-gate the prune only on "hard" abs+rel breaches**, else noisy per-region churn blocks the pipeline.
- **Invariant note:** build-time CI tooling — touches no runtime invariant; reinforces the Rule #6/#8 data-safety posture.

**B2 · Content-hash manifest + numbered migration ledger** *(the next-phase half of A4)* — SHA over the new subgraph for deterministic corruption detection beyond count heuristics; a numbered + applied-set migration ledger on `Meta` (makes Aura-vs-local drift detectable). Effort M. Sequence **with** A4's build-ID.

---

### WAVE C — Phase C history import (`path-to-complete.md:170,179`)

**C1 · GPX import reader tolerance**

- **Borrow:** `libs/kml/serdes_gpx.cpp` — dedupe consecutive near-identical points (`Pop()` at `kTrkPt` via `AlmostEqualAbs(..., kMwmPointAccuracy)`), drop <2-point segments (`if (m_line.size() > 1)`), `CheckAndCorrectTimestamps()` (~184-240: interpolate interior gaps, edge-fill first/last valid, **clear if >50% invalid**); `libs/kml/types.hpp:391-427` (`MultiGeometry` parallel lines+timestamps).
- **Build:** the Phase-C authed-episode intake — today only a FIT stub (`ingestion/ingest_episode.py`, "Episode ingestion from a FIT file (stub)", requires `fitdecode`; `upsert_episode` batch-only, `graph/queries.py:239`). Reuse the cleaning heuristics as the front-end normalizer before map-matching (CDP-20 HMM snap / free-floating fallback, Open Decision #10).
- **Gets us:** removes the unglamorous blocker on the critical path — noisy Garmin/Strava GPX exports (which *are* GPX, not FIT) carry exactly the duplicate-point / degenerate-segment / partial-timestamp mess this reader handles.
- **Unlocks:** the `been_on` producer that `Epic 006` novelty is self-blocked on (`roadmap.md:57,112,137`); the Stage-7 memory eval; shares the serdes module with GPX **export** (D4).
- **Effort:** S (reader-tolerance) + separate L (map-matching, Open Decision #10). **Verdict:** ADAPT (high).
- **Verifier corrections:**
  1. `borrow_type` overstated — port the **~3 cleaning heuristics**, not the C++ XML-SAX parser. Python has mature GPX parsers (`gpxpy`/`lxml`); layer the heuristics on top. This is what keeps it honestly S.
  2. **Rule #3 tension under-flagged:** the cleaned `MultiGeometry` polyline must feed map-matching **in-memory only** and **never** be written to `:Episode`. The existing `FITSummary` already enforces exactly this ("`gps_track` consumed in-transform... NEVER written to `:Episode` (Rule #3)") — reuse that discipline, don't invent a new geometry path.
  3. **Rule #1:** `CheckAndCorrectTimestamps`' "naive interpolation" manufactures interior timestamps — interpolated points **must carry a derived flag** and the Outcome screen must never present interpolated moving-time as measured. Elevate to a hard gate/test.
  4. Strip residual personal metadata on import (Rule #5).
- **Sequencing:** we are **pre-Phase-C** (auth unbuilt, `been_on` unconsumed). Build at Phase-C kickoff alongside auth + the authed-episode endpoint + the Epic 006 producer. Not now.

---

### WAVE D — Phase D honest verdict surface (`path-to-complete.md:190-212`)

**D1 · Wire `path_grade`/`psurface` into a difficulty guardrail + Detail two-axis badge** *(Phase-D half of A1)* — turns the parsed-but-inert `intent.filters.difficulty` (soft judge hint via `filter_preference_hints`, `engine.py:418`) into a real screen. **Blocker:** resolve the A1 taxonomy collision first — `path_grade` (technical) needs a **new terrain screen**; the effort-vocab `intent.filters.difficulty` stays a separate axis. Grade is a non-compensatory **screen** input, never a rank term (Rule #2). Effort M.

**D2 · Tobler per-segment ETA + `pace_on_grade` personalization** *(Half B of the Tobler/Duration proposals — Epic 007 gated)*

- **Borrow:** `libs/routing/edge_estimator.cpp:89-122` — the **composite pedestrian ETA** (Tobler for `|tangent| ≤ 1.19`, polynomial coefficients `3.01·t + 3.54·t²` for steeper grades and the Weight purpose), `0.35` descent asymmetry (`:93`), `>2500m` (`kMountainSicknessAltitudeM`) altitude penalty (`:95-96`); `libs/routing_common/pedestrian_model.cpp:29-61` (the honest **weight-vs-eta split** — `eta` stays 5 km/h, weight carries preference — which is our exact "taste shapes preference, surfaced number stays honest" invariant as two numbers).
- **Build:** replace flat Naismith (`api/app.py:608`) with a per-segment integral over the already-persisted 3DEP arrays (`profile_distances_m`/`profile_elevations_m`, read at `app.py:628-630`); personalize by `PhysicalProfile.pace_on_grade` (`belief_update.py:64`, EWMA α=0.3) **on the local path only** (`engine.py:505-561`).
- **Gets us:** a defensible per-segment ETA modeling descent + altitude that flat Naismith ignores; the effort **floor** the Curator structurally lacks.
- **Effort:** M (L with the design-session dependency). **Verdict:** ADAPT (high).
- **Verifier corrections — two invariant tensions, both in Half B:**
  1. **"Tobler per-segment ETA" oversimplifies** — CoMaps uses Tobler only for gentle grades; steeper grades and the Weight purpose use polynomial coefficients. Port the composite, not pure Tobler.
  2. **Rule #7 (capability ≠ preference):** `pace_on_grade` is a *measured capability* signal; folding it into the surfaced ETA personalizes an estimate by capability — defensible **only** for a logged-in viewer with disclosure. The anonymous-viewer number must stay generic.
  3. **Rule #2 + Phase-D screen-then-rank:** the proposal's "give the Curator the effort/ETA **ranking** term it lacks" runs directly against CDP-10/09 (`path-to-complete.md:190-197`) and CDP-20 (graph-arch Card 16): effort is a **non-compensatory screen/floor** and a query-time cost **modifier**, never a compensatory rank term that reorders by desirability. Reframe as a floor.
  4. **Epic 007 has no epic file and needs a design session before it can be DEFINED** (`path-to-complete.md:30,197,339`) — Half B **cannot be built to spec today**.
- **Sequencing:** Half A (A5) now; Half B here, gated behind Epic 007's design session.

**D3 · `access:conditional` seasonal-closure → MARGINAL verdict input**

- **Borrow:** `libs/routing/road_access.cpp:50-84` (`GetAccess` evaluates `access:conditional` against osmoh opening-hours at **arrival time = now + travel**); `:115-128` (`GetConfidenceForAccessConditional` tests `IsOpen` at moment ± `kConfidenceIntervalSeconds/2` = ±1h → both-open=**Sure**, one-open=**Maybe**, neither=no-signal); `generator/road_access_generator.cpp:45-51` (`kTagToAccessConditional`: `winter_road=yes`/`ice_road=yes` → synthesized `no @ (Mar-Nov)`).
- **Build:** parse OSM `opening_hours`/seasonal tags at ingest into a persisted closure-**window** property; evaluate at query time in `orchestration/verifier.py` alongside the RIDB permit probe; feed the ±window Maybe/Sure into the CDP-04 GO/MARGINAL/NO-GO verdict (today `evaluate_guardrails`, `curator.py:122-201`, is binary blocked/warnings — no MARGINAL, no seasonal input).
- **Gets us:** a MARGINAL verdict when a closure is borderline instead of a false all-clear; a "closed for the season, source-stamped" silence state.
- **Effort:** M. **Verdict:** ADAPT (high).
- **Verifier corrections:**
  1. **Drop or hard-hedge the `winter_road`/`ice_road` → "Mar-Nov" synthesis** — it fabricates a specific month boundary from a boolean and is Northern-hemisphere-buggy (CoMaps' own TODO at `road_access_generator.cpp:48`). Confidently-wrong precision on a safety-adjacent claim = the exact Rule #1 failure. Keep only real `opening_hours`/seasonal tag **values**.
  2. Arrival-time evaluation must use **region-local wall-clock + DST**, not server/system time — CoMaps' `system_clock` local time (`road_access.cpp:130`) is fine for a single-device offline app but wrong for a multi-region hosted API. Depends on the Phase-D timezone-correctness item (`path-to-complete.md:78,206`).
  3. **Authoritative NPS/USFS alert closures must OUTRANK OSM windows** (CDP-06 weakest-link MIN fusion) — elevate the proposal's own risk to a requirement.
  4. Wiring nit: Maybe/Sure is a **presentation hedge**, not a `freshness` value — `confidence.py` freshness is a `live/near_real_time/slow/stale` enum; map Maybe → hedged presentation directly.
- **Invariant note:** window is slow/structural (Rule #3 clean); "open right now" stays JIT.

**D4 · GPX/KML export — the on-trail handoff**

- **Borrow:** `libs/kml/serdes_gpx.cpp:516-605` (`SaveTrackData`/`GpxWriter::Write` — `trk`/`trkseg`/`trkpt`, altitude-guarded `<ele>` via `TrackHasAltitudes`, Garmin `gpxx` + OSMAnd `gpx_style` + `xsi` color extensions, CDATA-safe names). Borrow the **GPX 1.1 format + extension namespaces + the altitude gate**, not the C++ type machinery.
- **Build:** `GET /trail/{id}/export.gpx` + a "Send to device" action on `Detail.tsx:99-101` (beside `SaveButton`/`DirectionsLink`); serialize `route_geom_wkt` (`schema.cypher:71-77`) + persisted 3DEP profile + trailhead into a minimal single-track GPX.
- **Gets us:** the on-trail moment we have **zero** answer for — plan on our calm surface, carry the route to the user's own Garmin/Coros/phone. Roadmap covers GPX **import** only (`path-to-complete.md:179`); no user-facing export anywhere in A-G.
- **Deprecates:** nothing — additive. It does **not** make us a nav app.
- **Effort:** S–M (writer core ~90 lines; reuse the format, not the type graph). **Verdict:** ADAPT (high).
- **Verifier corrections:**
  1. Not a literal `FileData`/`MultiGeometry` port — minimal one-track serializer (`route_geom_wkt` → single `trk`/`trkseg`, optional `<ele>` from `profile_elevations_m`, one trailhead `<wpt>`).
  2. **Rule #5 is the live risk:** serialize the **world/corpus** `route_geom_wkt` (shared node), **never** the viewer's personal episode geometry — the Strava privacy-zone leak (`vision.md:65`) is the cautionary tale. Consequence: because it exports world data it needs **no auth** and is anonymous-friendly — **decoupled from Phase C**; could ship earlier.
  3. `<ele>` gate maps 1:1 to our existing null-on-no-DEM `elevationProfile` discipline — strengthens source-or-silence.
  4. Discount the contingent unlocks (native drops offline maps, import round-trip) — they depend on other proposals.
- **Sequencing:** Phase D (decided trip → carryable artifact) or early Phase E; not gated on Phase C.

---

### WAVE E — Phase E table-stakes reach (`path-to-complete.md:221+`)

**E1 · Named-trail relation assembly + endpoint-stitch enhancement**
*(consolidates "Named-trail relation assembly" + "Reassemble fragmented ways")*

- **Borrow (relation half — net-new, valuable):** fetch `rel[type=route][route=hiking|foot|superroute]` — `ingestion/fetch/osm.py:31-48` is way-only, never fetches relations. `generator/relation_tags.cpp:148` confirms CoMaps propagates `foot=yes` from hiking relations but **skips names** — the shared-unsolved problem, so this sets a realistic target.
- **Borrow (geometry half — idiom only):** `generator/feature_merger.cpp:118-278` — the O(n) **endpoint-quantize→hashmap adjacency** idiom (`GetKey`/`PointToInt64Obsolete`), *not* the algorithm.
- **Build:** enhance `consolidate_osm_segments` (`pipeline.py:117-216`, name-group + O(n²) 40m union-find) — replace O(n²) with O(n) endpoint-quantize, add a **net-new same-name-or-same-relation continuation guard**, rescue suffix-only "Trail" names currently dropped at `pipeline.py:179`, merge same-trail connected segments whose names differ (renamed segment).
- **Gets us:** a real `CanonicalTrail` identity for named through-trails (AT, Rivanna) instead of name+spatial guessing.
- **Effort:** L (M for logic, L with safety/back-fill). **Verdict:** ADAPT (medium confidence).
- **Verifier corrections — the geometry half was badly misread:**
  1. `feature_merger` is a **World.mwm low-zoom rendering generalizer** (`world_map_generator.hpp:96,117-120`), keyed on feature **TYPE** only, with **no name/identity gate**. Its `DoMerge` explicitly picks the **SHORTEST** continuation "to avoid producing too long lines" — the **opposite** of assembling one long named route. Ported as-is it fuses distinct same-type connected trails (a dense park path network all tagged `highway=path` collapses into one blob) — structurally **worse** than name-grouping. `borrow_type` should be **borrow-idiom**, not port-algorithm. The same-name/same-relation guard has **no CoMaps prior art** — build it net-new.
  2. **Do NOT retire Scout name-dedupe** (`scout.py:60-89`): D11 exists precisely for **disconnected** same-name segments (a canal walk split into pieces), which endpoint-stitch **cannot** merge (it requires connectivity). Complementary, not substitutes — name-dedupe stays.
  3. **Does not fix the slug-collision** — `_build_canonical_id` collision (`pipeline.py:72-91`) is a string-hashing problem between two *distinct* trails; geometry stitching doesn't touch it. The audit fix is the hash-suffix guard, orthogonal.
  4. `route.py:119-139` (`_assemble_lines`, shapely `linemerge`) **already** provides ordered-polyline stitching — not a missing capability. The genuine deltas are O(n) vs O(n²) and name-agnostic stitching (the latter is itself invariant-risky — it's the "Lead 2 map-nonsense" the pipeline docstring warns produced wrongly-fused trails).
  5. Relation fetch is partial in the US (`stage-1-data-sources.md:90`) — must fall back to guarded stitching.
- **Sequencing:** **next-phase, NOT now.** Adding relation-based identity changes `canonical_id` derivation, which collides head-on with Phase A's in-flight 1643→1458 slug-merge audit + `canonical_id` back-fill (`path-to-complete.md:139` — re-keying orphans Episode/Belief/grant edges). Sequence at Phase-E B001/B005 **after** the identity scheme is stable; scope as a spike first.

**E2 · Offline trail search on CoMaps' linear ranker + fuzzy matcher** — **DEFER to Phase E.**
- **Borrow:** `libs/search/ranking_info.cpp:347-411` (single-scalar linear model); `ranking_utils.hpp:219-361` (Levenshtein-DFA + offset-sliding `GetNameScores`, 6-level ladder); `ranking_info.cpp:104` (`kStreetType[Outdoor]=0.0` — trails deliberately not boosted, the documented **inversion** point for a hiking product); `ranking_info.cpp:34` + `real_mwm_tests.cpp:697` (`static_assert` wall + `Famous_Cities_Rank` golden test).
- **Why defer:** B001 search is Phase E and the **epic is explicitly unwritten** (`path-to-complete.md:221` "WRITE THE EPIC"); we are at Phase A, with Phase C auth as the gating pivot. Nothing to build now. **Verdict:** DEFER (high).
- **Verifier corrections:** (1) `GetNameScores` is a **scorer over already-retrieved candidates**, not a retriever — CoMaps feeds it from an offline inverted `.mwm` index **we lack**; port the scorer + build a **Neo4j-side candidate feed** (brute-force over ~1500 trails is fine, effort L stays sane). (2) **Rule #2 conflict:** the graded name-match score is **relevance, not confidence** — must stay **strictly separate** from the `freshness·authority·corroboration` confidence property; folding it in corrupts a non-negotiable. (3) `kStreetType` inversion is near-moot for us — our corpus is trail-first with roadlike already de-ranked. (4) "per-category bonus == Curator taste" is a loose analogy (fixed static vector vs. per-user learned preference).
- **Independently adoptable earlier:** the `static_assert`+golden-test **coefficient-pinning discipline** — pin every Curator taste/novelty/party weight with a regression test, a gate we currently lack. Directly supports the "confidence never penalizes ranking" invariant by making the weights testable.

**E3 · Outdoor-POI enrichment overlay (water potability, graded shelter, viewpoints)**
*(consolidates the two POI proposals)*

- **Borrow:** `data/mapcss-mapping.csv:629` (potable set: `drinking_water=yes|treated|refill`), `:1734-1737` (negation set); `:275,453-454,1199,167` (graded shelter: `alpine_hut`/`wilderness_hut` vs. `amenity=shelter`+`shelter_type basic_hut|lean_to`, with generic `amenity=shelter` demoted at z17 to avoid the bus-stop-as-backcountry-shelter trap); `data/styles/default/include/Icons.mapcss:62-192` (min-render-zoom as a rough salience prior); `generator/descriptions_section_builder.cpp:32-66` (OSM-id-keyed overlay).
- **Build:** a new slow/structural POI ingest pass (sibling to `ingestion/ingest_trailheads.py:28-163`); consumed by `orchestration/verifier.py` (nearest potable water, source-stamped) + `orchestration/curator.py` (en-route waypoint salience); surfaced on Detail.
- **Gets us:** the backpacking-grade water/shelter layer we entirely lack — `vision.md:19` names FarOut's per-feature water status as the provenance bar we aim to beat; our only "water" today is live JIT streamflow (`usgs_water.py`), a different thing.
- **Deprecates:** nothing — additive. (Adopt the `shelter_type` split, not a flat `shelter` node — that avoids a trap.)
- **Effort:** L. **Verdict:** ADAPT (high). **New epic needed.**
- **Verifier corrections — Rule #1/#7 critical:**
  1. **DROP "default-potable-unless-negated."** CoMaps assigns potable **only** on explicit `drinking_water=yes/treated/refill` — **never** by absence-of-negation. Inferring potable from an untagged source **fabricates a safety fact**. Potability must be **explicit-tag-driven in both directions** with a large untagged "unknown" middle that stays silent.
  2. **The legal-vs-physical split is largely a myth to lift:** CoMaps *folds* `drinking_water:legal=no` into the **same** `drinking_water_no` type (`:1734-1735`) and doesn't check `:legal` for springs/`water_point` (`:1736-1737`) at all — it **collapses** the distinction. Don't attribute a legal/physical hedge to CoMaps; we could build it as **our own** differentiator, but must not promise it as a borrow.
  3. min-render-zoom is label-collision/declutter tuning correlated with importance — a **rough prior only**, not an authoritative backpacker-relevance order.
  4. Stamp each POI `source=OSM` + `fetched_at` + confidence hedge (like trailheads already do). Persist tag/type only; flow/availability stays JIT.
- **Sequencing:** **Phase E, gated behind Epic 018** (live-conditions-on-card JIT overlay must exist first so static potable-points and live streamflow reconcile on the card, not surface as one unreconciled concept). The taxonomy can be captured as an adopt-spec now, built at E.

**E4 · DEM-coverage / NoData build gate** — **mostly descoped by the verifier.**
- **Borrow:** `generator/srtm_coverage_checker/srtm_coverage_checker.cpp:107-200` (`CheckCoverage` flags a tile if >10% points lack SRTM).
- **The one genuinely-new sliver:** `scripts/fetch_dem.py:135-160` merges+clips to bbox but verifies **only checksums** — add a **fetch-time NoData/hole assertion** on the clipped raster to fail loud before ingest consumes a corrupt/missing tile. Cheap. **Verdict:** ADAPT (high) — but small.
- **Verifier corrections (three of five bullets in the original proposal die):**
  1. The `CheckCoverage` region-completeness gate **already exists in stronger form** — `verify_before_prune` (`pipeline.py:411-466`, `ADVENTURE_ELEV_MIN_COVERAGE=0.8`) already aborts the prune on low per-node 3DEP coverage, measured against real trail nodes. Only detection *timing* would change.
  2. `CheckDistance` interpolation-quality gate is **architecturally moot** — `elevation.py build_profile` densifies geometry to 20m and resamples the DEM at every densified point; we **never** linearly interpolate elevation between sparse vertices, which is the exact failure `CheckDistance` exists to catch. Porting its 1-arcsec resampling adds build cost for a non-existent problem. **Drop it.**
  3. "region ⊆ tiles" is **tautological**, not merely degenerate — every region ships a **placeholder bbox** (Shenandoah is a 5-point box) and manifest tiles are generated from that same bbox, so the assertion **can never fail** under current data.
- **Sequencing:** the coverage-gate half only becomes non-tautological once regions ship **real polygons** (Phase E region-geometry tightening); the fetch-time NoData assertion could land now but is low-urgency.

**E5 · Wikipedia/landmark descriptions as an OSM-id-keyed derived overlay** — **DEFER to Phase E/G, gated on Phase A id-stabilization.**
- **Borrow:** `generator/descriptions_section_builder.cpp:32-66,91-107` (wiki-URL-first, wikidata-QID fallback); `.forgejo/workflows/mapgen-wikipedia.yml:124-169` (out-of-band scheduled bake, <90d staleness gate); `libs/descriptions/serdes.hpp:157-204` (versioned sorted-index binary search + language-prioritized fallback).
- **Build:** a derived Description overlay keyed on the **stable `SourceRecord.sr_uid`** (the OSM id our SAME_AS already carries), **not** `canonical_id`; plug into the shipped Epic 017 enrichment framework (`SourceKind.enrichment`, `_run_enrichment` `pipeline.py:273/709`).
- **Effort:** M at region scale. **Verdict:** DEFER (high).
- **Verifier corrections:**
  1. **CoMaps does NOT key by stable OSM id** — its persisted `.mwm` section is keyed by internal `FeatureIndex`; the OSM id is only a bake-time QID lookup, and it survives rebuilds by **fully re-baking each generation**. Our "survives via `sr_uid`" is a valid *adaptation*, not what CoMaps does.
  2. The cited join point is **inconsistent** — `load_enrichment_facts` (`graph/load.py:670-687`) keys on `canonical_id` and SETs on `CanonicalTrail`; it **cannot** be reused as-is for an `sr_uid`-keyed overlay. Correct target is facts-on-`:SourceRecord` (`schema.cypher:9`), needing a new loader variant.
  3. **Rule #1/#7 strain:** Wikipedia prose is tertiary/user-generated and can carry safety-relevant claims — present as clearly-attributed **encyclopedic context at authority_tier 3**, never fused into best-view conditions/attributes (aligns with CDP-14 persona/conclusion split).
  4. Do **not** replicate CoMaps' planet-scale wikiparser — hit the live Wikipedia/Wikidata API for the few wiki-tagged features per region.
- **Sequencing:** the overlay's stable-keying premise **depends on** the Phase-A `canonical_id` back-fill / slug-merge audit completing first.

---

### WAVE F — Deferred structural / ops (Phase E/F, gated on Open Decision #3)

**F1 · Versioned-artifact corpus with atomic per-region pointer-swap** — **DEFER.**
- **Borrow:** `libs/storage/storage.cpp:1117-1126` (`RenameFileX` atomic swap), `:742-746` (latest-wins registry); `libs/platform/local_country_file_utils.cpp:214-236` (GC-after-validate gated on `latestVersion`); `local_country_file.cpp:107-111` (per-file SHA1 integrity gate).
- **The idea:** build a new `data_version` subgraph beside the live one, verify+SHA-gate it, flip a per-region `CurrentVersion` pointer — a bad ingest can **never** corrupt what is served, plus instant rollback. Would retire the whole self-wipe defense stack (`prune_stale_trails` Guards 1/2, owned-ref DETACH-skip, region `-` anchor, `verify_before_prune` raise-to-skip, `graph/load.py:385-517`).
- **Effort:** L (verifier: **XL**). **Verdict:** DEFER (high). **Three load-bearing problems:**
  1. **File→graph disanalogy.** CoMaps versions a self-contained, **reference-free** `.mwm` file — renaming one immutable file is trivially atomic. Our corpus is a **referential property graph** where the private overlay holds edges **into** world nodes (`(:Episode)-[:ON]->(:CanonicalTrail)`, `queries.py:309-313`; Beliefs `DERIVED_FROM`). "Rewire-on-flip" is a **graph migration on every ingest** (move every Episode/Belief edge to the new-version node by `canonical_id`, atomically, without a concurrent viewer seeing a half-rewired overlay) that itself needs the exact owned-ref safety it claims to retire. Not an L.
  2. **Read-path rewrite is broad, not "woven into ScopedSession."** `ScopedSession` (`client.py:95-149`) merges `$viewer_id`/`$granted_ids` **params**; it does not rewrite query bodies. A version pointer "all scoped queries read through" forces a version predicate into **every world-node MATCH** across `queries.py` (~40 MATCH clauses), `scout.py`, `context_assembly.py`, `api/app.py` — a **second** cross-cutting "every query must carry X" surface layered on the Rule #4 access-control one, raising the odds of a query that silently reads a non-current version.
  3. **Aura ceiling trades one risk for another.** Two live `data_versions` per region ≈ 2× nodes through the ingest+verify window. Open Decision #3 (`path-to-complete.md:336`) says Aura Free's ceiling **already binds at 1×**. This replaces the prune-wipe hazard with a ceiling-overflow hazard dependent on an immediate GC that can itself fail. **Not strictly stronger** under the real deployment constraint.
  - **Roadmap:** the guards it retires **already shipped and work** (M1/PR#74, `verify_before_prune`/PR#95). It makes **no rendered claim truer** — Phase A's test — so it fails the Phase-A bar. Its unlocks (rollback UX, blue-green, manifest/SHA, a home for the commons FIT overlay) are Phase-B+ operational substrate.
- **Sequencing:** Phase E/F, **gated on Open Decision #3 (DB-tier) landing first**. If pulled forward, cut scope to staged-build-then-relabel core (build new subgraph → verify+SHA → relabel/pointer-flip → GC old) and **require an explicit atomic owned-overlay rebind algorithm + a scoped read-path version-predicate design before any code**; do not bundle rollback UX / A-B / commons overlay.

**F2 · Stage/resume pipeline model** — **DEFER.**
- **Borrow:** `tools/python/maps_generator/generator/status.py:14-52` (file-based `need_skip`/catch-up); `stages.py:167-243` (`outer_stage` decorator + per-country status); `generation.py:83-152` (dependency-closure skip + `reset_to_stage`).
- **The idea:** decompose the monolithic `run_pipeline` (`pipeline.py:642-801`) into named resumable stages + `--resume-from`, so a crashed multi-region batch resumes at the region+stage it died on.
- **Effort:** M (verifier: M–L). **Verdict:** DEFER (high). **Corrections:**
  1. **No in-process multi-region batch exists** — `run_pipeline` is invoked **once per single `--region`** (`pipeline.py:882`, `Makefile:79`). "Batch resumes at region+stage" is false; the realistic win is per-region single-run resume.
  2. **Safe mid-load resume is gated on F1** — `pre_load_count` is snapshotted before `_load_matches` (`pipeline.py:739`) and feeds the collapse gate + prune; re-running a partially-crashed load **pollutes the denominator** with already-MERGEd nodes. Standalone value limited to fetch/conflate boundaries.
  3. At current scale (4 regions, ≤1481 trails, minutes-long fetches) re-fetch cost is low — modest ROI now.
- **Sequencing:** **with F1**, then Phase-E B002 continental scaling. Do not land standalone before F1.

---

### CROSS-CUTTING · Native-iOS posture (record now, decide at Phase G)

> **PO note (2026-07-06, Josh):** the owner's lean is the *opposite* of the proposal's "native drops offline-maps scope" — becoming an on-trail offline guide is explicitly in play, with a far-horizon local on-device LLM companion layered on our main intelligence (see `docs/vision.md` § "Far horizon — the on-trail companion"). GPX export (D4) still ships first as the bridge regardless; the Phase-G native decision now weighs the offline guide + companion *up*, not down. The verifier's factual corrections below (fabricated vision citation; decision-log §15 lists offline as a native advantage) stand — they in fact support the owner's lean.

**Native-scope reframe: export-to-device is our on-trail answer, so native drops offline-maps scope** — **record as a contingent posture, do NOT present as resolving the open decision.**
- **The reframe:** CoMaps' entire `generator/`+`drape`+`routing`+`storage` stack proves on-device offline-maps+turn-by-turn is an enormous, self-contained build. Name GPX export (D4) as our on-trail answer, collapsing native iOS's remaining justification to APNs push + background geofencing for the CDP-11 perishable-safety watch + marginal HealthKit — **not** offline maps. Lets Phase-E PWA offline stay deliberately thin (cache last plan + conditions snapshot with **loud** staleness per CDP-08, `vision.md:63`).
- **Effort:** S. **Verdict:** ADAPT (medium) — **but the framing is fabricated:**
  1. **FALSE CITATION:** `vision.md:82-91` does **NOT** refuse on-trail nav — those lines are the **engagement/social/scoring** refusals only (no streaks/leaderboards/infinite-scroll/readiness-score/guilt-notifications/paywalling-safety/model-training). No on-trail-nav refusal exists in the doc. The proposal fabricated the exact alignment it leaned on.
  2. **OPPOSITE OF CURRENT DOCS:** `decision-log.md:149` lists on-trail offline maps as a **remaining native advantage** and `:208` as a **Phase-4 deliverable**. This is a **new** decision to *edit* those lines, not a clarification of an existing refusal.
  3. **DEPENDENCY UNBUILT:** a GPX device-**export** is not a committed item — only GDPR data-export (`path-to-complete.md:74`) and GPX **import** (B003) exist. The whole hinge (D4) must be scoped first.
- **Sequencing:** record now as a **contingent posture** (like the anti-engagement refusals, stated as identity not gap); decide for real at Phase G (decision-log §15, "the last decision"), contingent on D4 shipping.

---

## 3. What we explicitly do NOT borrow

- **Elevation profile chart on Detail + card/Detail two-tier split** *(rejected — duplicative).* Everything proposed is **already shipped** (Epic 017 S4/S5b). The premise "Detail only shows Ascent as a scalar" is **factually false**: `Detail.tsx:130` renders `TerrainMap`, `TerrainMap.tsx:154-155` renders `<ElevationProfile>` — a complete accessible SVG distance×elevation chart (`frontend/src/screens/map/ElevationProfile.tsx`) with scrubbable cursor, keyboard slider, gain/loss/max-grade labels (`:87-89`). The card-light `ElevationGlyph` (`RecommendationCard.tsx:54`) **is** the two-tier split. Cumulative-distance x-axis exists via `profile_distances_m`/`profile_elevations_m` (`graph/queries.py:147-148`) → `WireElevationProfile` (`api/app.py:614-649`). Silence states exist. The CoMaps citations are accurate but buy us nothing.
- **CoMaps' "default-potable-unless-negated" water model** (E3) — copied literally it **fabricates a safety fact** for untagged sources (Rules #1/#7). Adopt only the explicit-tag path.
- **CoMaps' `winter_road`/`ice_road` → "Mar-Nov" closure synthesis** (D3) — fabricated month precision from a boolean, hemisphere-buggy (CoMaps' own TODO).
- **`CheckDistance` interpolation-quality gate** (E4) — architecturally moot; we densify+resample the DEM and never interpolate between sparse vertices.
- **`feature_merger` as a named-route assembler** (E1) — it is a type-keyed *rendering generalizer* that picks the shortest continuation; ported as-is it fuses distinct trails (the "map-nonsense" we deliberately backed away from). Borrow only the O(n) endpoint-quantize idiom.
- **The literal on-disk dual-version pointer-swap + GC** (F1 core) — a file-immutability idiom with no clean analogue in a live-MERGE graph; doubles nodes against the Aura Free ceiling; forces owned-overlay re-anchoring.
- **Search-relevance score as a confidence signal** (E2) — relevance ≠ the `freshness·authority·corroboration` confidence property; folding them corrupts a non-negotiable (Rule #2).
- **`kStreetType[Outdoor]` inversion as a major win** (E2) — near-moot; our corpus is already trail-first with roadlike de-ranked.
- **CoMaps' internal-FeatureIndex description keying** (E5) — we must key on stable `sr_uid`; CoMaps re-bakes wholesale instead.
- **`foot_access` enum retiring the curator name-regex** (A1) — the name-heuristic exists *because* access tags are absent for tracks; keep it.

---

## 4. Deprecation ledger — what this program retires

| Retired / demoted | Location | Replaced by | Wave | Caveat |
|---|---|---|---|---|
| Frontend `√(2·climb·miles)` as the **sole** difficulty axis | `frontend/src/data/summary.ts:94-117` | `path_grade` (technical) + `psurface`; the estimate survives as the *effort* sub-axis | A1/D1 | Keep the estimate; only its monopoly ends |
| Dead `normalize_surface`/`normalize_allowed_use` vocab | `ingestion/transform.py:44-66` | Richer CoMaps surface word-lists | A1 | `transform.py` full-deadness unverified |
| Elevation-derived length as length source | (none exists — `t.length_mi` is null corpus-wide) | Authoritative agency `GIS_MILES`/NPS length + `length_source` | A2 | The "3DEP length" it claimed to replace **does not exist** |
| NPS MultiLineString explosion (N fragments, geometry overwrite) | `ingestion/fetch/nps.py:86-92` | NPS re-assembly mirroring `usfs_convert.py:70-116` | A2 | Harm is geometry-overwrite + candidate inflation, not dup SourceRecords |
| Dead `hygiene.py` validity checks (test-only) | `ingestion/hygiene.py:15-47` | Wired into load path (geometry/null-island half only) | A3 | Provenance half depends on **CDP-03** |
| Hardcoded incident-tuned denylists in code | `ingestion/trail_filter.py:52-93` | `regions/exclusions.json` (migration + pinning tests) | A3 | Regexes are **live at fetch**, not dormant |
| Two-state `Meta.schema_version` (`0.1.0`/`0.2.0` forever) | `graph/schema.cypher:22-24`; `/health` `api/app.py:345` | Integer `schema_format` (startup-validated) + migration ledger | A4/B2 | Startup check must degrade-and-disclose, not crash |
| Content-free perpetual-null manifest vintages | `regions/usfs_manifest.json`, `regions/dem_manifest.json` | Populated `{osm_date, usfs_vintage, dem_sha, code_sha}` composite build-ID | A4 | Null was *honest*; gap is populate+propagate, not a fabrication bug |
| Dead-computed Duration silently dropped | `httpPlanner.ts:136-146`, `vm.ts:88` vs. `api/app.py:649` | Wired-through number + render-layer estimate disclosure | A5 | Disclosure must be **built**; it doesn't exist at render today |
| `ADVENTURE_PRUNE_MIN_RATIO` as the **only** multi-trail defense | `graph/load.py:48-67` | One row in a leveled per-class abs+rel matrix (keeps ratio as coarse floor) | B1 | Keep `verify_before_prune`'s raising ABORT as backstop |
| Fetch-time DEM checksum-only verification | `scripts/fetch_dem.py:135-160` | + NoData/hole assertion on clipped raster | E4 | Low urgency; the 0.8 prune gate already guards |
| **Not retired (kept):** Scout name-dedupe, `curator` roadlike name-regex, `trail_filter` hard-drop, `verify_before_prune` ABORT gate, the entire prune guard stack | `scout.py:60-89`; `curator.py:219-295`; `trail_filter.py:109`; `graph/load.py:385-517` | — | — | Verifiers explicitly **countermanded** the proposals that wanted these gone |

---

## 5. Unlock map — capabilities gained per wave

- **After Wave A (Phase A):** a source-backed difficulty/surface/access triple on every trail (populated where tags exist, silent elsewhere); authoritative agency length even with zero DEM coverage; null-island/invalid-geometry actually rejected; per-region exclusions tunable without a code change; a meaningful `/health` schema+staleness signal; Duration renders on Detail with an honest estimate qualifier. → *Substrate is honest enough to build the Phase-D verdict surface on.*
- **After Wave B (Phase A/B):** class-specific ingest collapses (a source vanishing, a `way_type` over-dropping, elevation halving) are caught before the prune; a human-readable regression report per re-ingest; a persisted facet baseline that F1/B1 both key off; content-hash corruption detection + a migration ledger that makes Aura-vs-local drift visible. → *The ingest is defensible enough to run repeatedly at CI gate quality (Phase-B Epic 009).*
- **After Wave C (Phase C):** noisy Garmin/Strava GPX cleans into candidate tracks — the `been_on` producer that unblocks Epic 006 novelty and the Stage-7 memory eval. → *Personalization has real user history to learn from.*
- **After Wave D (Phase D):** the dead `intent.filters.difficulty` becomes a real terrain screen + a two-axis Detail badge; an honest per-segment Tobler ETA (personalized only for logged-in viewers, as an effort *floor*); a MARGINAL verdict for borderline seasonal closures instead of a false all-clear; GPX export makes a decided trip a carryable artifact (anonymous-friendly). → *The go/marginal/no-go verdict surface is real, and the on-trail moment has an answer.*
- **After Wave E (Phase E):** real `CanonicalTrail` identity for named through-trails (AT/Rivanna); local-first trail/place search with a coefficient-pinning regression gate; a backpacking-grade water/shelter/viewpoint layer (FarOut-parity provenance); non-tautological DEM coverage gates once regions carry real polygons; landmark descriptions as a derived overlay. → *Table-stakes reach: search, multi-day logistics, coherent long-trails feed route planning (B005).*
- **After Wave F (Phase E/F, post Open-Decision-#3):** a bad ingest can never corrupt what is served + instant rollback (F1); crash-resilient staged multi-region ingest (F2). → *Operational substrate for continental scale — but only once the DB-tier decision removes the Aura Free ceiling that currently makes both infeasible.*
- **Cross-cutting:** the native-iOS bet shrinks from "implied offline-maps rewrite" to "safety-watch surface + APNs," recorded as a stated posture and decided at Phase G — contingent on GPX export (D4) actually shipping.