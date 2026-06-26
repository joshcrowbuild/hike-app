# Epic 017 — Terrain elevation enrichment (USGS 3DEP profiles)

**Status:** DEFINED
**Phase:** 1 (pulled forward — the backend prerequisite for Epic 016 Maps)
**Spec refs:** `stage-1-data-sources` (USGS 3DEP = elevation/grade) · `stage-3-corpus-pipeline` §7 (enrichment joins — the "second kind" of source) · Epic 012 (CorpusSource seam, which this extends) · **Epic 016** (the consumer: the elevation profile chart) · CLAUDE.md Rule #1 (source-or-silence) · Rule #3 (graph holds slow/structural data) · Rule #7 (provenance + timestamp)

> **Built in parallel with Epic 016.** This epic *produces* elevation data; Epic 016 *consumes* it. The only thing coupling them is a small API contract (S0) — freeze it first and the two builds run concurrently. See **Parallelization** at the bottom.

---

## Capability statement
Every trail in the corpus carries a precomputed **elevation profile** — height sampled along its real route, plus total gain/loss and max grade — so the app can show the *shape of the climb* (Epic 016) and any later feature (readiness, grade-aware ranking) can read real terrain difficulty without a live call. Unblocks the elevation half of Epic 016.

## Architectural context

**Builds on:**
- **The route geometry already in the graph** (`CanonicalTrail.geom_wkt`) — the line we sample along.
- **The CorpusSource seam (Epic 012).** This epic adds the **enrichment** kind of source — the "second kind" that Stage 3 §7 called for but that was never built (spine + conflate exist; enrichment does not).
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

**S1 — Enrichment-adapter seam**
**Given** the corpus pipeline (Epic 012 spine/conflate) runs before load
**When** enrichment is added
**Then** an enrichment kind of source runs after conflation, generically.
**AC-1.1:** An `EnrichmentSource` protocol (`enrich(...) -> properties`) + registry under `ingestion/sources/` (the Stage 3 §7 "second kind"), iterated after conflation, separate from spine/conflate.
**AC-1.2:** Enrichment failure for one source degrades to "no enrichment" for that property (degrade-and-disclose), never aborts the run.
**AC-1.3:** Covered by a test with a fake enrichment source (mirrors Epic 012's seam tests).

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
**AC-3.1:** `elevationProfile` (samples + totalGain/Loss + maxGrade + source + resolution + version) is stored on `CanonicalTrail` as a property (no PostGIS — consistent with the schema note).
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
- **Lane A — this epic (backend/data):** S0 first, then S1 → S2 → S3 → S4.
- **Lane B — Epic 016 (frontend + geometry API):** Epic 016 S1 (expose geometry) + S2–S4 (topo map, route, trailhead, card glyph) + S6 — all buildable against the mock (including S0's mock profile), with **no dependency on Lane A**.
- **Join:** Epic 016 **S5b** (the chart consuming the *real* `elevationProfile`) needs both lanes complete. Everything up to the join runs concurrently.
- **Only S0 (the contract) must land before the lanes split** — do it first, together. After that, two builders work without blocking each other.
