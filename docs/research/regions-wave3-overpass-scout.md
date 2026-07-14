# Expansion Wave 3 — Overpass Forward Scout (Real Inventory)

**Status:** ACTIVE (foreign-model research; ready for PO review)
**Reviewer:** GLM
**Date:** 2026-07-13
**Scope:** Actual Overpass trail inventory for all 9 Wave-3 candidate regions from `regions-wave3-candidates.md`.
**Method:** Live Overpass API queries using the production query pattern (`highway`~`path|footway|track|bridleway|steps`, `name` tag required) with the production `is_trail_worthy` filter applied to real geometry. Each region queried with `out geom;` for accurate coordinate counts. 15-second delays between queries to respect Overpass rate limits.

---

## 1. Measured inventory

| Region | Raw OSM ways | Post-filter | Footway ways (2-vertex) | Filter drop rate |
|--------|-------------|-------------|-------------------------|-----------------|
| C1 monongahela-highlands | 491 | 449 | 36 (4) | 8.6% |
| C2 new-river-gorge | 188 | 170 | 32 (5) | 9.6% |
| C3 greenbrier-river | 282 | 246 | 63 (5) | 12.8% |
| C4 cho-canal | 743 | 649 | 161 (26) | 12.7% |
| C5 gettysburg | 8 | 4 | 5 (0) | 50.0% |
| C6 highland-county | 75 | 70 | 0 (0) | 6.7% |
| C7 tuscarora-great-north | 89 | 64 | 13 (1) | 28.1% |
| C8 roanoke-valley | 345 | 310 | 36 (3) | 10.1% |
| C9 allegheny-trail | 1113 | 871 | 259 (30) | 21.7% |

**Notes:**
- "Raw" = all named OSM ways with `highway` in `path|footway|track|bridleway|steps` within the candidate bbox.
- "Post-filter" = ways that pass `is_trail_worthy` (the production trail filter: drops private access, public route refs, non-trail footway types, name denylist matches, residential street suffixes, 2-vertex footway stubs).
- "2-vertex footway" = ways with `highway=footway` and exactly 2 geometry nodes (driveway/connector stubs, correctly filtered).
- Filter drop rate = (raw - filtered) / raw. Higher rates indicate more urban noise or non-trail infrastructure.

---

## 2. Estimate vs. actual comparison

| Region | Original estimate | Actual post-filter | Delta | Accuracy |
|--------|-------------------|-------------------|-------|----------|
| C1 monongahela-highlands | 300–500 | 449 | — | ✅ Within range |
| C2 new-river-gorge | 200–350 | 170 | -30 to -180 | ❌ Below range |
| C3 greenbrier-river | 150–250 | 246 | — | ✅ Within range |
| C4 cho-canal | 100–200 | 649 | +449 to +549 | ❌ **Way above** |
| C5 gettysburg | 50–100 | 4 | -46 to -96 | ❌ **Way below** |
| C6 highland-county | 80–150 | 70 | -10 to -80 | ❌ Below range |
| C7 tuscarora-great-north | 120–200 | 64 | -56 to -136 | ❌ **Way below** |
| C8 roanoke-valley | 200–350 | 310 | — | ✅ Within range |
| C9 allegheny-trail | 300–500 | 871 | +371 to +571 | ❌ **Way above** |

**Key discrepancies:**
- **C4 cho-canal (649 vs 100–200):** The C&O Canal towpath area has far more named trail ways than estimated. The Great Falls area alone has extensive side-trail networks. The 161 footway ways (26 of which are 2-vertex stubs) confirm high urban trail density.
- **C9 allegheny-trail (871 vs 300–500):** The very large bbox (~8,000 sq km) captures far more trails than estimated, especially in the Monongahela NF southern portion. 259 footway ways indicate significant trail-side infrastructure.
- **C5 gettysburg (4 vs 50–100):** Only 8 raw named ways in the bbox, and half are filtered out. The battlefield's "trails" are mostly touring roads tagged as `highway=track` or `highway=footway` with names that match the residential street suffix or name denylist patterns. **This region is likely not viable for OSM-only ingestion.**
- **C7 tuscarora-great-north (64 vs 120–200):** The narrow bbox (0.4° × 0.2°) captures fewer trails than expected. The Tuscarora Trail itself is one long way, and side trails are sparse in this section.

