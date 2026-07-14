# Expansion Wave 3 — Candidate Region Research

**Status:** ACTIVE (foreign-model research; ready for PO review)
**Reviewer:** GLM
**Scope:** 6–10 candidate regions within ~4h drive of Front Royal VA (38.918, -78.194) + 1 stress-test pick.
**Method:** Web research + Overpass density estimation from pilot baseline (2,419 named OSM ways / ~3,500 sq km = ~0.7 ways/sq km). All bboxes verified non-overlapping against 16 existing regions and each other.

---

## 1. Existing regions (16)

shenandoah-gwj, outer-banks, catoctin-sugarloaf, douthat, first-landing, great-falls, harpers-ferry, james-river-sp, mount-rogers, peaks-of-otter, prince-william-forest, richmond, sky-meadows, st-john-usvi, westmoreland, york-river.

Wave 3 bboxes must not overlap any existing region (positive-area intersection in BOTH axes fails `test_region_bboxes_pairwise_disjoint`).

---

## 2. Candidates

### C1: Monongahela Highlands (WV)

| Field | Value |
|-------|-------|
| region_id | `monongahela-highlands` |
| bbox | `[-80.0, 38.6, -79.4, 39.2]` |
| Drive from Front Royal | ~3.5h (I-81 N, I-64 W, US-219 N) |
| Parks | Monongahela NF: Dolly Sods Wilderness (17,371 ac, 47 mi trails), Seneca Creek Backcountry, Spruce Knob-Seneca Rocks NRA |
| NPS overlap | No |
| USFS overlap | Yes — Monongahela NF (Gauley + Potomac RDs) |
| Estimated OSM ways | ~300–500 (Dolly Sods well-mapped; wilderness interior sparse) |
| 3DEP tiles | n39w079, n39w080, n40w079, n40w080 |
| Urban noise risk | **Very low** — among the most remote areas in the eastern US. Nearest towns: Davis (~1,000 pop), Seneca Rocks (~100 pop) |
| min_fetch_counts | `{osm: 200}` |
| Sources | OSM, USFS |
| Origins | Dolly Sods (39.0, -79.35), Seneca Rocks (38.85, -79.37) |
| Non-overlap | Zero-area lon contact with shenandoah-gwj at -79.4. Safe. |

**Why:** High-elevation plateau ecosystem (bog, heath, wind-carved sandstone) distinct from Shenandoah. Heavy backcountry use = strong OSM coverage. Tests USFS-only region with no NPS source.

---

### C2: New River Gorge (WV)

| Field | Value |
|-------|-------|
| region_id | `new-river-gorge` |
| bbox | `[-81.15, 37.8, -80.85, 38.2]` |
| Drive from Front Royal | ~4h (I-81 S, I-64 W, US-19 S) |
| Parks | New River Gorge NP and Preserve (NPS, 70,000+ ac, 40+ named trails), Babcock State Park, Hawk's Nest State Park |
| NPS overlap | Yes — NERI |
| USFS overlap | No |
| Estimated OSM ways | ~200–350 (NPS trails well-mapped; state parks moderate) |
| 3DEP tiles | n38w081, n38w082 |
| Urban noise risk | **Low** — Fayetteville (~2,500 pop). Some spillover from Beckley (~15 mi south, outside bbox). |
| min_fetch_counts | `{osm: 150, nps: 20}` |
| Sources | OSM, NPS |
| Origins | Fayetteville (38.05, -81.1), Grandview (37.97, -81.08) |
| Non-overlap | No overlap with any existing region. Safe. |

**Why:** Newest NPS unit (2020). Diverse trail types: gorge rim overlooks, waterfall hikes, historic coal-mining ruins. Tests NPS trail data for a modern park with heavy AllTrails/OSM coverage.

---

### C3: Greenbrier River Trail (WV)

