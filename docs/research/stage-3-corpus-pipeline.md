# Stage 3 — Corpus Pipeline (design)

*Workplan Stage 3. Draft v0.1 — June 19, 2026. Builds on `stage-1-data-sources.md` (the sources) and `stage-2-schema.md` (the target graph).*

> **STATUS: IMPLEMENTED by Epic 012 (CorpusSource seam) — the corpus pipeline shipped; the Shenandoah + GW&Jefferson pilot was ingested.** *(Design narrative below kept as spec provenance; "DESIGN / first build-mode task" framing is historical.)* This specifies *how* raw sources become the indexed graph — the architecture, the transform/hygiene rules, the conflation step, and the refresh/idempotency model. Actually *running* it against the pilot region is the first build-mode task; design decisions marked 🅓 are flagged for review (§10).

> **What this produces (per workplan):** the ingestion architecture (bulk-load → transform → validate/hygiene → conflate → dedup → load) · refresh cadence + idempotency · geographic scoping + expansion · (then) the first real East-Coast regional corpus. **Honors:** Rule #3 (slow data only), the §6 thin-v0 discipline, T6 (license obligations), T3 (the forked commons write).

---

## 1. Architecture — a versioned, idempotent DAG

Batch ingestion = **ordinary scheduled jobs, not MCP** (Decision Log §8). The pipeline is a directed acyclic graph of stages; each is independently runnable, logs to a run manifest, and is keyed so re-runs are idempotent.

```
                 ┌──────────┐   per source
  region.geojson │ ACQUIRE  │   (Geofabrik VA, USFS EDW, NPS GIS, USGS NTD,
   (boundary) ──▶│          │    3DEP, PAD-US, RIDB, VA/Fairfax)
                 └────┬─────┘
                      ▼
                 ┌──────────┐   clip to region+buffer; OSM→hiking filter;
                 │ EXTRACT  │   one normalized record set per source
                 └────┬─────┘
                      ▼
                 ┌──────────┐   units, names, attribute→canonical mapping
                 │TRANSFORM │   (raw values preserved on the SourceRecord)
                 └────┬─────┘
                      ▼
                 ┌──────────┐   drop malformed · flag incomplete ·
                 │ HYGIENE  │   geometry validity · provenance integrity
                 └────┬─────┘
                      ▼
                 ┌──────────┐   OSM = spine; match USFS/NPS on name+ref+geom
                 │ CONFLATE │   (OSM Merge); score → auto-accept / review queue
                 └────┬─────┘
                      ▼
                 ┌──────────┐   within-source + cross-source dedup;
                 │  DEDUP   │   resolve to canonical entities
                 └────┬─────┘
                      ▼
                 ┌──────────┐   build :SourceRecord → :CanonicalTrail + SAME_AS
                 │   LOAD   │   + Segments/Junctions/Trailheads; enrich (3DEP,
                 └────┬─────┘   PAD-US manager, RIDB permits); compute best-view
                      ▼
                 ┌──────────┐   constraints, point index;
                 │  INDEX   │   + fork de-identified commons write (T3 stub)
                 └──────────┘
```

**Stack (recommended):** **Python** — the geospatial ecosystem (Shapely/GeoPandas/GDAL/`osmium`/`rasterio`) plus **OSM Merge** (Python) plus `pyproj`/`thefuzz` are all here, and the watch libs (Phase 1) are Python too. 🅓 *This effectively makes Python the ingestion language (a Stage-0 placeholder) — confirm. The orchestration engine (Stage 4) could be a separate language, but Python there too keeps it one toolchain.* Geometry compute is in-process (no PostGIS, per Stage 2 decision 2); the Neo4j Python driver does the load.

**Run manifest (idempotency + provenance of the pipeline itself):** every run writes `{run_id, region, ingest_version:"2026-06", source_versions:{osm:"<geofabrik-date>", padus:"4.1", …}, counts, review_queue_size, started/finished}`. The graph's `ingest_version` ties back to this.

---

## 2. Geographic scoping & expansion

**Region = a boundary polygon**, everything clips to it. For the pilot: the union of **Shenandoah NP** (NPS boundary) + **GW & Jefferson NF** (PAD-US/USFS boundary), buffered ~2 km so trails crossing the edge aren't truncated. Stored as `regions/shenandoah-gwj.geojson`.

