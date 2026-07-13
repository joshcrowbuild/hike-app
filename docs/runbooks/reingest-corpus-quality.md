# Runbook — "Map routes are nonsense" triage + corpus re-ingest

**Owner:** ingestion · **Status:** fixes landed in code; **a re-ingest is required** to
take effect (geometry is baked into Aura at ingest).

Investigation of the live Shenandoah corpus ("map routes are nonsense"). PM triage
narrowed it to three leads; this is what each turned out to be and how it was fixed.

## Diagnosis

Ground-truthed against the **live Aura data** (1458 trails) + the live API + an
in-browser render of the actual USGS topo tiles.

| Lead | Verdict | Evidence |
|---|---|---|
| **3 — basemap alignment** | **Ruled out.** | A standalone MapLibre render with the *exact* `USGSTopo/.../tile/{z}/{y}/{x}` template + a real route showed the route sitting **perfectly on** the topo (US-340, contours, place names). The `{z}/{y}/{x}` order matches ArcGIS REST `tile/{level}/{row}/{col}` and MapLibre's XYZ scheme (EPSG:3857). No projection bug. |
| **1 — corpus quality (dominant)** | **Confirmed.** | The feed literally suggested **"Path to School", "Snake Road", "Leach Road"** as hikes. The Overpass spine pulls *any named* `path/footway/track/bridleway/steps` and **discarded the discriminating tags**. Real tags: "Leach Road" `access=private`; "Path to School" `highway=footway`. But "Snake Road" / "Compton Gap Road" are `highway=track` — legit fire-road hikes — so a name-only filter would wrongly kill them. |
| **2 — conflation segment-grouping** | **Confirmed.** | `consolidate_osm_segments` merged ways **solely by normalized name**, unioning disconnected ways into one gappy MultiLineString. 213 multi-segment trails; the gappy ones: "Rivanna Trail (RTF Spur)" 42 segs / **823 m gap**, "Appalachian Trail" 18 segs / **326 m gap**. Contiguous ones (RedFields, Hillandale) were 0 m gap — correct merges. So the fix must **split disconnected** components, not stop merging. |

## Fixes (in this change)

1. **Trail-worthiness filter** (`ingestion/trail_filter.py`, wired into
   `ingestion/fetch/osm.py`). Captures the OSM tags (previously discarded) and drops
   urban/private non-trails by tag (`access=private/no`, `footway=sidewalk/crossing`),
   a tight name denylist (sidewalk / driveway / "path to school" connectors), and
   2-vertex footway stubs — **keeping** unpaved fire-road `track`s. Conservative by
   design (high precision); residential footway loops with innocuous names need a
   park-boundary signal (follow-up). *Impact on the real region fetch: 195 non-trail
   ways filtered.*
2. **Connectivity-aware consolidation** (`ingestion/pipeline.py`). Same-name ways are
   clustered into spatially-connected components (≤ 40 m gap); each disconnected
   component becomes its own `CanonicalTrail` with a stable, unique id (the min member
   way id), while genuinely-contiguous segments still merge into a clean `LineString`.
   *Impact: 108 same-name groups split into their real components (2678 → 1532).*

## Re-ingest (apply the fixes to Aura)

> **Superseded (2026-07-13): the manual wipe in step 2 is no longer needed for filter
> drift.** `prune_stale_trails` now keys on a per-run marker (`ingest_run_id`, stamped
> on every node a run touches), so a node a *tightened* filter newly excludes is
> pruned automatically on the next healthy re-ingest — including legacy nodes that
> predate the marker (no `ingest_run_id` = stale by construction). Previously this did
> **not** self-heal: `ingest_version` is a constant per region, so drift victims were
> invisible to the version-keyed prune and needed exactly this wipe (or a manual
> scoped delete, as on 2026-07-12). Keep step 2 only for structural resets a prune
> can't express — e.g. the canonical-id scheme change below, where the old ids must
> vanish wholesale. For ordinary filter tightening: just re-run step 3 and let the
> guarded prune retire the drops.

Both fixes change what gets written at ingest, so the live graph keeps the old
geometry until a re-ingest. The connectivity change also mints **new** canonical ids
for split components (`ct:osm:appalachian-trail` → per-section `ct:osm:way_…`), so the
stale name-slug trails must be cleared, not left orphaned.

1. Point `NEO4J_URI/USER/PASSWORD` at Aura (`.env`), apply schema if needed
   (`python scripts/apply_schema.py`).
2. Clear the world corpus (world nodes only — the personal overlay is untouched):
   ```cypher
   MATCH (n) WHERE n:CanonicalTrail OR n:SourceRecord OR n:Segment OR n:Trailhead
   DETACH DELETE n
   ```
3. Re-run ingestion: `make ingest` (or `python -m ingestion.pipeline --region shenandoah-gwj`
   then `python -m ingestion.ingest_trailheads --region shenandoah-gwj`).
4. Verify: `/health` graph counts drop (non-trails removed), and a previously-gappy
   trail (e.g. the AT) now serves contiguous `LineString` sections instead of one
   `hedged` 18-part MultiLineString.

> Personal `Episode.trail_id`s that pointed at a name-slug OSM trail that got split
> will need re-pointing; negligible at pilot scale (mostly anonymous browsing).

See [`../../CLAUDE.md`](../../CLAUDE.md) for the source-or-silence + access-control
rules this upholds (no fabricated geometry; world-only wipe in step 2).
