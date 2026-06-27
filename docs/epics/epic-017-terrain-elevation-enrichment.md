# Epic 017 — Terrain elevation enrichment (USGS 3DEP profiles)

**Status:** IN_PROGRESS
**Owner:** Lane A (backend) — started 2026-06-26
**Phase:** 1 (pulled forward — the backend prerequisite for Epic 016 Maps)
**Spec refs:** `stage-1-data-sources` (USGS 3DEP = elevation/grade) · `stage-3-corpus-pipeline` §7 (enrichment joins — the "second kind" of source) · Epic 012 (CorpusSource seam, which this extends) · **Epic 016** (the consumer: the elevation profile chart) · CLAUDE.md Rule #1 (source-or-silence) · Rule #3 (graph holds slow/structural data) · Rule #7 (provenance + timestamp)

> **Built in parallel with Epic 016.** This epic *produces* elevation data; Epic 016 *consumes* it. The only thing coupling them is a small API contract (S0) — freeze it first and the two builds run concurrently. See **Parallelization** at the bottom.

> **✅ Contract FROZEN (Lane A, 2026-06-26).** Both coupling shapes — the assembled `geometry` (Epic 016 S1) and `elevationProfile` (S0 below) — are implemented in `api/schemas.py` (`TripDetailResponse` · `GeoJsonGeometry` · `ElevationProfile`) and served by `GET /trail/{canonical_id}`. Lane B mirrors these as the frontend trip type + realistic mock; the two lanes no longer block each other. Backend production (016 S1 route assembly + 017 S1–S4 loader/3DEP/store/expose) has landed; the elevation profile is precomputed at ingest by the `usgs-3dep` enrichment source (off by default — needs `ADVENTURE_3DEP_DEM`).

---

## Capability statement
Every trail in the corpus carries a precomputed **elevation profile** — height sampled along its real route, plus total gain/loss and max grade — so the app can show the *shape of the climb* (Epic 016) and any later feature (readiness, grade-aware ranking) can read real terrain difficulty without a live call. Unblocks the elevation half of Epic 016.

## Architectural context

> **⚠️ Review corrections (2026-06-26) — two scope-changing facts:**
> 1. **The enrichment seam already exists and is wired.** Epic 012 built `kind = enrichment` + `EnrichmentFact` (`ingestion/sources/base.py`), and `ingestion/pipeline.py` already runs the post-conflation join (`_run_enrichment`, called in both dry-run + live paths). **Do NOT rebuild the seam.** The genuinely missing piece is the **enrichment loader** — pipeline.py says verbatim *"No graph write yet — a real enrichment loader lands with the first enrichment source."* So `_run_enrichment` collects facts but nothing persists them. **S1 is rescoped to: build the enrichment loader (the deferred graph write) + the 3DEP source — using the existing seam.**
> 2. **Geometry is per-Segment, not per-Trail.** Sample along **`Segment.geom_wkt`** assembled across `(:CanonicalTrail)-[:HAS_SEGMENT]->(:Segment)` (ordered via junctions) — there is no `CanonicalTrail.geom_wkt`. Ideally consume the *same assembled route* Epic 016 S1 precomputes, so geometry is assembled once.