- **Why polygon, not bbox:** parks/forests are irregular; a bbox pulls in unrelated urban/private trails and bloats conflation. PAD-US gives clean manager boundaries for free (Stage 1 §3.1).
- **Clip discipline:** OSM extract (`osmium extract --polygon`), and every other source filtered by spatial intersect with the region. A trail partly outside is **kept whole** but tagged `extends_beyond_region` (don't chop geometry mid-trail).
- **Expansion strategy:** widening = add another polygon and re-run for that region; regions are independent units (a `region` property on every node) so runs never interfere. National coverage = many regional runs, not one giant job — keeps per-run compute and review bounded (§22 "per-session compute stays bounded" applied to ingestion). 🅓 *region granularity — per-park-unit vs. per-state vs. per-metro? Recommend per-coherent-recreation-area for the pilot, revisit at scale.*

---

## 3. Transform / normalization rules

Map each source's raw schema to the canonical attribute set **while preserving raw values on the `:SourceRecord`** (Stage 2 decision 3a — best-view computed at LOAD, not here).

- **Names → canonical form for *matching* (keep the display name raw):** lowercase; strip/normalize "Trail/Tr/Trl", "Road/Rd/FR/FS"; expand known abbreviations; collapse punctuation/whitespace. This `name_norm` is what conflation blocks on; the original `raw_name` is preserved for display. (Mirrors what OSM Merge's `osmhighways.py` does — moves misfiled ref-as-name into `ref`.)
- **Units → SI/standard:** lengths to miles (display) + meters (compute); elevation meters; record the unit explicitly.
- **Attribute mapping (per source → canonical), e.g.:**
  | Canonical | OSM | USFS | NPS |
  |---|---|---|---|
  | `name` | `name` | `TRAIL_NAME` | `TRLNAME` |
  | `ref` | `ref`/`ref:usfs` | `TRAIL_NO` | — |
  | `allowed_use` | `access`,`bicycle`,`horse` | managed-use cols | `TRLUSE` |
  | `surface` | `surface` | surface attr | `TRLSURFACE` |
  | `source_pk` | element id | `TRAIL_CN` | `OBJECTID` |
- **Controlled vocabularies:** normalize `allowed_use`/`surface` to a fixed enum **but keep the raw string** — and **never reconcile conflicting `allowed_use` across sources** (Stage 1 rule: USFS↔OSM access definitions differ). Conflicts survive to the graph as separate SourceRecord facts.
- **Dog/leash:** **not extracted from OSM as truth** (Stage 1 §3.1) — only from agency/Area-level regulation. An OSM `dog=*` tag, if present, is stored as a low-authority SourceRecord fact, never the best-view winner.

---

## 4. Data-hygiene ruleset (the §17 contract)

Applied at HYGIENE; failures are logged to the run manifest, not silently dropped.

1. **Geometry validity:** must be non-empty, valid (GDAL `-makevalid`), in EPSG:4326, and intersect the region. Invalid → attempt repair, else **drop + log**.
2. **Completeness flags:** missing required field (no name *and* no ref → can't conflate by attribute, geometry-only) → **keep + flag** `attr_incomplete`. RIDB blank coords (a known Stage 1 issue) → flag, don't place spatially.
3. **Coordinate sanity:** within region bbox; reject null-island (0,0) and out-of-range.
4. **Provenance integrity (hard invariant):** every record entering LOAD must carry `(source, source_pk, fetched_at, ingest_version)`. No anonymous facts — this is what makes the whole graph source-or-silence-able.
5. **OSM-specific:** keep `informal=yes`/social trails but **flag** them (`informal`) so the Curator/guardrails can down-rank or warn, per the "lesser-traveled trails are first-class but unofficial≠safe" tension.
6. **Endpoint-trim for the commons (T3, privacy hygiene):** any forked commons observation has track endpoints trimmed at this stage — hygiene and privacy in one (Decision Log §12).

---

## 5. Conflation — operationalizing Stage 1 §7

The de-risked, human-in-the-loop step. **OSM is the geometry spine; USFS/NPS conflate onto it.**

1. **Block** candidate pairs by `name_norm` and `ref` (cheap, cuts the comparison space).
2. **Score** each candidate: weighted combine of name string-similarity (`thefuzz`, threshold ~80) + geometry overlap (buffer 10–25 m) + Hausdorff (Fréchet for loops) + bearing guard at junctions (reject side-trails). *(These are OSM Merge's constants — start there.)*
3. **Triage:** auto-accept high-confidence; **everything else → a review queue** (GeoJSON/OSM-XML with `fixme=`/`overlapping=yes`, reviewable in JOSM or a MapRoulette-style list). At pilot scale (dozens of named trails) review is hours.
4. **Persist as `SAME_AS` edges** with `match_method`, `match_score`, `matched_on`, `reviewed_by`, `reviewed_at` (Stage 2 §3). **The human decision is stored** so refreshes don't re-ask (§6).
5. **Tool:** evaluate **OSM Merge** directly first (it already targets OSM+USFS+NPS); fall back to a thin Shapely/GeoPandas script for control. 🅓 *adopt-OSM-Merge vs. thin-custom — recommend spike OSM Merge on the pilot, decide from the review burden it produces.*

**Cross-check, don't double-count:** USGS NTD re-hosts agency data (Stage 1 §3.1) — load it as corroboration/`SAME_AS` evidence, **not** an independent source, so corroboration counts aren't inflated.

---

## 6. Refresh cadence & idempotency

**Monthly refresh** (Decision Log §4), idempotent and reconciling:

- **Upsert key = `(source, source_pk)`.** A re-fetched record updates its `:SourceRecord` in place and bumps `ingest_version`.
- **Change detection:** diff new vs. prior `source_version`. **Adds** → new SourceRecords (re-conflate just these). **Changes** → update; **re-run conflation only if geometry moved materially** (else keep the stored human match — don't re-review accepted matches). **Deletes** (record absent in new version) → **tombstone** (`retired_at`, `retired_in_version`), don't hard-delete — preserves provenance/history and avoids thrashing the canonical layer on transient source hiccups. 🅓 *tombstone-then-purge window — recommend retire on absence, purge after N consecutive absent refreshes.*
- **Canonical recompute:** best-view attributes recomputed on any contributing SourceRecord change; confidence is computed-on-read so nothing to recompute there.
- **Live keys refreshed too:** re-resolve `nws_grid_ref`/`usgs_site_id` only if a trailhead moves.

---

## 7. Enrichment at LOAD (joins onto the canonical graph)

After conflation, enrich the canonical nodes:
- **Elevation (3DEP):** densify each `:Segment` line (~5–10 m), sample the 3DEP COG (1 m where available else 1/3 arc-sec), smooth, sum positive deltas → `gain_m`, `grade_max`; **record the DEM resolution used** (a confidence/freshness input).
- **Land manager (PAD-US):** spatial-join each `:Area`/trail to PAD-US → `manager`, `pub_access` (policy-level), designation.
- **Permits (RIDB):** join `:Area` → RIDB RecArea/Facility → `permit_required` (inferred), `ridb_facility_id`, `ridb_permit_id` (for live availability later).
- **Live resolution keys:** nearest NWS grid, nearest USGS gauge (+distance), AirNow distance — stored, not the readings (Rule #3).

---

## 8. Testing & data-quality (the §17 gates, runnable in CI)

- **Unit:** extractors (OSM filter, RIDB parser), normalizers (name canonicalization, unit conversion), conflation scorers/mergers.
- **Data-quality checks (on every run):** geometry validity rate, % records with provenance, conflation precision on a small **golden match set** (hand-labeled pilot pairs), dedup correctness, schema validation on load. Thresholds fail the run.
- **Privacy/security test (T3, even pre-persons):** the forked commons write **never retains a person link** and endpoint-trimming **actually fires** — assert structurally now so it can't regress when persons arrive.
- **Idempotency test:** running the same input twice yields an identical graph (no duplicate SourceRecords/edges).

---

## 9. What runs where
Local for v0 (Decision Log §8): a scheduled job (cron/Makefile target) on Josh's machine → local Neo4j. No always-on host needed (ingestion is async + idempotent; backfills whenever it runs). The monorepo home is `ingestion/` with `regions/*.geojson`, `ingestion/sources/*` adapters, `ingestion/pipeline/*` stages, `ingestion/conflate/*`. Build/test commands land in Stage 0's TBD slots.

---

## 10. Open decisions (🅓 for review)
1. **Ingestion language = Python?** (strong fallout from the geospatial + OSM Merge ecosystem). *Recommend yes.*
2. **Region granularity** for scoping/expansion (per-rec-area vs. per-state). *Recommend per-rec-area for pilot.*
3. **Conflation tool:** adopt OSM Merge vs. thin custom Shapely script. *Recommend spike OSM Merge first, decide on review burden.*
4. **Delete handling:** tombstone-then-purge window (how many absent refreshes before purge). *Recommend retire-on-absence, purge after N.*
5. **Review UX for the conflation queue:** JOSM vs. a lightweight custom review list. *Defer until the spike shows the volume.*

## 11. Deferred
- Conflation match-score *thresholds* tuned on real pilot data (this is the empirical part of the Stage-1 spike, done during the first real run).
- Commons aggregation (k-value, capability bands) — Stage 9; here only the de-identified forked write + endpoint-trim.
- Multi-region orchestration/scheduling at scale — when we leave the pilot.

## 12. Next
On sign-off, the bridge to build is: wire `ingestion/` to pull the pilot region, run the pipeline against **Shenandoah + GWJ**, and produce the **first real regional corpus** in local Neo4j — the artifact that makes Stage 4 (engine) runnable against real data, and where the conflation thresholds get their empirical tuning.
