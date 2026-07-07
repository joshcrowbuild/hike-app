# B001 — Trail-name search + geocoder seam: architecture decision

**Status:** research complete (spike) · makes **Epic 038** writable · **Date:** 2026-07-07
**Provenance:** OSS-sprint spike lane `photon-search`. This is the repo-resident distillation of that spike; the engine/frontend anchors below were re-verified against `main` on 2026-07-07.
**Verdict (one line):** **Do NOT self-host Photon.** B001 is two problems wearing one name — (A) *trail-name search over our curated corpus* is an **in-graph** job (Neo4j FULLTEXT + a ported CoMaps scorer, **zero new infra**), and (B) *place→coords geocoding* is a **thin swappable geocoder seam** whose self-hosted-Photon option is correctly **deferred to the B002 continental / R7 DB-tier decision (Open Decision #3)**. Hybrid, weighted heavily to in-graph.

---

## 1. B001 is two sub-problems, one epic

`docs/strategy/path-to-complete.md:221` scopes B001 as *"'dreaming from home' place-name search + geocoder seam … search is a finite tool curated **through** the engine, never an infinite-scroll raw list."* Decomposed:

- **Problem A — trail-name search over OUR corpus.** User types "Old Rag" / "Rivanna" → *our verified, engine-curated cards* for that named trail. Search over ~2204 `CanonicalTrail` names already in Neo4j (Aura). **Not geocoding** — the answer is a curated card set through Scout/Verifier/Curator, not a lat/lon.
- **Problem B — place→coords geocoding.** User types "Charlottesville" → we need a lat/lon to feed the *existing* origin-based `/plan`. Classic forward geocoding — what Photon/Nominatim exist for.

Photon addresses only **B**, and even there it's the heavy-infra option. It does **nothing** for **A** (Photon indexes raw OSM places, not our enriched/conflated `CanonicalTrail` corpus with `length_source`, `path_grade`, corroboration).

## 2. Stale-doc correction (do not re-solve a solved problem)
`path-to-complete.md:221` says origins are *"3 hardcoded towns today, `frontend/src/data/origins.ts`."* **That file does not exist** (verified). Origins are **config-driven**: `GET /regions` (`api/app.py:522`) sources them from `regions/*.geojson` `properties.origins`, consumed via `frontend/src/data/regionsCatalog.ts` `useOrigins()`, and a **"near me" geolocation path already exists** (`orderOrigins()` re-sorts nearest-first from `tuning.originCoords`). **The real gap is arbitrary place names beyond the curated set** — not un-hardcoding. Epic 038's build lane corrects this line.

## 3. Integration seam (verified against `main`, 2026-07-07)
- **Search box lands on Home.** `frontend/src/screens/Home.tsx` — `useOrigins()` (`:90`) + `contextSentence()` (`:57`) is where a search box wires in.
- **Origin coords already plumbed.** `frontend/src/types.ts:63` `originCoords?: Coords` carries arbitrary coords for planning independent of the named-origin `OriginKey` — **a geocoded place flows through this exact field**. `regionsCatalog.ts` `orderOrigins()` (`:119`) already re-sorts nearest-first from a live fix, so a geolocation origin path exists.
- **Engine takes an origin; search feeds it.** `api/schemas.py:21` `PlanRequest{query, lat, lon}`; `/plan` (`api/app.py:544`) → `orchestration/engine.py:468` `plan(query, origin, runtime, …)` → `:258` `plan_from_origin` → `orchestration/scout.py:92` `scout()`. Scout is **spatial-nearest only** (`graph/queries.py:66` `candidate_trails_near`, POINT-index). **There is no name-search retrieval path today** — the hole Problem A fills.
- **Retrieval substrate half-exists.** `graph/schema.cypher:46` `TEXT INDEX trail_name` / `:47 area_name` — indexes names but only exact/`CONTAINS` (no fuzzy, no relevance). Problem A wants a **FULLTEXT** index (Lucene: fuzzy `~`, token analysis) + a scorer — a **one-line DDL + a query** on infra (Aura) already running. `scout._norm_name`/`_dedupe_by_name` (`:60`/`:78`) already collapse same-name segments to one card.
- **Geocoder-seam precedent.** `orchestration/adapters/registry.py` (kind-keyed, config-driven) + `valhalla.py` — a hosted service behind a thin swappable adapter, **already deployed** for drive-time. Problem B mirrors this.

## 4. Photon: architecture, cost, license
- **What it is.** komoot's OSS forward/reverse geocoder for OSM. Backend = **OpenSearch 3.x** (legacy ES 5.6 unmaintained), **Java 21+**. Imports from a Nominatim PostgreSQL DB or a prebuilt index; supports replication. Native search-as-you-type, typo tolerance, multilingual, bbox/tag filtering. ([github.com/komoot/photon](https://github.com/komoot/photon))
- **License — Apache-2.0** (code port-ok *with attribution*). Index data is **OSM = ODbL** (search box needs "© OpenStreetMap").
- **Self-host footprint (the disqualifier).** Worldwide index **72 GB compressed / 159 GB uncompressed**. Even a regional extract needs **OpenSearch (a JVM cluster) + Java 21 + a large persistent disk** — a whole dedicated always-on service. On our memory-limited Render footprint (Neo4j external on Aura), that is a heavyweight standing service for a product serving a handful of curated VA/NC regions. Disproportionate.
- **Public API is not a production dependency.** `photon.komoot.io` terms: *"extensive usage will be throttled or completely banned."* No commercial SLA. Fine for a spike, unfit as the shipped backend.

**Nominatim** (the geocoder alternative behind the seam): public API **forbids geocoding-primary apps** (must self-host); code license **GPLv2/v3 → pattern-only** (never copy); self-hosting is heavy (PostgreSQL + PostGIS + import). Data = ODbL.

## 5. The three architectures, scored

| | **Photon (self-host)** | **In-graph scorer** | **Hybrid (recommended)** |
|---|---|---|---|
| Solves A (trail-name search) | ❌ indexes raw OSM, not our corpus | ✅ native | ✅ |
| Solves B (place→coords) | ✅ | ❌ | ✅ (thin seam) |
| New standing infra | **OpenSearch + JVM + 100s GB** | **none** (Aura runs) | none now (seam swappable later) |
| Fits "curated through the engine" | ❌ raw list | ✅ through Verifier/Curator | ✅ |
| Effort | L+ (a whole service) | M | M (A) + S (B seam) |
| License risk | Apache ok, infra cost | none new | none new |

**Winner: Hybrid, weighted to in-graph.** Problem A → in-graph (Neo4j FULLTEXT + ported CoMaps scorer, fed through the engine so results are verified curated cards). Problem B → a thin geocoder seam (mirrors `valhalla.py`); near-term keep config-driven curated origins + browser "near me"; when arbitrary place search is truly needed, drop a hosted geocoder behind the seam. **Self-hosted Photon/Nominatim deferred to B002 / Open Decision #3** — it earns its keep only at continental coverage, a separate unmade call.

## 6. CoMaps scorer borrow (Problem A's relevance engine)
Reuses `docs/research/comaps-borrow-plan.md:214-217` (E2, DEFER-tagged, pattern verified):
- **Borrow (pattern-and-re-derive, do NOT clone):** `libs/search/ranking_utils.hpp:219-361` (`GetNameScores` — Levenshtein-DFA + offset-sliding, **6-level match ladder**); `libs/search/ranking_info.cpp:347-411` (single-scalar **linear** model); `ranking_info.cpp:34` + `real_mwm_tests.cpp:697` (`static_assert` coefficient wall + `Famous_Cities_Rank` golden test — the **regression-gate pattern** to replicate).
- **License:** CoMaps / Organic Maps lineage = **Apache-2.0 → port-ok** (pure scoring logic; port with an attribution header into `orchestration/search_score.py`).
- **Two verifier corrections baked into the epic:**
  1. **`GetNameScores` is a *scorer over already-retrieved candidates*, not a retriever.** CoMaps feeds it from an offline inverted `.mwm` index **we lack**. We build the candidate feed as a Neo4j **FULLTEXT** query (brute-force over ~2204 trails is trivially fine). **Port the scorer, build the feed.**
  2. **Relevance ≠ confidence (Rule #2, non-negotiable).** The name-match score is **relevance/ranking**; it must stay **strictly separate** from `freshness·authority·corroboration`. Folding a match score into confidence corrupts a non-negotiable. The scorer orders results; it **never** touches the confidence axis. Epic 038 enforces this with a **static import guard** (`search_score.py` ⟂ `orchestration/confidence.py`).

## 7. Risks / open questions
- **Aura FULLTEXT verification:** Lucene FULLTEXT is Aura-supported; confirm analyzer choice + that `~` fuzzy latency over ~2204 nodes is trivial before committing the DDL.
- **"Finite tool" tension:** the search endpoint must **cap + curate** — do not let FULLTEXT become an infinite raw list (`path-to-complete.md:221` explicitly refuses).
- **Geocoder provider choice (Problem B)** is deferred but should be scoped when B001 is scheduled: hosted commercial (paid, SLA) vs. self-host-later. Must not block the in-graph half.
- **Do not clone/stand up Photon** for this epic — the reading above is sufficient; the decision is "don't self-host now."

---
*This brief is the SSOT for **Epic 038 — Trail-name search + geocoder seam (B001)**. Source spike: OSS-sprint lane `photon-search`.*