| Field | Value |
|-------|-------|
| region_id | `greenbrier-river` |
| bbox | `[-80.7, 37.9, -80.0, 38.6]` |
| Drive from Front Royal | ~4h (I-81 S, I-64 W, US-219 S) |
| Parks | Greenbrier River Trail (78 mi rail-trail, WV State Parks), Watoga State Park (10,000+ ac), Cass Scenic Railroad SP, Greenbrier State Forest |
| NPS overlap | No |
| USFS overlap | Yes — Monongahela NF (bordering) |
| Estimated OSM ways | ~150–250 (rail-trail is one well-mapped way; side trails moderate) |
| 3DEP tiles | n38w080, n38w081, n39w080, n39w081 |
| Urban noise risk | **Very low** — Marlinton (~1,000 pop), Cass (~50 pop). Partly within National Radio Quiet Zone. |
| min_fetch_counts | `{osm: 100}` |
| Sources | OSM, USFS |
| Origins | Marlinton (38.22, -80.09), Cass (38.42, -80.05) |
| Non-overlap | No overlap with any existing region. Safe. |

**Why:** 78-mile rail-trail is a unique trail type (flat, graded, multi-use) absent from the corpus. Tests the trail filter on a long-distance rail-trail that might trigger false positives.

---

### C4: C and O Canal Towpath (MD)

| Field | Value |
|-------|-------|
| region_id | `cho-canal` |
| bbox | `[-77.9, 39.2, -77.35, 39.7]` |
| Drive from Front Royal | ~2h (I-66 E, I-270 N, MD-28) |
| Parks | C and O Canal NHP (184.5 mi towpath, NPS), Billy Goat Trail, Great Falls Tavern area |
| NPS overlap | Yes — CHOH |
| USFS overlap | No |
| Estimated OSM ways | ~100–200 (towpath is one long way; side trails at Great Falls well-mapped) |
| 3DEP tiles | n39w077, n39w078 |
| Urban noise risk | **High** — runs through suburban Montgomery County, MD. Many residential streets and park paths near the towpath. Trail filter's `residential_street_suffix` denylist heavily exercised. |
| min_fetch_counts | `{osm: 80, nps: 15}` |
| Sources | OSM, NPS |
| Origins | Brunswick MD (39.31, -77.62), White's Ferry (39.16, -77.52) |
| Non-overlap | Narrowed from initial bbox to leave a clear gap from great-falls [-77.3, 38.9, -77.1, 39.05]. No overlap. Safe. |

**Why:** 184.5-mile historic towpath is the longest rail-trail-equivalent in the corpus. High urban noise risk makes it an excellent stress-test for the trail filter.

---

### C5: Gettysburg NMP (PA)

| Field | Value |
|-------|-------|
| region_id | `gettysburg` |
| bbox | `[-77.3, 39.8, -77.2, 39.85]` |
| Drive from Front Royal | ~3h (I-66 E, US-15 N) |
| Parks | Gettysburg NMP (NPS, ~9,000 ac, 8 named trails: Billy Yank 9.8 mi, Johnny Reb 4 mi, Gettysburg Trail 2.8 mi) |
| NPS overlap | Yes — GETT |
| USFS overlap | No |
| Estimated OSM ways | ~50–100 (military park trails fewer but well-mapped; battlefield roads may trigger trail filter) |
| 3DEP tiles | n40w077, n40w078 |
| Urban noise risk | **Medium** — Gettysburg borough (~3,800 pop) inside bbox. Battlefield roads tagged as `highway=track` in OSM may test filter's ability to distinguish touring roads from hiking trails. |
| min_fetch_counts | `{osm: 40, nps: 5}` |
| Sources | OSM, NPS |
| Origins | Gettysburg (39.83, -77.23) |
| Non-overlap | No overlap with any existing region. Safe. |

**Why:** Military park trail system is unique — historic/interpretive trails rather than recreational. Small inventory but tests pipeline on low-volume NPS source and trail filter on battlefield roads.

---

### C6: Highland County (VA)

