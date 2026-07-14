# Epic 038 — Trail-name search + geocoder seam (B001)

**Status:** IN_PROGRESS (S1 + S3's in-graph retrieval half shipped; S2/S4/S5/S6 not started — see build-lane note below)
**Phase:** E (Phase-E "dreaming from home" search; a build lane has picked up Problem A's in-graph retrieval — Problem B's geocoder seam and the frontend search box remain unscheduled)
**Spec refs:** research brief `docs/research/b001-search-geocoder.md` (this epic's SSOT) · `docs/strategy/path-to-complete.md:221` (B001 "search is a finite tool curated *through* the engine, never an infinite-scroll raw list") · `docs/research/comaps-borrow-plan.md:214-217` (E2 — CoMaps `GetNameScores` borrow + verifier corrections) · CLAUDE.md **Rule #1** (source-or-silence), **Rule #2** (confidence = freshness·authority·corroboration; relevance must never fold in), **Rule #4** (access control at the query/data layer) · Open Decision #3 (R7 Aura DB-tier / B002 continental)

---

## Capability statement
A user can type a **trail name** ("old rag", "rivanna") into the Home search box and get *our verified, engine-curated cards* for that named trail — fuzzy-matched, capped, and run through Scout/Verifier/Curator so results arrive as sourced cards, never a raw graph dump — **and** (behind a thin swappable seam) type an **arbitrary place name** and have it geocoded to coords that flow into the existing origin-based `/plan` path, without standing up any new heavyweight infrastructure.

## Architectural context

**Builds on (all anchors verified 2026-07-07 against `main`):**
- **The existing name-index substrate.** `graph/schema.cypher:46` `CREATE TEXT INDEX trail_name … FOR (t:CanonicalTrail) ON (t.name)` and `:47` `area_name`. A TEXT index already indexes names but serves only exact / `STARTS WITH` / `CONTAINS` / `ENDS WITH` — **no typo tolerance, no relevance rank**. This epic upgrades to a Lucene **FULLTEXT** index (Aura-supported, one-line DDL, **zero new infra**).
- **The spatial retrieval precedent.** `graph/queries.py:66` `candidate_trails_near(lat, lon, radius_m, k)` and `:97` `candidate_trails_near_direct(...)` — the shape the new name-retrieval query must mirror so Scout/Curator reuse holds (returns `canonical_id, name, point, trailhead_point, is_loop, length_mi, way_type, outside_boundary, trailhead_id, distance_m, area_id`). Access-control clause helper: `graph/queries.py:61` `owner_scope(var)`.
- **Scout's name-dedupe.** `orchestration/scout.py:60` `_norm_name` + `:78` `_dedupe_by_name` + `:92` `scout(lat, lon, session, *, radius_m, k)` — name-normalization and same-name segment collapse (D11) already exist; name-search results dedupe to one card per trail through this same path.
- **The engine entry points.** `orchestration/engine.py:468` `plan(query, origin=(lat,lon), runtime, *, k, viewer_id)` → `:258` `plan_from_origin(lat, lon, …)`. Search feeds the engine; it does not replace it.
- **The API request shape.** `api/schemas.py:21` `PlanRequest{ query:str, lat:float, lon:float, … }`; `/plan` at `api/app.py:544` already takes free-text `query` **plus** an origin lat/lon. `/regions` (origins source) at `api/app.py:522`.
- **The kind-keyed adapter registry** (the model for the geocoder seam). `orchestration/adapters/registry.py` (`enabled_adapters` `:53`, `probes_for` `:78`, config-driven `ADVENTURE_LIVE_ADAPTERS`), `orchestration/adapters/valhalla.py` (drive-time — a hosted service behind a thin swappable adapter, **already deployed**), `orchestration/adapters/base.py` (the `LiveAdapter` protocol).
- **The frontend origin seam.** `frontend/src/types.ts:63` `originCoords?: Coords` (`Coords` at `:43`) — tuning state already carries arbitrary coords for planning, independent of the named-origin `OriginKey` (`:8`). `frontend/src/data/regionsCatalog.ts` `useOrigins()` + `orderOrigins()` (`:119`, re-sorts nearest-first when a live fix exists) + `originCoordsMap()` (`:109`). `frontend/src/screens/Home.tsx` `useOrigins()` (`:90`) + `contextSentence()` (`:57`) — where a search box wires in.
- **The confidence property to keep search OUT of.** `orchestration/confidence.py` `compute(authority, freshness, corroboration)` (`:52`) + `for_fact()` (`:71`). Name-match relevance MUST NOT be imported into or fold into this module (Rule #2).

**Enables:** the Phase-E "find any trail (near me now / dreaming from home)" exit criterion (`path-to-complete.md:216`); unblocks B001 as a build lane; establishes the swappable geocoder seam that the B002 continental decision later slots a hosted/self-hosted provider into.

**Does NOT include (scope fence — binding):**
- **NO self-hosting Photon.** Photon's backend is OpenSearch 3.x (a JVM search cluster) + Java 21 + a **72 GB compressed / 159 GB uncompressed** worldwide index (or a large regional extract) — a whole dedicated always-on service, wildly disproportionate to a handful of curated VA/NC regions. Deferred to the **B002 continental / R7 Aura DB-tier decision (Open Decision #3)** — see S6.
- **NO self-hosting Nominatim** (PostgreSQL + PostGIS + import pipeline; GPLv3 code = **pattern-only**, never copied). Also deferred to B002.
- **NO product code changes to routing, conflation, or the confidence axis.** Search is name/place lookup; routing (CDP-20 topology-integrity gate) is separate substrate.
- **NO "un-hardcoding" of origins** — origins are **already** config-driven (see stale-doc correction below). This epic adds *arbitrary place names beyond the curated set*, not a re-solve of the solved problem.

**License / attribution (binding — LICENSE GATE):**
- **CoMaps / Organic Maps `GetNameScores` scorer — Apache-2.0 → PORT-OK.** The 6-level Levenshtein-DFA match ladder + linear scalar model (`libs/search/ranking_utils.hpp:219-361`, `libs/search/ranking_info.cpp:347-411`) is pure scoring logic; port it (re-derived in Python) into `orchestration/search_score.py` **with an attribution header** naming CoMaps/Organic Maps, Apache-2.0, and the upstream repo URL. Pattern reference lives in `docs/research/comaps-borrow-plan.md:214-217` (do NOT clone the CoMaps repo — source lines are cited there; the borrow is pattern-and-re-derive).
- **Photon — Apache-2.0** (code port-ok *with attribution* if any of its API contract is mirrored) — but we are **NOT porting Photon code** in this epic; only its public HTTP request/response **shape** informs the geocoder-seam interface (S5). If S5's default adapter targets a Photon-compatible endpoint, mirror the contract, don't copy code.
- **Nominatim — GPLv3 → PATTERN-ONLY** (read, learn, re-derive; never copy).
- **Index/geocode data is OSM → ODbL** (we already comply). Any search box surfacing OSM-derived place results MUST show "© OpenStreetMap" attribution.

---

## Stale-doc correction (binding — do not re-solve a solved problem)
`docs/strategy/path-to-complete.md:221` says *"origins are 3 hardcoded towns today, `frontend/src/data/origins.ts`."* **That file does not exist** (verified: `ls frontend/src/data/origins.ts` → no such file). Origins are now **config-driven**: served by `GET /regions` (`api/app.py:522`) from `regions/*.geojson` `properties.origins`, consumed via `frontend/src/data/regionsCatalog.ts` (`useOrigins()`), and a **"near me" geolocation path already exists** (`orderOrigins()` re-sorts nearest-first from `tuning.originCoords`). The real near-term gap is **arbitrary place names beyond the curated origin set** — not un-hardcoding. **AC-0.1 (documentation):** this epic's implementation PR (whenever the build lane runs) corrects `path-to-complete.md:221` to remove the stale `origins.ts` reference. *(In-scope for this spike: the correction is stated here and in the research brief; the source-doc edit is carried by the build lane so it lands with code.)*

---

## Stories

> **Spike-lane note.** This is a **spec-complete draft epic** (the deliverable that makes B001 writable). The stories/ACs below are the buildable spec; the actual product code is a **later Phase-E build lane**, not this PR. This PR delivers `docs/research/b001-search-geocoder.md` + this epic + the index row (docs only).

> **Build-lane update (this PR):** a build lane shipped S1's FULLTEXT retrieval substrate and S3's engine-through wiring for **trail-name search only** (Problem A): `graph/schema.cypher` `trail_name_fts`, `graph/queries.py:candidate_trails_by_name`, `orchestration/scout.py:scout_by_name`, `orchestration/engine.py:search_trails` (+ the behavior-preserving `_plan_from_candidates` extraction), and `POST /search` (`api/schemas.py:SearchRequest`, `api/app.py`). **S2 (the ported CoMaps `search_score.py` scorer) was deliberately NOT built this pass** — ranking uses the FULLTEXT relevance `score DESC` order directly (order-preserving through Scout/Verifier), satisfying Rule #2 (relevance never touches confidence) without yet porting the 6-level match ladder; a later pass can layer S2's scorer in without changing the `/search` contract. S4 (frontend search-as-you-type UI), S5 (geocoder seam / Problem B), and S6 are unstarted.

### S1 — FULLTEXT retrieval substrate (in-graph, zero new infra)

**Given** the corpus of ~2204 `CanonicalTrail` nodes with `name` already on Aura
**When** a name query arrives
**Then** a Lucene-backed FULLTEXT index serves fuzzy, token-analyzed, relevance-ordered candidate retrieval, scoped to the viewer.

**AC-1.1:** `graph/schema.cypher` adds `CREATE FULLTEXT INDEX trail_name_fts IF NOT EXISTS FOR (t:CanonicalTrail) ON EACH [t.name]` (and an `Area` equivalent if area search is in the build). The existing TEXT index `trail_name` (`schema.cypher:46`) is **kept** (still serves exact-match callers) — the FULLTEXT index is additive.
**AC-1.2:** `graph/queries.py` gains `candidate_trails_by_name(query: str, k: int) -> tuple[str, dict]` that calls `db.index.fulltext.queryNodes('trail_name_fts', $q)`, applies a `LIMIT`, and **returns rows in the exact column shape of `candidate_trails_near`** (`canonical_id, name, point, trailhead_point, is_loop, length_mi, way_type, outside_boundary, trailhead_id, distance_m, area_id`) so `scout._row_to_candidate` / `_dedupe_by_name` reuse holds with no downstream changes. (`distance_m` may be `null`/absent for a name hit — the shape is preserved, the ordering key is relevance not distance.)
**AC-1.3:** the query is a **scoped read** through the same `ScopedSession` path Scout uses; a test asserts the name-search path emits no ungranted nodes (Rule #4) — i.e. it runs through the access-scoped session wrapper and never a raw driver session.
**AC-1.4:** an integration test (`@pytest.mark.neo4j`, **local Neo4j only** — see DB-safety rule) loads ≥2 same-name-prefix trails and asserts `candidate_trails_by_name("old rag", 10)` fuzzy-matches "Old Rag Loop" (and a deliberately misspelled "old rga" still hits, proving fuzzy tolerance).
**AC-1.5:** the DDL is verified to build and query on the **live Aura tier** (Lucene FULLTEXT is Aura-supported) with acceptable latency over ~2204 nodes; the verification note (analyzer choice + observed latency) is recorded in the epic's Open Questions resolution or PR description.

### S2 — Port the CoMaps name scorer (relevance-only, confidence-isolated)

**Given** a set of already-retrieved name candidates from S1
**When** they are scored for name relevance
**Then** a ported CoMaps `GetNameScores` ladder orders them by match quality — and that score **never** touches the confidence axis.

**AC-2.1:** new pure module `orchestration/search_score.py` re-derives the CoMaps 6-level match ladder (full-match → prefix → substring → …) + Levenshtein distance, with an **Apache-2.0 attribution header** naming CoMaps/Organic Maps + upstream URL. No I/O, no graph, no network — pure functions over strings.
**AC-2.2:** a **golden regression test** (mirroring CoMaps' `Famous_Cities_Rank` pattern, `real_mwm_tests.cpp:697`) pins the rank order of a fixed set of trail-name inputs; changing a scorer coefficient trips the test. Include a coefficient tripwire (assert on the constant vector, mirroring the `static_assert` wall at `ranking_info.cpp:34`).
**AC-2.3 (invariant guard — binding, Rule #2):** a CI/lint test asserts **`orchestration/search_score.py` does not import from `orchestration.confidence`** and **`orchestration/confidence.py` does not import from `orchestration.search_score`** (static import-graph check via `ast`/module inspection). The name-match score is **relevance/ranking only**; it is structurally impossible for it to fold into `freshness·authority·corroboration`. A code comment in both modules states the invariant.
**AC-2.4:** the scorer's output orders search results and is used as a *ranking* input only; a test asserts it is **never** passed as an argument to `confidence.compute()` / `confidence.for_fact()` and never written to any `confidence`/`corroboration` field.

### S3 — Search endpoint through the engine (finite tool, curated cards)

**Given** a name query
**When** the search endpoint runs
**Then** results are retrieved (S1), scored (S2), then **run through Verifier/Curator** so they arrive as sourced curated cards — capped, never an infinite raw list.

**AC-3.1:** a search path (`GET /search?q=` or an extension of `/plan` with a name-search mode — the build lane picks one; the epic requires the results flow **through `engine.plan()`/`plan_from_origin` verification+curation**, not a direct graph dump).
**AC-3.2 (finite-tool invariant — binding, `path-to-complete.md:221`):** results are **hard-capped** (a `k`/`LIMIT` cap, no pagination-to-infinity); a test asserts the response length ≤ cap and that FULLTEXT cannot return an unbounded list. No infinite scroll.
**AC-3.3:** every returned card carries source + timestamp (source-or-silence, Rule #1) — results are engine-curated cards identical in shape to `/plan` cards, verified by live checks and deduped via `scout._dedupe_by_name`.
**AC-3.4:** an **empty or no-match query returns a sourced empty-state** ("no trail named X in our data; last ingested …"), never a blank or a fabricated result.

### S4 — Search-as-you-type UI (calm, degrades gracefully)

**Given** the Home screen
**When** a user types in the search box
**Then** a debounced type-ahead calls S3 and renders curated cards, degrading to the existing origin picker on failure.

**AC-4.1:** a debounced search box on `frontend/src/screens/Home.tsx` (wired near `useOrigins()` `:90` / `contextSentence()` `:57`), calling the S3 endpoint.
**AC-4.2:** on search error/outage the UI **degrades to the existing origin picker** (degrade-and-disclose) — never a dead-end.
**AC-4.3:** calm-utility invariants: no infinite scroll, reduced-motion honored, results capped visually to the S3 cap.

### S5 — Geocoder seam for arbitrary-place origins (Problem B, thin swappable adapter)

**Given** a user typing an arbitrary place name ("Charlottesville")
**When** it is geocoded
**Then** a thin swappable adapter (mirroring the LiveAdapter registry pattern) returns coords that flow into the **existing `tuning.originCoords` → `PlanRequest.lat/lon`** path.

**AC-5.1:** a geocoder seam mirroring `orchestration/adapters/registry.py` + `valhalla.py` — a `geocode(place) -> Coords | None` interface, config-selected provider, **swappable by config** (a test swaps a stub provider). No provider is hardcoded into call sites.
**AC-5.2:** a successful geocode result flows into the **existing `frontend/src/types.ts:63` `originCoords`** field → `PlanRequest.lat/lon` (`api/schemas.py:21`) — **no new plan plumbing**. Near-term default remains the curated `regions/*.geojson` origins + browser geolocation ("near me"); the geocoder is additive for arbitrary places.
**AC-5.3:** **degrade-and-disclose** on geocoder outage (Rule #6): geocode failure falls back to the curated origin picker with a disclosed reason, never a silent blank.
**AC-5.4:** if the default adapter targets an OSM-derived geocoder, "© OpenStreetMap" attribution is shown (ODbL). The adapter file carries the correct license header for whatever provider contract it mirrors (Photon-shape = Apache-2.0 attribution; no Nominatim/GPL code copied).

### S6 — Deferred marker (do-not-build fence for planet-scale)

**Given** the temptation to self-host Photon/Nominatim for continental coverage
**When** this epic is scoped
**Then** planet-scale geocoding is explicitly folded into **B002 / Open Decision #3 (R7 Aura DB-tier)** — not this epic.

**AC-6.1:** the epic (this file) and the research brief explicitly scope OUT self-hosted Photon/Nominatim continental coverage, naming B002 / Open Decision #3 as the owner of that call. **No infra for planet-scale search is stood up here.**
**AC-6.2:** the geocoder seam (S5) is designed so a self-hosted or hosted continental provider can drop in *later* behind the same interface, with no call-site changes — the deferral is a config swap, not a re-architecture.

---

## Cross-cutting requirements
- **Relevance ≠ confidence (Rule #2, non-negotiable):** enforced by AC-2.3's static import guard + AC-2.4's value-flow test. This is the single most load-bearing invariant of the epic.
- **Finite tool, not infinite list (`path-to-complete.md:221`):** enforced by AC-3.2's hard cap.
- **Access control at the query layer (Rule #4):** enforced by AC-1.3's scoped-session test.
- **Source-or-silence (Rule #1):** enforced by AC-3.3 / AC-3.4 (sourced cards, sourced empty-state).
- **Attribution:** CoMaps Apache-2.0 header (AC-2.1); OSM/ODbL on any surfaced place data (AC-5.4).

## Definition of Done (for the eventual build lane — NOT this spike PR)
- [ ] All ACs covered by at least one passing test
- [ ] `make check` green
- [ ] AC-2.3 import-guard test green (search_score ⟂ confidence)
- [ ] Aura FULLTEXT DDL verified live (AC-1.5)
- [ ] Targeted review agent run; CRITICALs fixed
- [ ] `path-to-complete.md:221` stale `origins.ts` reference corrected (AC-0.1)
- [ ] Committed and pushed

## Definition of Done (THIS spike PR — docs only)
- [x] `docs/research/b001-search-geocoder.md` written (the brief)
- [x] This epic authored with objectively-testable ACs + verified file:line anchors
- [x] `docs/epics/README.md` index row added
- [ ] `make check` green (docs-lint passes: links resolve, no stale markers)
- [ ] PR opened "Epic 038: … — FOR REVIEW"

---

## Open questions / risks
1. **Aura FULLTEXT analyzer + latency (S1):** confirm the analyzer choice (`standard` vs `standard-folding` for accent/case) and that `~` fuzzy latency over ~2204 nodes is trivial at query time on the live Aura tier before committing the DDL. Expected trivial; verify (AC-1.5).
2. **`/search` vs extend `/plan` (S3):** the build lane picks the surface; the binding requirement is results flow through the engine (verify+curate), not the endpoint name.
3. **Geocoder provider choice (S5):** deferred but should be scoped when B001 is scheduled — hosted commercial (paid, SLA) vs. self-host-later. Must not block the in-graph half (Problem A ships without a geocoder).
4. **Area search (S1):** whether to also FULLTEXT-index `Area.name` (park/forest names) is a build-lane call; the epic allows it but does not require it.
5. **Status semantics:** this is a spec-complete **draft** epic (DEFINED-level detail, Phase-E deferred build). It is not IN_PROGRESS and authorizes no product code; the build lane flips it to IN_PROGRESS when scheduled.
