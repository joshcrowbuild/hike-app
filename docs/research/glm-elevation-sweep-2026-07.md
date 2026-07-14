# [GLM] Elevation-profile sanity sweep — July 2026

**Last verified:** 2026-07-14 · **Owner:** research (data-quality audit) · **Status:** `CLOSED AUDIT` (point-in-time; read for provenance + the proposed fix lane)

> Read-only, API-only sweep of the 3DEP elevation profiles at scale. No code, schema, or data was
> changed. Every claim below was re-derived from cached `/trail/{id}` responses (not taken on trust
> from the collection pass), and the one root cause is confirmed against `ingestion/elevation.py`.

---

## TL;DR

The elevation **profiles are structurally sound**. The two properties that would be catastrophic if
wrong — profiles crossed between trails, and profiles that disagree with their own geometry — both
hold cleanly (0 duplicates; profile length matches geometry within 5 % for **645/648** trails). No
coastal trail carries mountain elevations; no region shows an implausible range.

The sweep surfaced **one real, code-confirmed defect class** and **one enrichment gap**:

1. **HIGH — multi-part "seam" phantom climbs (12 trails).** Every trail whose OSM geometry is a
   `MultiLineString` with disjoint parts gets a phantom elevation step at each seam, because
   `build_profile` bridges the between-parts gap by **distance only** and then credits the full
   endpoint-to-endpoint elevation delta to `total_gain`. On Dickey Ridge the two parts are **4.9 km
   apart**, producing a **1334 ft** phantom step; short trails see `estimated_duration` inflated
   **2–5×** (Caneel Hill: a 1.45 mi trail reports 153 min / 1473 ft gain). This is a documented,
   intentional shortcut resting on the assumption *"multi-part routes are rare — segments usually
   join,"* which the data falsifies.
2. **MEDIUM — null-profile enrichment misses (21 trails).** Clustered in Prince William Forest
   (10/48) and Douthat (5/47). These trails have full geometry but no profile, and they sit **inside**
   the coverage envelope (intermixed with 72 good profiles), so this is **not** the known bbox-edge
   DEM pattern — it points to per-trail enrichment misses that need a graph-side check.

A large third bucket — 580 "length_mismatch" flags — is **not an elevation-profile defect** and is
re-scoped to a distance/geometry lane below.

---

## Method & coverage