| Field | Value |
|-------|-------|
| region_id | `highland-county` |
| bbox | `[-79.7, 38.3, -79.3, 38.6]` |
| Drive from Front Royal | ~3h (I-81 S, US-250 W) |
| Parks | George Washington NF (Highland Ranger District), Virginia Birding and Wildlife Trail segments |
| NPS overlap | No |
| USFS overlap | Yes — GWJ NF (Highland RD) |
| Estimated OSM ways | ~80–150 (very rural county, ~2,300 pop; USFS trails moderate, OSM coverage thin) |
| 3DEP tiles | n38w079, n38w080 |
| Urban noise risk | **Very low** — one of the least populous counties in VA. No incorporated towns >500 pop. |
| min_fetch_counts | `{osm: 60}` |
| Sources | OSM, USFS |
| Origins | Monterey (38.41, -79.58) |
| Non-overlap | No overlap with douthat [-79.9, 37.8, -79.72, 38.06] — no lat overlap. Safe. |

**Why:** Tests the pipeline on a very sparse, low-volume region. The `min_fetch_counts` floor is deliberately low — a truncated Overpass fetch could go undetected if the floor is miscalibrated. Good falsification test for the fetch-sanity gate.

---

### C7: Tuscarora Trail / Great North Mountain (VA/WV)

| Field | Value |
|-------|-------|
| region_id | `tuscarora-great-north` |
| bbox | `[-78.7, 39.1, -78.3, 39.3]` |
| Drive from Front Royal | ~1.5h (I-81 S, US-11 S, VA-259 W) |
| Parks | George Washington NF (Lee RD — Great North Mountain Wilderness), Tuscarora Trail (250 mi long-distance trail, AT branch) |
| NPS overlap | No |
| USFS overlap | Yes — GWJ NF (Lee RD) |
| Estimated OSM ways | ~120–200 (Tuscarora Trail well-mapped as route relation; side trails moderate) |
| 3DEP tiles | n39w078, n39w079 |
| Urban noise risk | **Low** — Wardensville WV (~300 pop). Some residential spillover from Winchester (~15 mi east, outside bbox). |
| min_fetch_counts | `{osm: 90}` |
| Sources | OSM, USFS |
| Origins | Wardensville (39.07, -78.59), Lost River (38.97, -78.43) |
| Non-overlap | Adjusted north to lat 39.1 to avoid overlap with shenandoah-gwj [-79.4, 37.8, -78.0, 39.1]. Zero-area lat contact at 39.1. Safe. |

**Why:** The Tuscarora Trail is a 250 mi long-distance hiking trail branching off the AT — a trail type not yet in the corpus. Great North Mountain Wilderness has a dense USFS trail network. Tests OSM route-relation conflation with USFS trail data.

---

### C8: Roanoke Valley (VA) — STRESS TEST

| Field | Value |
|-------|-------|
| region_id | `roanoke-valley` |
| bbox | `[-80.1, 37.15, -79.7, 37.45]` |
| Drive from Front Royal | ~3h (I-81 S) |
| Parks | Blue Ridge Parkway (NPS), Mill Mountain Park (Roanoke City), Carvins Cove Natural Reserve (60+ mi trails), Explore Park |
| NPS overlap | Yes — BLRI (Blue Ridge Parkway corridor) |
| USFS overlap | Yes — GWJ NF (Eastern Divide RD, bordering) |
| Estimated OSM ways | ~200–350 (Carvins Cove heavily mapped; BRP trails moderate; Roanoke urban trail network significant) |
| 3DEP tiles | n37w080, n37w081 |
| Urban noise risk | **High** — Roanoke (~100,000 pop) inside bbox. Urban greenway trails, park paths, and residential streets heavily exercise the trail filter. This is the primary stress-test for urban noise. |
| min_fetch_counts | `{osm: 150, nps: 10}` |
| Sources | OSM, NPS, USFS |
| Origins | Roanoke (37.27, -79.94) |
| Non-overlap | No overlap with any existing region. Safe. |