---

## 3. Calibrated min_fetch_counts floors

Following the pilot region's methodology (70% of measured post-filter baseline):

| Region | Post-filter | 70% floor | Original floor | Change | Recommended floor |
|--------|------------|-----------|----------------|--------|-------------------|
| C1 monongahela-highlands | 449 | 314 | 200 | +114 | **310** |
| C2 new-river-gorge | 170 | 119 | 150 | -31 | **120** |
| C3 greenbrier-river | 246 | 172 | 100 | +72 | **170** |
| C4 cho-canal | 649 | 454 | 80 | +374 | **450** |
| C5 gettysburg | 4 | 3 | 40 | -37 | **5** (see note) |
| C6 highland-county | 70 | 49 | 60 | -11 | **50** |
| C7 tuscarora-great-north | 64 | 45 | 90 | -45 | **45** |
| C8 roanoke-valley | 310 | 217 | 150 | +67 | **220** |
| C9 allegheny-trail | 871 | 610 | 250 | +360 | **610** |

**C5 gettysburg note:** With only 4 post-filter ways, a `min_fetch_counts` floor of 5 is the practical minimum. However, this region is likely not viable for OSM-only ingestion — the NPS source would need to provide the actual hiking trails (Billy Yank, Johnny Reb, Gettysburg Trail) since OSM only captures battlefield touring roads that get filtered out. **Recommendation: drop C5 from Wave 3 unless an NPS trail source is added.**

**Rounding convention:** Floors rounded to nearest 10 (nearest 5 for small regions). The floor exists to catch gross truncation (e.g., Overpass timeout returning a partial result), not ordinary OSM churn — a 30% margin is conservative for that purpose.

---

## 4. Filter drop rate analysis

The trail filter's drop rate varies significantly by region character:

| Drop rate | Regions | Interpretation |
|-----------|---------|---------------|
| < 10% | C1 (8.6%), C6 (6.7%) | Wilderness areas — almost all named ways are real trails |
| 10–15% | C2 (9.6%), C3 (12.8%), C4 (12.7%), C8 (10.1%) | Mixed rural/recreational — some non-trail infrastructure |
| 20–30% | C9 (21.7%), C7 (28.1%) | Mixed wilderness/developed — more non-trail ways |
| 50% | C5 (50.0%) | Urban/historic — most named ways are roads, not trails |

**Finding:** The filter drop rate correlates with urban noise risk as expected. C5 Gettysburg's 50% drop rate confirms it's primarily non-trail infrastructure. C7's 28% rate is higher than expected for a rural area — the bbox may capture some residential spillover from Winchester's western suburbs.

---

## 5. Footway 2-vertex analysis

2-vertex footway ways (driveway/connector stubs) by region:

| Region | Total footway | 2-vertex footway | % of footway |
|--------|--------------|-----------------|-------------|
| C4 cho-canal | 161 | 26 | 16.1% |
| C9 allegheny-trail | 259 | 30 | 11.6% |
| C3 greenbrier-river | 63 | 5 | 7.9% |
| C1 monongahela-highlands | 36 | 4 | 11.1% |
| C2 new-river-gorge | 32 | 5 | 15.6% |
| C8 roanoke-valley | 36 | 3 | 8.3% |
| C7 tuscarora-great-north | 13 | 1 | 7.7% |
| C5 gettysburg | 5 | 0 | 0% |
| C6 highland-county | 0 | 0 | — |

**Finding:** C4 cho-canal has the highest absolute count (26) and C2 has the highest rate (15.6%). These are expected in urban-adjacent areas. The 2-vertex footway filter is working correctly — these are driveway/connector stubs, not real trails.

---

## 6. Updated recommendations

### First batch (revised from original)

| Region | Priority | Drive | Actual inventory | Why |
|--------|----------|-------|-----------------|-----|
| C1 monongahela-highlands | HIGH | 3.5h | 449 | Largest wilderness inventory, USFS-only, unique ecosystem |
| C8 roanoke-valley | HIGH | 3h | 310 | Urban noise stress-test, multi-source, substantial inventory |
| C3 greenbrier-river | HIGH (↑) | 4h | 246 | Larger than estimated, rail-trail type, very low noise |
| C9 allegheny-trail | HIGH (↑) | 4h+ | 871 | Largest inventory, large-scale stress test |