| | |
|---|---|
| API | `https://adventure-planner-api.onrender.com` (live, ≤ 2 req/s, responses cached locally) |
| Collection date | 2026-07-13 |
| Regions | all 16 |
| Harvest | 49 `/plan` calls (`k=20`) across an origin grid per region → trail ids |
| Detail pulls | **669 unique** `/trail/{id}` responses (**~25 %** of the ~2,623-trail corpus) |
| Profiles present | 648 · **null** 21 |
| Profile shape | `elevation_profile.samples[]` = `{distance_m, elevation_m}`; `source` uniformly `usgs-3dep`; `resolution_m` 20 m (the "10 m 3DEP" is the DEM's native tile resolution, not the sample spacing) |

Checks run per profile: zero-variance / flatline; single-sample step > 100 ft; profile length vs
stated distance **and** vs its own geometry; range implausible for the region; profiles identical
across trails; null clustering vs the bbox-edge pattern.

---

## What holds (first-class verified results)

These are the "these hold" findings — a clean negative is a result.

| Check | Result | Evidence |
|---|---|---|
| **Crossed parallel-array wires** (identical profile on two trails) | **0 found** | 0 duplicate profile groups across 648 profiles |
| **Profile agrees with its own geometry** | **645/648 (99.5 %)** within 5 % | profile end-distance vs summed geometry length; only 3 exceed 5 % (max 39 %, Fore Mountain) |
| **Implausible range for region** (e.g. > 6,000 ft in coastal VA/OBX) | **0 found** | coastal maxima: First Landing 53 ft, Outer Banks 53 ft, York River 101 ft, Westmoreland 181 ft; mountain maxima are genuine (Peaks of Otter 3,277 ft = an AT segment; Mount Rogers 1,530 ft) |
| **Source provenance** | uniform | every profile `source = usgs-3dep` |

The 99.5 % geometry-agreement number is the load-bearing one: it means the DEM sampling and the
distance axis are faithful to whatever geometry the API holds. Every anomaly below is therefore
either (a) a *geometry* problem the profile faithfully inherits, or (b) an enrichment miss — **not** a
DEM-sampling error.

---

## Defect Class A — multi-part "seam" phantom climbs · **HIGH**

**Symptom.** 12 trails carry a single adjacent-sample elevation step > 100 ft — physically impossible
across 20 m of trail. Unlike a classic DEM void (which spikes and returns), these **step up and
persist**: e.g. Dickey Ridge reads `…604, 604, 1939, 1939…` ft.

**Root cause (confirmed, `ingestion/elevation.py:158` `build_profile`).** All **12/12** flagged
trails are `MultiLineString` geometries with disjoint parts. When the route has multiple parts, the
code bridges the gap between them by distance only:

```python
if last_pt is not None:
    # Bridge a between-parts gap by distance only — do NOT densely sample the
    # bridge (it isn't real trail). ... gain/loss across the bridge reflect the
    # real elevation delta between the two covered endpoints (multi-part routes
    # are rare — segments usually join).
    cum += haversine_m(last_pt, part[0])
```

The comment names three protections; the data shows **two hold and one fails**:

- ✅ **Distance stays honest** — the bridge length is added to `cum`, which is why profile length
  matches geometry at 99.5 %.
- ✅ **Max grade is protected** — grade is measured over a ground window, so Dickey Ridge reports
  `max_grade 19 %`, not the ~2,000 % the raw 1334 ft / 20 m step would imply.
- ❌ **Gain/loss is *not* protected** — `compute_gain_loss_grade` walks adjacent `(distance,
  elevation)` pairs, so it credits the full endpoint-to-endpoint elevation delta across the bridge as
  climb. The guarding assumption — *"multi-part routes are rare — segments usually join"* — is
  falsified: the sampled bridges span **300 m to 4,887 m**.

The separate `max_gap_m` guard (line 197) only nulls a profile for interior **DEM coverage holes**
(uncovered samples between covered ones); a between-parts *geometry* bridge is never sampled, so it
sails straight through that guard.

**User-facing impact.** The phantom climb inflates `total_gain` and, through it, `estimated_duration`:

| Trail | Declared | Reported gain | Reported duration | Note |
|---|---|---|---|---|
| Caneel Hill | 1.45 mi | 1,473 ft | **153 min** | 6 parts; absurd for 1.45 mi |
| Northern Peaks | 1.3 mi | 1,000 ft | **119 min** | 3 parts |
| Dickey Ridge | 3.4 mi | 2,280 ft | **305 min** | 1334 ft phantom step alone |

### Worst offenders (all 12, by max adjacent step)

| Trail id | Name | Region | Parts | Max step | Largest inter-part gap |
|---|---|---|---:|---:|---:|
| `ct:osm:way_1418076505` | Dickey Ridge Trail | shenandoah-gwj | 2 | **1,334 ft** | 4,887 m |
| `ct:osm:way_1005063202` | Ted Lake Trail | sky-meadows | 2 | **931 ft** | 2,853 m |
| `ct:osm:way_1038392003` | Feather Camp Trail | mount-rogers | 3 | 436 ft | — |
| `ct:osm:way_19812948` | Brown Hollow Spur Trail | douthat | 3 | 342 ft | — |
| `ct:osm:way_70198067` | Caneel Hill Trail | st-john-usvi | 6 | 338 ft | 480 m |
| `ct:osm:way_367166496` | Northern Peaks Trail | catoctin-sugarloaf | 3 | 314 ft | 750 m |
| `ct:osm:way_389900583` | Tuscarora Overlook Trail | douthat | 3 | 176 ft | — |
| `ct:osm:way_1437146978` | Salt Stump Trail | douthat | 5 | 164 ft | — |
| `ct:osm:way_20262099` | Helton Creek Trail | mount-rogers | 5 | 134 ft | — |
| `ct:osm:way_1086817106` | Flat Run Trail | douthat | 3 | 131 ft | — |
| `ct:osm:way_1149009210` | South Valley Trail | prince-william-forest | 18 | 114 ft | — |
| `ct:osm:way_1279422915` | Snead Farm Loop Trail | shenandoah-gwj | 3 | 101 ft | — |

The 12 are a **lower bound**: the sweep only sees a multi-part trail when a seam happens to bridge a
large elevation delta. Multi-part trails whose parts sit at similar elevations carry the same phantom
distance/gain-across-the-bridge behavior without tripping the > 100 ft step threshold.

---

## Defect Class B — null-profile enrichment misses · **MEDIUM**

21 of 669 trails (3 %) return `elevation_profile: null`. They are not evenly spread:

| Region | Nulls / trails | Example trails |
|---|---|---|
| Prince William Forest | **10 / 48 (21 %)** | Sewer, K-9, Scout, Limbo, Heartbreak Ridge, Neabsco Greenway, John Palmer, Geiger Loop, Little Pine, Montezuma's Revenge |
| Douthat | **5 / 47 (11 %)** | Warm Springs Mountain, Dry Run, Jordan Run, Piney Mountain, Beards Mountain Spur |
| Sky Meadows | 2 / 26 | North Ridge Trail, Old Trail |
| Catoctin · Harpers Ferry · Westmoreland · York River | 1 each | C&O Canal, AT Nat'l Scenic, Range 24 Firebreak, "A" |

**These trails have geometry.** Sampled nulls carry full `LineString`/`MultiLineString` coordinates
(Neabsco Greenway 243 verts, the AT segment 697 verts) — the null is a failed **DEM lookup**, not a
missing route.

**It is not the bbox-edge DEM pattern.** Prince William Forest's 10 nulls sit in the geographic
**interior** of the region, intermixed with 72 trails that *do* have profiles in the same lat/lon
envelope (null centroid −77.337, 38.543 lands well inside the present-profile spread). Douthat's
nulls partly hug the region's northern margin, but PWF's do not. Scattered interior misses beside
successful neighbors point to **per-trail enrichment gaps** (e.g. ways added/updated after a DEM
pass, or silently dropped during enrichment) rather than an absent tile.

**Owed follow-up (graph-side, out of this sweep's API-only reach):** query which trail nodes lack an
elevation array, cross-check against DEM manifest coverage and ingest timestamps, and re-run
enrichment for the misses.

---

## Not a defect — flatlines explained (2 trails)

Both zero-variance profiles have benign explanations; neither is a DEM miss read as sea level:

- `ct:osm:way_602322159` **North Boat Slips** (outer-banks) — 12 samples, all **−2 ft**. Correct: a
  boat slip at the waterline. A true negative, correctly flat.
- `ct:osm:way_1119667683` **Kennedy Peak Tr (white)** (shenandoah) — 3 samples, all **2,561 ft**. Not
  a flat mountain; a **3-sample stub** (~40 m of geometry). This is a symptom of the geometry-fragment
  issue below, not an elevation defect.

---

## Adjacent finding (re-scoped, NOT elevation) — stated distance vs geometry

580 trails were flagged "length_mismatch." Because the profile matches its **geometry** at 99.5 %,
this is a mismatch between the **stated distance** and the geometry the API holds — a
distance/geometry-completeness question, **not** an elevation-profile defect. It splits two ways:

- **357 trails: profile ≪ stated** (ratio < 0.3; median ratio 0.25). The stored geometry is a
  fragment. Extremes: Kennedy Peak (white) — 9 m of geometry vs 5.5 mi stated; The Priest Shelter
  Trail — 162 m vs 23 mi. The elevation profile is mechanically correct but describes a stub, so its
  gain/duration under-report the real trail (this is what makes Kennedy Peak read as a flatline).
- **58 trails: profile ≫ stated** (ratio > 1.5). The geometry/way is longer than the stated figure —
  John Blair Trail 14.0 km vs 1.4 mi stated; an AT segment 44.8 km vs 5.6 mi. The stated number looks
  like a named-trail subsection or is simply too small.

Recommend a **separate distance/geometry-completeness lane** own this; it is not in scope for an
elevation-DEM sweep and should not be fixed in the elevation pipeline.

---

## Per-region statistics

Ranges and steps in feet. `spk` = steps > 100 ft; `flt` = flatlines; `null` = null profiles.

| Region | Trails | Profiles | Null | spk | flt | Range median | Range max | Step median | Step max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Catoctin | 55 | 54 | 1 | 1 | 0 | 86 | 734 | 14.6 | 314 |
| Douthat | 47 | 42 | 5 | 4 | 0 | 256 | 1,743 | 21.1 | 342 |
| First Landing | 39 | 39 | 0 | 0 | 0 | 7 | 53 | 5.3 | 29 |
| Great Falls | 54 | 54 | 0 | 0 | 0 | 48 | 188 | 9.2 | 77 |
| Harpers Ferry | 27 | 26 | 1 | 0 | 0 | 87 | 655 | 17.2 | 75 |
| James River SP | 24 | 24 | 0 | 0 | 0 | 65 | 1,401 | 15.3 | 57 |
| Mount Rogers | 79 | 79 | 0 | 2 | 0 | 362 | 1,530 | 27.8 | 436 |
| Outer Banks | 48 | 48 | 0 | 0 | 1 | 11 | 53 | 5.9 | 23 |
| Peaks of Otter | 39 | 39 | 0 | 0 | 0 | 243 | 3,277 | 21.9 | 46 |
| Prince William Forest | 48 | 38 | 10 | 1 | 0 | 84 | 331 | 11.5 | 114 |
| Richmond | 20 | 20 | 0 | 0 | 0 | 15 | 82 | 7.8 | 26 |
| Shenandoah | 60 | 60 | 0 | 2 | 1 | 79 | 2,090 | 14.8 | 1,334 |
| Sky Meadows | 26 | 24 | 2 | 1 | 0 | 143 | 1,017 | 15.0 | 931 |
| St. John | 27 | 27 | 0 | 1 | 0 | 186 | 1,043 | 23.7 | 338 |
| Westmoreland | 32 | 31 | 1 | 0 | 0 | 73 | 181 | 15.0 | 47 |
| York River | 44 | 43 | 1 | 0 | 0 | 42 | 101 | 9.3 | 54 |
| **Total** | **669** | **648** | **21** | **12** | **2** | — | — | — | — |

Regions with **all-sane** profiles (no null, no spike, no flatline, plausible ranges): **First
Landing, Great Falls, James River SP, Peaks of Otter, Richmond** — verified clean.

---

## Proposed severity ranking for a fix lane

| # | Severity | Issue | Scope | Fix locus |
|---|---|---|---|---|
| 1 | **HIGH** | Multi-part seam phantom climbs — inflated `total_gain` / `estimated_duration` | 12 confirmed (lower bound); every multi-part trail affected on gain | `ingestion/elevation.py` `build_profile` — when a between-parts bridge exceeds a threshold (reuse `max_gap_m`), **don't credit the endpoint elevation delta to gain/loss** (reset the running elevation across the bridge, mirroring the grade window's existing protection); or split into a per-part profile; re-ingest affected regions |
| 2 | **MEDIUM** | Null-profile enrichment misses, interior-clustered (PWF 21 %, Douthat 11 %) | 21 trails, likely more corpus-wide | Graph-side: find trail nodes lacking elevation, cross-check DEM manifest + ingest timestamps, re-run enrichment |
| 3 | **LOW** | 3-sample stub flatline (Kennedy Peak white) | symptom of #4 | folds into the distance/geometry lane |
| 4 | **SEPARATE LANE (not elevation)** | Stated distance vs geometry divergence — 357 stub geometries + 58 aggregate mismatches | 580 flags | distance/geometry-completeness lane; do **not** touch the elevation pipeline |

Recommended first action: **item 1**. It is a small, well-localized change (the code already
protects distance and grade against the same bridge; only gain/loss is unguarded), it corrects a
visibly wrong user-facing number, and its scope is bounded by a single documented assumption.

---

## Scope & limits (honest boundaries)

- **API-only / black box.** This sweep sees `/plan` + `/trail/{id}` responses; it cannot see the DEM
  manifest, ingest logs, or the graph. Root cause for Class A is confirmed against source; the null
  (Class B) cause is **inferred** from the API surface and needs a graph-side check to close.
- **~25 % sample.** 669 of ~2,623 trails, spread across all 16 regions via a `/plan` origin grid.
  Counts (12 spikes, 21 nulls) are **lower bounds**, not corpus totals.
- **Read-only.** No code, schema, or data changed. The `ingestion/elevation.py` excerpt is quoted for
  provenance only.
- **Reproduction.** Cached responses + the derived stats live under `/private/tmp/` on the collecting
  host (`glm-elevation-sweep-cache-2026-07/`, `glm-elevation-sweep-results-2026-07.json`); every table
  above was re-derived from that cache, not from the collection pass's own summary.