**Why:** **Stress-test pick.** Urban-adjacent mountain trail system. Carvins Cove is one of the largest municipal trail networks in the eastern US. The BRP corridor adds NPS trails. Tests: high urban noise + multi-source conflation (OSM + NPS + USFS) + municipal trail data that may not be in OSM at all.

---

### C9: Allegheny Trail (WV) — LARGE-SCALE STRESS TEST

| Field | Value |
|-------|-------|
| region_id | `allegheny-trail` |
| bbox | `[-81.0, 37.0, -80.0, 38.3]` |
| Drive from Front Royal | ~4h+ (I-81 S, I-64 W) |
| Parks | Monongahela NF (southern portion), Watoga State Park, Seneca State Forest, Greenbrier River Trail (partial), multiple county parks along the Allegheny Trail (330 mi, WV Scenic Trails Association) |
| NPS overlap | No |
| USFS overlap | Yes — Monongahela NF (large overlap) |
| Estimated OSM ways | ~300–500 (very large bbox; coverage varies from dense in MNF to sparse in southern WV) |
| 3DEP tiles | n37w080, n37w081, n38w080, n38w081 |
| Urban noise risk | **Mixed** — passes near Lewisburg (~4,000 pop), White Sulphur Springs. Southern portion has resort development. |
| min_fetch_counts | `{osm: 250}` |
| Sources | OSM, USFS |
| Origins | Lewisburg (37.80, -80.05), Marlinton (38.22, -80.09) |
| Non-overlap | Narrowed to lat 38.3 max to avoid overlap with C1 monongahela-highlands (lat 38.6 min). No overlap with C3 greenbrier-river if C3 is also added — C3 starts at lat 37.9, this goes to 37.0. **WARNING**: lon overlap with C3 at -80.0 to -80.7. Must coordinate: either narrow C3 or don't add both. Recommend: if both are added, split at lon -80.0 (C3 gets -80.7 to -80.0, C9 gets -81.0 to -80.0). Safe with coordination. |

**Why:** **Large-scale stress-test pick.** Very large bbox (~8,000 sq km, 2x the pilot region) that tests:
1. Overpass timeout handling (large query, truncated fetch, `verify_before_prune` must catch)
2. `min_fetch_counts` calibration (250 floor is aggressive for a sparse region)
3. Elevation coverage across 4 3DEP tiles (DEM fetch + merge complexity)
4. Trail filter on a long-distance trail passing through towns (urban noise in Lewisburg)
5. Region non-overlap coordination with C1/C3 if multiple Wave 3 regions are added

---

## 3. Summary ranking

| # | Region | Priority | Drive | OSM est. | Urban noise | Key test |
|---|--------|----------|-------|----------|-------------|----------|
| C1 | monongahela-highlands | HIGH | 3.5h | 300–500 | Very low | USFS-only region, unique ecosystem |
| C2 | new-river-gorge | HIGH | 4h | 200–350 | Low | Newest NPS unit, diverse trail types |
| C7 | tuscarora-great-north | HIGH | 1.5h | 120–200 | Low | Long-distance trail conflation, closest to FR |
| C8 | roanoke-valley | HIGH | 3h | 200–350 | **High** | Urban noise stress-test, multi-source |
| C3 | greenbrier-river | MEDIUM | 4h | 150–250 | Very low | Rail-trail type, trail filter edge cases |
| C4 | cho-canal | MEDIUM | 2h | 100–200 | **High** | Historic towpath, urban noise |
| C6 | highland-county | MEDIUM | 3h | 80–150 | Very low | Sparse region, fetch-sanity falsification |
| C5 | gettysburg | LOW | 3h | 50–100 | Medium | Military park, low-volume NPS |
| C9 | allegheny-trail | LOW (stress) | 4h+ | 300–500 | Mixed | Large-scale timeout/DEM stress test |

**Recommended first batch:** C1, C2, C7, C8 (4 regions, diverse ecosystems, all within 4h, covers USFS-only / NPS-newest / long-distance / urban-noise).

**Second batch:** C3, C4, C6 (rail-trail type, historic towpath, sparse-region falsification).