**Builds on:**
- **The route geometry already in the graph** — as **`Segment.geom_wkt`** lines assembled per trail (see correction 2); ideally the same precomputed route as Epic 016 S1.
- **The CorpusSource enrichment seam (Epic 012) — already built and wired** (see correction 1). This epic supplies the first enrichment **source** (3DEP) and the **loader** that persists its facts; it does not rebuild the seam.
- **The batch-ingestion posture** (CLAUDE.md: "batch ingestion = scheduled jobs"; monthly refresh). Elevation is **precomputed at ingest**, not fetched per request — it is slow/structural data (Rule #3), so it lives in the graph, not in a JIT live call.

**Enables:**
- **Epic 016 S5** (the elevation profile chart + map↔profile sync) — the direct consumer.
- Future grade-aware ranking and the readiness filter (Epic 007) reading real climb difficulty.

**Does NOT include:**
- The map UI or the profile chart (Epic 016).
- Any live, per-request elevation call (precomputed only).
- Other enrichment sources (PAD-US land-manager, RIDB permits) — the seam is built generically here, but only the **3DEP** adapter is implemented; others are follow-ons.

## The shared contract — what makes the two epics parallel

The single integration point between this epic (producer) and Epic 016 (consumer) is the **elevation-profile shape on the trip/detail API response**. Freeze it first; then backend produces real data and frontend mocks it until ready, meeting at the contract. Proposed shape (ratify in S0):

```
elevationProfile: {
  samples: [{ distanceMeters, elevationMeters }],   // ordered start → end
  totalGainMeters,
  totalLossMeters,
  maxGradePercent,
  source: "usgs-3dep",
  resolutionMeters                                  // sampling spacing
} | null    // null = no coverage; never fabricated (Rule #1)
```

## Design decisions

**D1 — Sample locally from 3DEP DEM rasters, not per-point web queries.** Download the USGS 3DEP DEM for a region once (1/3 arc-second ≈ 10 m seamless layer), then sample elevation along each trail's geometry in-process (rasterio/GDAL). Thousands of points × many trails would hammer a point-query API; a local raster is fast, idempotent, offline, and fits the monthly batch. *Fallback for tiny/dev regions:* the National Map EPQS point query.

**D2 — Sample at a fixed spatial resolution** (densify `geom_wkt` to ~10–25 m spacing — ratify in S0). Store the samples + derived gain/loss/grade as properties on the trail. **Apply light smoothing** so 10 m-DEM noise doesn't inflate "total gain" (a well-known DEM artifact); document the method.

**D3 — Source-or-silence (Rule #1):** a trail outside DEM coverage, or with missing geometry, gets `elevationProfile: null` — never an interpolated or faked curve. Partial coverage → a profile over the covered span with a disclosed gap, or `null` if too sparse (ratify the threshold).

**D4 — Idempotent + versioned (Rule #7):** re-running enrichment for a region recomputes deterministically; a `dem_version`/`ingest_version` records provenance so staleness is visible.

## Stories

**S0 — Freeze the elevation-profile contract (this unblocks the parallel build)**
**Given** Epic 016 needs to consume elevation and this epic produces it
**When** the contract is ratified
**Then** both epics build against a frozen shape.
**AC-0.1:** The `elevationProfile` shape (above) is documented in the API contract **and** the frontend trip type, including `null` semantics.
**AC-0.2:** The **mock** data source returns a realistic sample `elevationProfile`, so Epic 016's chart builds before any real data exists.
**AC-0.3:** This shape is the **only** coupling between the two epics (no other shared types).

**S1 — Enrichment loader (the deferred graph write) — using the existing seam**
**Given** the seam + `_run_enrichment` join already exist (Epic 012) but collect `EnrichmentFact`s with **no graph write yet**
**When** the first enrichment source is added
**Then** its facts are persisted to the graph through a real loader.
**AC-1.1:** An enrichment **loader** writes the `EnrichmentFact`s returned by `_run_enrichment` onto the target nodes (idempotent), closing the explicit "no graph write yet" gap in `ingestion/pipeline.py`. **The seam/protocol is NOT rebuilt — reuse `CorpusSource`/`EnrichmentFact`.**
**AC-1.2:** A failing enrichment source degrades to "no fact" for that property (degrade-and-disclose), never aborts the run (the existing join already isolates this — assert it).
**AC-1.3:** Covered by a test with a fake enrichment source whose facts round-trip to the graph and back.

**S2 — USGS 3DEP elevation adapter**
**Given** a region + trail geometries
**When** the 3DEP adapter runs
**Then** it samples elevation along each trail from the local DEM.
**AC-2.1:** Resolves + caches the 3DEP DEM for a region (D1); a small dev region is covered by a **fixture DEM** so tests don't hit the network.
**AC-2.2:** Given a `geom_wkt` line, returns ordered `(distance, elevation)` samples at the configured resolution (D2).
**AC-2.3:** Geometry outside coverage / missing → returns no profile (drives D3's `null`), with a logged, disclosed reason.

**S3 — Compute + store the profile**
**Given** sampled elevations
**When** enrichment loads
**Then** the trail carries the profile + derived metrics.
**AC-3.1:** `elevationProfile` is stored on `CanonicalTrail` (the assembled-route owner). **Encoding note:** Neo4j has no list-of-maps property type, so persist the samples as **two parallel primitive arrays** (`profile_distances_m: [float]`, `profile_elevations_m: [float]`) plus scalars (`total_gain_m`, `total_loss_m`, `max_grade_pct`, `elev_source`, `elev_resolution_m`, `elev_version`) — *or* a single JSON-string property; pick one in S0 and keep it consistent with the API serializer. (No PostGIS — consistent with the schema note.)
**AC-3.2:** Gain/loss use the documented smoothing (D2); a test asserts a known synthetic hill returns the expected gain within tolerance.
**AC-3.3:** Re-running is idempotent (D4); the version property updates.

**S4 — Expose via the API (the contract join)**
**Given** a stored profile
**When** the app requests a trip's detail
**Then** the response carries `elevationProfile` per S0.
**AC-4.1:** The trip/detail endpoint returns `elevationProfile` in the frozen shape (or `null`).
**AC-4.2:** A trail with no stored profile returns `null` — not omitted, not faked.
**AC-4.3:** A contract test asserts the API shape matches the frontend type exactly (the join with Epic 016 S5b).

## Definition of Done
- [ ] S0–S4 ACs covered by passing tests; `make check` green (live-DB enrichment behind the `neo4j` marker per Epic 015's pattern; the rest DB-free).
- [ ] The contract (S0) is frozen and mirrored in the frontend type with a realistic mock — so Epic 016 builds in parallel without waiting.
- [ ] A real (or fixture) region produces stored profiles; a no-coverage trail correctly yields `null`.
- [ ] Source-or-silence verified — no fabricated curve anywhere.
- [ ] Provenance/version recorded; re-run is idempotent.

## Open questions
1. Sampling resolution + smoothing method (S0/D2) — pick defaults; cheap to tune later.
2. Partial-coverage threshold (D3) — when does a partial profile become `null`?
3. Dev-region DEM — bundle a small fixture DEM vs document a download step.
4. Does grade-aware ranking want this now, or just the chart? (Scopes whether per-segment grade is consumed beyond Epic 016.)

## Parallelization (with Epic 016)
The split is by **area (backend vs frontend)**, not strictly by epic — note that **Epic 016 S1 (assemble + expose route geometry) is backend** and belongs with Lane A.
- **Lane A — backend / data:** the contract first (017 S0 elevation shape **+** the geometry shape from 016 S1), then **016 S1** (assemble route from segments → expose) ‖ **017 S1→S4** (enrichment loader + 3DEP source + store + expose). All the real-data production.
- **Lane B — frontend UI (Epic 016 S2–S4, S6):** the topo map, route, trailhead, card glyph, layers/fullscreen — built **entirely against the mock** (sample geometry *and* sample `elevationProfile`), with **no dependency on Lane A**.
- **Join:** Epic 016 swaps mock→real geometry (S2) and renders the real elevation chart (**S5b**) once Lane A lands. Everything up to the join runs concurrently.
- **Freeze first, together:** the **two contract shapes** — assembled `geometry` (016 S1) + `elevationProfile` (017 S0) — plus realistic mocks for both. After that, the two lanes never block each other.
- **Note:** Lane B can render the *entire* maps-and-elevation experience on the mock **without Lane A** — so the feature is demoable on sample data early; Lane A is what makes it *true for real trails*.
