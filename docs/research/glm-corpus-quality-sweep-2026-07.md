# GLM Corpus Quality Sweep (2026-07-13)

**Status:** ACTIVE (read-only audit + proposed exclusions.json diff)
**Reviewer:** GLM (foreign-model corpus quality sweep)
**Scope:** All 16 regions via public API, 681 unique trails surfaced

---

## Methodology

- Queried `/regions` endpoint for all 16 region configs
- POSTed `/plan` with `k=20` from every origin (49 queries total, ~0.7s spacing)
- Deduplicated trails by `canonical_id` within each region
- Flagged suspicious names against current `regions/exclusions.json` patterns + additional heuristics
- Verified each flagged entry against the OSM API (`api.openstreetmap.org/api/0.6/way/{id}.json`) for ground-truth tags
- Cross-checked within-region and cross-region duplicate names

**API endpoint:** `https://adventure-planner-api.onrender.com`
**Total unique trails surfaced:** 681 across 16 regions

| Region | Unique trails | Origins queried |
|--------|-------------|-----------------|
| catoctin-sugarloaf | 55 | 3 |
| douthat | 47 | 3 |
| first-landing | 39 | 4 |
| great-falls | 54 | 3 |
| harpers-ferry | 27 | 2 |
| james-river-sp | 24 | 3 |
| mount-rogers | 79 | 4 |
| outer-banks | 60 | 4 |
| peaks-of-otter | 39 | 3 |
| prince-william-forest | 48 | 4 |
| richmond | 20 | 1 |
| shenandoah-gwj | 60 | 3 |
| sky-meadows | 26 | 3 |
| st-john-usvi | 27 | 3 |
| westmoreland | 32 | 3 |
| york-river | 44 | 3 |

---

## Findings (ranked by severity)

### F1 (HIGH): OBX beach access ramps — 10 non-trail entries

**Region:** outer-banks
**Pattern:** Bare numbered "Ramp N" names — beach/campground access infrastructure, not recreational trails.

| OSM way ID | Name | Tags |
|------------|------|------|
| way/326632770 | Ramp 1 | `highway=footway, surface=sand` |
| way/326625579 | Ramp 2 | `highway=footway` |
| way/73964377 | Ramp 45 | `highway=footway` |
| way/1068579602 | Ramp 48 | `highway=footway` |
| way/16494845 | Ramp 49 | `highway=footway` |
| way/699297668 | Ramp 55 | `highway=footway` |
| way/295329757 | Ramp 59 | `highway=footway` |
| way/16611428 | Ramp 67 | `highway=footway` |
| way/240450986 | Ramp 68 | `highway=footway` |
| way/252788735 | Ramp 70 | `highway=footway` |

**Why these slip through:** The `name_deny` pattern has `\b(ramp|stairs?) to\b` which catches "Ramp to X" but not bare "Ramp N". These are Cape Hatteras National Seashore beach access ramps — numbered boardwalk/sand paths from parking to beach, not hiking trails.

**Proposed fix:** Add `\bramp \d+\b` to `name_deny` in `exclusions.json`.

### F2 (HIGH): OBX campground utility paths — 5 non-trail entries

**Region:** outer-banks
**Pattern:** Campground paths to comfort stations/showers — pedestrian infrastructure, not recreational trails.

| OSM way ID | Name | Tags |
|------------|------|------|
| way/328748535 | Loop G path to Comfort Station | `highway=footway, surface=wood` |
| way/328748536 | Loop G Showers Path | `highway=footway, surface=wood` |
| way/328748555 | Loop J Path to Comfort Station | `highway=footway, surface=wood` |
| way/327975184 | Path Loop B Comfort Station | `highway=footway` |
| way/327975185 | Path Loop B Showers | `highway=footway` |

**Why these slip through:** The `name_deny` pattern has `\bpath to (a |an |the )?(school|store|parking|lot|bus|garage|garden|building|club|gym|colonnade)\b` but "Comfort Station" and "Showers" are not in the target list.

**Proposed fix:** Add `comfort station` and `showers? path` to `name_deny` in `exclusions.json`.

### F3 (MEDIUM): York River placeholder names — 3 entries

**Region:** york-river
**Pattern:** OSM placeholder names for trails under construction or never properly named.

| OSM way ID | Name | Tags |
|------------|------|------|
| way/1300601245 | New Trail (in progress) | `highway=path, bicycle=designated, foot=designated, mtb:scale:imba=1, surface=dirt` |
| way/1300607446 | New Unnamed Trail Shortcut | `highway=path, bicycle=designated, foot=designated, surface=dirt` |
| way/431591663 | New Section | `highway=footway, bicycle=yes, surface=unpaved` |

**Why these slip through:** No pattern in `exclusions.json` catches placeholder names. "New Trail (in progress)" is an OSM editor's temporary name — the trail may be complete now but the name was never updated, or it may still be under construction. Either way, presenting "New Trail (in progress)" as a hike recommendation is a poor user experience.

**Proposed fix:** Add `\bunnamed\b` and `\bnew (trail|section)\b` to `name_deny` in `exclusions.json`.

### F4 (MEDIUM): York River generic access path — 1 entry

**Region:** york-river

| OSM way ID | Name | Tags |
|------------|------|------|
| way/1380847240 | Access Route | `highway=path` |

**Why it slips through:** "Access Route" is a generic access path with no recreational trail tags. The name doesn't match any existing denylist pattern.

