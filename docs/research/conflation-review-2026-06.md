# Conflation Review — 2026-06-23

Generated after first live ingest of shenandoah-gwj pilot region.
OSM (2,873) × NPS (758) × USFS (459 from bulk file).

---

## Summary

| Pair | Auto-accept | Review | Notes |
|---|---|---|---|
| OSM × NPS | 245 | 250 | |
| OSM × USFS | 507 | 216 | USFS names are ALL-CAPS; normalize handles it |
| **Total** | **752** | **466** | |

---

## Root cause of review cases

**~90% of review failures are not wrong matches — they are the OSM segment-fragmentation problem.**

OSM stores long named trails as many disconnected `way` segments. Each segment individually has:
- Perfect name match (score = 100)
- Poor geometry agreement (hausdorff > 500m, overlap < 0.2)

...because a single 300m OSM segment only spatially overlaps a small fraction of a 10km NPS polyline.

Examples:
- "Dickey Ridge Trail" appears **5×** against the same NPS record (different OSM segments)
- "Elkwallow Picnic Ground Trail" appears **4×** against the same NPS record
- "North Fork Moormans River Trail" appears **3×** against the same NPS record

**The fix is OSM segment consolidation, not threshold tuning.** Merging all OSM ways sharing a normalized name into a single `CanonicalTrail` before conflation would:
1. Convert most score=100 review cases to auto-accept (combined geometry aligns)
2. Fix the "5× same trail in Scout results" UX issue
3. Reduce `CanonicalTrail` node count significantly (2,899 → estimated ~800–1,000)

---

## Genuine review cases (not fragmentation)

A smaller set are actual judgment calls:

### Name mismatch — Road vs Trail
OSM names the path as a road; NPS names the same physical feature as a trail.
These are same-feature conflicts requiring a sourcing decision (NPS wins on official name).

| OSM name | NPS name | Score | Hausdorff |
|---|---|---|---|
| Conway River Road | Conway River Trail | 100 | 2230m |
| Blackrock Hut Road | Blackrock Hut Trail | 100 | 387m |
| Pass Mountain Hut Road | Pass Mountain Hut Trail | 100 | 1132m |

**Decision:** auto-promote to auto-accept with `road` → `trail` name normalization
post-conflation, OR add these as manual overrides. NPS name is authoritative.

### Spur vs Main trail ambiguity
OSM carries the main-trail name; NPS has a separate "Spur Trail" record.
These are geometrically close but semantically distinct.

| OSM | NPS | Score |
|---|---|---|
| Lewis Spring Falls Trail | Lewis Spring Falls Spur Trail | 100 |
| Humpback Rocks Trail | Humpback Rocks Spur Trail | 100 |

**Decision:** do NOT auto-merge. Two CanonicalTrails: the main trail (OSM-primary)
and the spur (NPS-primary). The OSM and NPS geometries are genuinely different features.

### USFS truncated names
USFS names are often abbreviated or truncated ALL-CAPS in the EDW.
normalize_name() lowercases and strips suffixes, which catches many cases.

| OSM | USFS | Score |
|---|---|---|
| Long Mountain Trail | LONG MOUNTAIN | 100 |
| Dowells Draft | DOWELLS DRAFT | 100 |
| Massanutten Trail | MASSANUTTEN | 100 |

**Decision:** good candidates for auto-accept threshold lowering specifically for
OSM×USFS pair (or post-normalize suffix stripping on USFS names in the fetcher).

---

## Recommended actions (in priority order)

1. **OSM segment consolidation** ← highest impact. Implement before next ingest.
   Group OSM ways by normalized name → one `CanonicalTrail` per name, centroid of
   all matching geometries. Dedup in `ingestion/pipeline.py` before the load step.

2. **USFS name normalization** — strip trailing ALL-CAPS suffix words in
   `ingestion/fetch/usfs.py` before passing to conflation. `"LONG MOUNTAIN TRAIL"` →
   `"Long Mountain Trail"` (title-case + strip known suffixes).

3. **Road→Trail canonical name resolution** — in the pipeline's SAME_AS merge for
   auto-accept matches where `match_score = 1.0`, prefer the NPS `raw_name` for the
   `CanonicalTrail.name` (authority tier 1 for NPS names).

4. **Manual review of the spur/main ambiguities** (~10 cases) — these need a human
   decision; document the chosen CanonicalTrail boundaries.

---

## Threshold verdict

Current thresholds (`name_auto=85`, `overlap_auto=0.5`, `hausdorff_auto_m=80`) are
**correct** given fragmented OSM input. Do NOT loosen the geometry threshold —
that would cause false merges. Fix the geometry (consolidation) instead.

After consolidation, re-run and measure: expect auto-accept rate to rise from
~62% to ~85%+ for named named NPS trails.