**Change rationale:** C3 and C9 move up because their actual inventories are much larger than estimated. C2 drops from the first batch because its inventory (170) is at the low end and below the original estimate.

### Second batch

| Region | Priority | Drive | Actual inventory | Why |
|--------|----------|-------|-----------------|-----|
| C2 new-river-gorge | MEDIUM | 4h | 170 | NPS-newest, diverse trail types, but smaller than expected |
| C4 cho-canal | MEDIUM | 2h | 649 | Huge inventory, historic towpath, urban noise stress-test |
| C6 highland-county | MEDIUM | 3h | 70 | Sparse region, fetch-sanity falsification |
| C7 tuscarora-great-north | MEDIUM (↓) | 1.5h | 64 | Smaller than expected, but closest to Front Royal |

### Drop / defer

| Region | Status | Reason |
|--------|--------|--------|
| C5 gettysburg | **DROP** | Only 4 trail-worthy OSM ways. Battlefield roads filtered out. Not viable without NPS trail source. |

---

## 7. Updated summary table

| # | Region | Priority | Drive | OSM actual | Urban noise | Floor | Key test |
|---|--------|----------|-------|-----------|-------------|-------|----------|
| C1 | monongahela-highlands | HIGH | 3.5h | 449 | Very low | 310 | USFS-only, largest wilderness |
| C9 | allegheny-trail | HIGH | 4h+ | 871 | Mixed | 610 | Large-scale stress test |
| C8 | roanoke-valley | HIGH | 3h | 310 | High | 220 | Urban noise, multi-source |
| C3 | greenbrier-river | HIGH | 4h | 246 | Very low | 170 | Rail-trail, low noise |
| C4 | cho-canal | MEDIUM | 2h | 649 | High | 450 | Historic towpath, urban |
| C2 | new-river-gorge | MEDIUM | 4h | 170 | Low | 120 | NPS-newest, smaller than expected |
| C6 | highland-county | MEDIUM | 3h | 70 | Very low | 50 | Sparse, fetch-sanity |
| C7 | tuscarora-great-north | MEDIUM | 1.5h | 64 | Low | 45 | Long-distance trail, closest |
| ~~C5~~ | ~~gettysburg~~ | ~~DROP~~ | ~~3h~~ | ~~4~~ | ~~Medium~~ | ~~5~~ | ~~Not viable (OSM-only)~~ |

---

## 8. Methodology notes

- **Query date:** 2026-07-13. OSM is a living database — counts will drift as mappers add/edit ways. The floors are calibrated against this snapshot.
- **Query pattern:** Identical to production (`ingestion/fetch/osm.py`): `way["highway"~"path|footway|track|bridleway|steps"]["name"]` with `out geom;` for real geometry.
- **Filter:** Production `is_trail_worthy` from `ingestion/trail_filter.py` applied to real OSM tags and geometry (not dummy coordinates).
- **Overpass mirrors:** Primary mirror (`overpass-api.de`) used. Some queries required retries due to rate limiting (empty responses). All 9 regions eventually succeeded.
- **NPS/USFS sources not queried:** This scout measures OSM inventory only. NPS and USFS trail data will add to the total ingested count but were not queried here (they require API keys or PBF files not available in this research context).
- **Water sources not queried:** The water overlay (Epic 041) depends on `:WaterSource` nodes, which are ingested separately. Water source counts are not included in this scout.

---

## 9. Open questions for PO

1. **C5 Gettysburg:** Drop entirely, or defer until an NPS trail source is added? The 4 OSM ways are insufficient for a viable region.
2. **C9 scale:** At 871 trail-worthy ways across ~8,000 sq km, C9 is 2.6x the pilot region's inventory. Should it be split into 2–3 smaller regions, or kept as a large-scale stress test?
3. **C4 floor:** At 450, C4's floor is the highest of all candidates. Is this acceptable, or should the bbox be narrowed to reduce inventory?
4. **C2 viability:** At 170 ways, C2 is smaller than expected. Is it still worth ingesting, or should it be deferred?
5. **First batch order:** Recommended first batch is now C1, C9, C8, C3 (largest inventories first). Does the PO want to prioritize differently (e.g., closest first: C7, C4, C1)?