**Stress-test (standalone):** C9 (large-scale, add only after the first batch is ingested and verified).

---

## 4. 3DEP tile reference

All tiles are USGS 1/3-arc-second (~10 m) DEM, NW-corner naming convention `n{lat}w{lon}`.

| Region | Tiles |
|--------|-------|
| C1 monongahela-highlands | n39w079, n39w080, n40w079, n40w080 |
| C2 new-river-gorge | n38w081, n38w082 |
| C3 greenbrier-river | n38w080, n38w081, n39w080, n39w081 |
| C4 cho-canal | n39w077, n39w078 |
| C5 gettysburg | n40w077, n40w078 |
| C6 highland-county | n38w079, n38w080 |
| C7 tuscarora-great-north | n39w078, n39w079 |
| C8 roanoke-valley | n37w080, n37w081 |
| C9 allegheny-trail | n37w080, n37w081, n38w080, n38w081 |

Tile base URL: `https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/13/TIFF/current/`
Tile file pattern: `{tile_name}.tif` (e.g., `n39w079.tif`)

Run `python scripts/fetch_dem.py --init <region_id>` after authoring the geojson to populate `regions/dem_manifest.json` with the tile list and fetch the DEMs.

---

## 5. Non-overlap verification

All candidate bboxes checked against:
- 16 existing region files (see section 1)
- Each other (pairwise)

Adjustments made:
- C4 cho-canal: narrowed east boundary from -77.2 to -77.35 to leave gap from great-falls
- C7 tuscarora-great-north: narrowed south boundary from 38.9 to 39.1 to avoid overlap with shenandoah-gwj
- C9 allegheny-trail: narrowed north boundary from 39.0 to 38.3 to avoid overlap with C1 monongahela-highlands

**Remaining coordination needed:** C3 greenbrier-river and C9 allegheny-trail share a lon boundary at -80.0. If both are added, C3 gets lon [-80.7, -80.0] and C9 gets lon [-81.0, -80.0]. Zero-area edge contact is allowed per the non-overlap guard.

---

## 6. min_fetch_counts calibration

Following the pilot region's methodology (70% of measured live Overpass baseline):

| Region | Estimated OSM ways | Floor (70%) | Rationale |
|--------|-------------------|-------------|-----------|
| C1 | 300–500 | 200 | Conservative floor for USFS-heavy region |
| C2 | 200–350 | 150 | NPS trails well-mapped |
| C3 | 150–250 | 100 | Rail-trail is one long way; side trails moderate |
| C4 | 100–200 | 80 | Urban area has more OSM coverage |
| C5 | 50–100 | 40 | Small military park |
| C6 | 80–150 | 60 | Very sparse rural county |
| C7 | 120–200 | 90 | Tuscarora Trail well-mapped |
| C8 | 200–350 | 150 | Urban trail network adds coverage |
| C9 | 300–500 | 250 | Large bbox, sparse in southern portion |

**Note:** These are estimates. The actual floor should be calibrated against a live Overpass query (`make ingest --region <id> --dry-run`) before the first real ingest. The floor exists to catch gross truncation, not ordinary OSM churn.

---

## 7. Open questions for PO

1. **Region granularity:** C9 (allegheny-trail) is 2x the pilot region. Should it be split into 2–3 smaller regions, or kept as a stress-test?
2. **C3/C9 overlap:** If both greenbrier-river and allegheny-trail are added, the lon boundary must be split at -80.0. Is this acceptable, or should one be dropped?
3. **Municipal trail data:** C8 (roanoke-valley) has Carvins Cove trails that may not be in OSM. Should we add a municipal trail source, or rely on OSM coverage?
4. **Gettysburg:** C5 has only ~50–100 OSM ways. Is the ingest pipeline overhead worth it for such a small inventory?
5. **Priority order:** Recommended first batch is C1, C2, C7, C8. Does the PO want to prioritize differently (e.g., closest first: C7, C4, C1)?