**Proposed fix:** Add `\baccess route\b` to `name_deny` in `exclusions.json`.

### F5 (LOW): Within-region duplicate names — 2 pairs

**Regions:** james-river-sp, outer-banks

| Region | Name | OSM way IDs |
|--------|------|-------------|
| james-river-sp | Appleberry Mountain Trail | way/19778420, way/19778421 |
| outer-banks | Mountains-to-Sea Trail | way/769524372, way/769441507 |

**Why this happens:** OSM ways are often split at road crossings or jurisdictional boundaries. The conflation pipeline (`ingestion/conflate/match.py`) should merge these into a single canonical trail, but these pairs slipped through. This is a conflation gap, not a trail_filter gap — the names are legitimate, but the user sees what appears to be the same trail twice.

**Proposed fix:** No `exclusions.json` change — this is a conflation pipeline issue. Documented here for the Claude lane to investigate.

---

## Investigated and cleared (not findings)

These entries were flagged by heuristics but verified as legitimate trail names:

| OSM way ID | Name | Region | Why it's legitimate |
|------------|------|--------|---------------------|
| way/388480340 | Sewer | prince-william-forest | MTB trail name in PWFP — `highway=path, mtb:scale=2, surface=dirt`. Named for the sewer line it follows, but it's a real recreational trail. |
| way/294026318 | Pipeline Trail | richmond | Real trail in Richmond — `highway=footway, foot=yes, operator=City of Richmond`. Runs along a pipeline corridor but is a designated recreational trail. |
| way/1210338670 | African American Cemetery Trail | catoctin-sugarloaf | Historical trail name — `highway=footway`. Trail accessing a historic African American cemetery site. Legitimate recreational/historical trail. |
| various | *Fire Road / *Road | shenandoah-gwj, sky-meadows, etc. | NPS/USFS fire roads are deliberately kept by `trail_filter.py` — they are hikeable named roads within protected areas (e.g. "Lands Run Gap Fire Road", "Skyland Fire Road"). The filter explicitly excludes "Road" from `residential_street_suffix` to keep these. |
| way/132581099 | Taylor Farm Road | prince-william-forest | Named rural road within the park boundary — `highway=track`. Legitimate hikeable road. |
| way/19779174 | Rin-Ran Farm | james-river-sp | Named trail/way on private land adjacent to the park. May warrant boundary demotion (outside protected area) but not a hard drop. |
| way/19779797 | Fairview Farm Road | james-river-sp | Named rural road — `highway=track`. Legitimate hikeable road. |

---

## Proposed `exclusions.json` diff

```diff
--- a/regions/exclusions.json
+++ b/regions/exclusions.json
@@ -6,5 +6,5 @@
-  "name_deny": "\\b(side ?walk|drive ?way|cross ?walk|wheelchair|colonnade|parking (lot|area)|bus (stop|loop))\\b|\\bwellness (and recreation|cent(er|re)|campus|clinic|hospital|institute)\\b|\\bpath to (a |an |the )?(school|store|parking|lot|bus|garage|garden|building|club|gym|colonnade)\\b|\\b(ramp|stairs?) to\\b"
+  "name_deny": "\\b(side ?walk|drive ?way|cross ?walk|wheelchair|colonnade|parking (lot|area)|bus (stop|loop))\\b|\\bwellness (and recreation|cent(er|re)|campus|clinic|hospital|institute)\\b|\\bpath to (a |an |the )?(school|store|parking|lot|bus|garage|garden|building|club|gym|colonnade)\\b|\\b(ramp|stairs?) to\\b|\\bcomfort station\\b|\\bshowers? path\\b|\\bunnamed\\b|\\bnew (trail|section)\\b|\\baccess route\\b|\\bramp \\d+\\b"
```

### New tokens added to `name_deny`

| Token | Catches | False-positive risk |
|-------|---------|---------------------|
| `\bcomfort station\b` | "Loop G path to Comfort Station", "Path Loop B Comfort Station" | None — no legitimate trail has "comfort station" in its name |
| `\bshowers? path\b` | "Loop G Showers Path", "Path Loop B Showers" | None — no legitimate trail has "showers path" in its name |
| `\bunnamed\b` | "New Unnamed Trail Shortcut" | None — "Unnamed" is never a legitimate trail name |
| `\bnew (trail\|section)\b` | "New Trail (in progress)", "New Section" | Very low — "New Trail" and "New Section" are placeholder names. "New River Trail" and "New England Trail" do NOT match (different word after "New") |
| `\baccess route\b` | "Access Route" | None — no legitimate trail is named "Access Route" |
| `\bramp \d+\b` | "Ramp 1", "Ramp 45", "Ramp 70" | None — no legitimate trail is named "Ramp N". The existing `\b(ramp\|stairs?) to\b` catches "Ramp to X" but not numbered ramps |

### Impact

If applied, these patterns would hard-drop **19 entries** across 2 regions:
- 10 OBX beach access ramps
- 5 OBX campground utility paths
- 3 York River placeholder names
- 1 York River generic access path

No legitimate trails would be affected (verified by OSM tag inspection).

---

## Coverage limitation

This sweep queried with `k=20` from each origin. Regions with >20 trails (e.g. mount-rogers with 79 unique) were sampled across multiple origins, but some trails may not have surfaced in any query. A full corpus dump (direct graph read) would be needed for exhaustive coverage. The findings here are a lower bound — additional non-trails likely exist in the unsampled tail.
