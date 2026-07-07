# Epic 023 — Capture authoritative USFS/NPS length + re-assemble NPS multi-part trails

**Status:** DONE ✅
**Phase:** A (path-to-complete.md — "substrate honest enough to build the Phase-D verdict surface on")
**Spec refs:** comaps-borrow-plan.md item **A2** (wave 1) · CLAUDE.md Rule #3 (graph holds slow/structural) · Rule #1 (source-or-silence) · Rule #7 (provenance on every belief)

> Line numbers below were read on 2026-07-06 and **may drift** — always re-grep the named
> symbol before editing, never trust a bare line number.

---

## Capability statement
Every conflated trail carries a **source-backed length** (USFS `GIS_MILES` / NPS agency
length) with an explicit `length_source`, populated even where DEM elevation is absent —
and a named NPS trail becomes **one** canonical node instead of N fragments that overwrite
each other's geometry.

## Architectural context

**Builds on:**
- The frozen `Feature` dataclass (`ingestion/conflate/match.py:80-96`) — the conflation
  currency that flows fetch → match → load.
- `graph/load.py` `load_canonical_trail` (`graph/load.py:198-247`) — **already accepts**
  `length_mi` / `length_source` / `gain_ft` / `gain_source` (params at ~`load.py:207-210`,
  SET clauses at ~`load.py:242-247`) but `ingestion/pipeline.py` calls it **without them**.
- `ingestion/usfs_convert.py` `consolidate_by_trail_no` (`usfs_convert.py:70-116`) — the
  proven "group source segments back into whole trails by a shared trail id, merge geometry
  via `unary_union`, keep one representative's props" idiom. NPS gets its own copy of this
  discipline (do **not** import/reuse across sources — see Correction 4).

**Enables:** the Phase-D verdict/ETA surface (an honest per-segment ETA needs a real length),
and removes the candidate-set inflation that degrades conflation precision on NPS land.

**⚠ Concurrent wave-1 merge collision (READ — `ingestion/pipeline.py` is an AGENTS.md
merge-sensitive seam):** Epic 026 **concurrently extends the same `Feature` dataclass**
(`ingestion/conflate/match.py:80-96`, adding `path_grade`/`psurface`/`foot_access`) **and
edits the same two `load_canonical_trail` call sites** this epic touches
(`pipeline.py:538` auto-accept, `pipeline.py:603` unmatched-spine). Epic 025 inserts a
hygiene `continue` guard immediately *before* those two calls; Epic 030 edits
`_build_canonical_id` in the same file. Epic 026's prompt already names Epic 023 as the
lane it must merge after. **Mitigations required of this builder:** (a) keep the four new
`Feature` fields grouped adjacently (one contiguous hunk) to minimise the conflict; (b)
name this collision explicitly in the PR **Merge-risk** section; (c) do **not** merge blind
against 026 — whichever of 023/026 lands second rebases on the first (they cannot both
merge without a manual reconcile on `match.py` + `pipeline.py:538/603`).

**Does NOT include:**
- **Any DEM / 3DEP length work.** `t.length_mi` is **null across the entire corpus today**
  (see Correction 1) — there is no derived length to deprecate; the gap is total. This epic
  does **not** compute length from geometry or elevation.
- **`graph/load.py` edits.** The loader already accepts and guards the four fields; we only
  start *passing* them. (This means an absent length is a no-op, not an explicit null-clear —
  a documented asymmetry vs. `route_geom_wkt`; see AC-4.4 / Open Questions.)
- **Cross-row same-name re-assembly** of separate NPS/OSM features into one long named route.
  That is the deferred E1 / roadmap-030 work (borrow-plan §E1, lines 199-207) and carries the
  false-merge "map-nonsense" risk the project deliberately backed away from. This epic only
  collapses a **single source feature's multipart geometry** into one `Feature`.
- **Gain fabrication.** `gain_ft` is plumbed through end-to-end but populated **only** if an
  agency source actually exposes a gain attribute; otherwise it stays `None` (Rule #1). Do not
  derive gain here.

### Binding verifier corrections (from comaps-borrow-plan.md A2 — the builder cannot read the plan; these are authoritative)

1. **There is NO "3DEP length to deprecate."** `usgs_3dep` emits gain/profile but **no
   length**; `t.length_mi` is written **nowhere** today. The field is null corpus-wide, so the
   length gap is *total*, not a fallback improvement. Do not frame or code around a pre-existing
   derived length.
2. **NPS harm is NOT duplicate SourceRecords.** `_sr_uid(NPS, OBJECTID, name)` is identical for
   every part of one MultiLineString, so `load_source_record` MERGEs them idempotently into
   **one** SourceRecord. The real harm: all N parts share **one `canonical_id`**, so
   `load_canonical_trail` runs N times (`pipeline.py:603`) each overwriting `route_geom_wkt` —
   the surviving node keeps only the **last** part's geometry (last-fragment-wins) — **and** the
   matcher scores N agency features against every OSM candidate (candidate-set inflation). The
   fix is to emit **one `Feature` per source trail**, not to dedupe SourceRecords.
3. **Matched-trail length is a CROSS-SIDE copy, not pass-through.** For an auto-accept match the
   canonical node is built from the **OSM spine `m.a`** (`pipeline.py:534-548`) while the
   authoritative length lives on the **agency side `m.b`**. So length must be copied
   `m.b → canonical` with `length_source = m.b.source`, not read from `m.a`.
4. **`generator/feature_merger.cpp` is inspirational only.** CoMaps merges by geometry endpoint
   with **no name/identity gate** and picks the *shortest* continuation (a rendering
   generalizer) — ported as-is it fuses distinct trails. **Copy our own `consolidate_by_trail_no`
   discipline**; do not port the C++.
5. **Never silently reconcile conflicting agency-vs-derived lengths.** Always write
   `length_source` alongside `length_mi`. Centerline vs. round-trip disagreement is real —
   record it honestly (per-source, each normalized independently — the Stage-1 rule), never
   average or silently overwrite.

---

## Stories

### S1 — Carry length/gain on the frozen `Feature`

**Given** the conflation currency `Feature` (`ingestion/conflate/match.py:80-96`) carries
`name`, `geom`, `source`, `ref`, `way_type` and nothing about length,
**When** a fetcher reads an authoritative agency length/gain,
**Then** it can attach it to the `Feature` so it survives to the loader.

**AC-1.1:** `Feature` gains four keyword fields, declared **after** `way_type` to preserve
positional construction: `length_mi: float | None = None`, `length_source: str | None = None`,
`gain_ft: float | None = None`, `gain_source: str | None = None`.
**AC-1.2:** Every existing positional construction still type-checks and runs unchanged — e.g.
`Feature("Old Rag Trail", LINE, "osm")` (see `tests/test_conflate.py:52`) yields all four new
fields `None`. A test asserts this.
**AC-1.3:** `Feature` remains `@dataclass(frozen=True)`; the new fields are immutable.
**AC-1.4:** `mypy` (via `make check`) is clean; no field is `Any`-typed.

### S2 — Capture USFS `GIS_MILES` as an authoritative length

**Given** `ingestion/fetch/usfs.py` reads `TRAIL_NO` at `usfs.py:94` but **ignores** `GIS_MILES`
(the module docstring at `usfs.py:21` explicitly names it as a known-but-unread field),
**When** it builds a USFS `Feature`,
**Then** the trail carries `length_mi` (miles) with `length_source = "USFS"`.

**AC-2.1:** `usfs.fetch` reads `GIS_MILES` from feature props and sets `Feature.length_mi`
(float, miles) and `Feature.length_source = "USFS"` **only** when the value parses to a number
`> 0`. Missing / blank / non-numeric / `<= 0` → `length_mi = None`, `length_source = None`
(Rule #1 — never emit `0.0` as a "length").
**AC-2.2:** `usfs_convert.consolidate_by_trail_no` (`usfs_convert.py:70-116`) aggregates
`GIS_MILES` to a **whole-trail** total on the consolidated feature's props, so a trail exported
as N maintenance segments reports the full length, not one segment's. Segments with no usable
`GIS_MILES` contribute nothing; if **no** segment in a group has a usable value the field is
left absent (not `0`). Single-segment and unkeyed-passthrough features keep their original value
unchanged.
  - **VERIFIED — implement the SUM branch (no data access required):** the raw USFS
    `S_USA.TrailNFS_Publish` shapefile was inspected against this epic — `GIS_MILES` is
    **per-feature / per-segment**, not a per-trail total replicated on every row (e.g.
    `TRAIL_NO` 509 has 18 national rows with *distinct* values 0.174 / 1.35 / 0.627 / 6.855 /
    …). Therefore **SUM `GIS_MILES` across a `TRAIL_NO` group is correct**; single-feature
    groups pass through unchanged. State in the PR body: "GIS_MILES is per-segment (verified
    against raw S_USA.TrailNFS_Publish); implemented the sum branch."
  - **Do NOT try to re-verify from `data/usfs/trails.geojson`.** That file is gitignored (absent
    from your fresh worktree) **and** is already output *after* `consolidate_by_trail_no` — it
    carries exactly ONE `GIS_MILES` per trail, so it structurally *cannot* disambiguate
    per-segment vs. per-trail. The read-only main-tree copy at
    `/Users/joshcrow/Documents/GitHub/hike-app/data/usfs/trails.geojson` is likewise consolidated
    and cannot settle the branch — the finding above already settles it. The raw shapefile
    (geopandas + ~300 MB) is not present in the worktree either.
  - **Same-`TRAIL_NO` cross-forest caveat (known limitation, do NOT fix here):** `TRAIL_NO` is
    not globally unique (raw `509` maps to 18 distinct trails across ADMIN_ORGs). Summing is safe
    **only** because `scripts/fetch_usfs.py` clips to the region bbox *before* consolidating. If a
    region bbox ever spans two forests sharing a `TRAIL_NO`, geometry *and* now length fuse — a
    pre-existing geometry hazard whose blast radius this epic widens to length. Flag as a known
    limitation in the PR; out of scope to fix.
**AC-2.3:** A USFS `Feature` carries **one** length per named trail — the fetcher emits **one
`Feature` per consolidated source feature** (see S3; this prevents the whole-trail length from
being duplicated onto every exploded segment).

### S3 — One `Feature` per source trail (collapse the multipart explosion; re-assemble NPS)

**Given** `ingestion/fetch/nps.py:86-92` explodes a MultiLineString into **N** `Feature`s that
share one `name` and one `OBJECTID` `ref` (and `usfs.py:102-106` does the same per-segment),
**When** the fetcher returns features,
**Then** a single source trail becomes exactly **one** `Feature` with the merged geometry.

**AC-3.1:** Given one ArcGIS/GeoJSON feature whose geometry is a MultiLineString of N parts,
the fetcher returns **exactly one** `Feature` whose geometry contains all N parts (merged via
`shapely.ops.unary_union`, mirroring `usfs_convert.py:97-114`), **never** N `Feature`s. This
holds in both `nps.fetch` and `usfs.fetch`.
**AC-3.2:** Consolidation is keyed on a **single source feature's own identity** (NPS: its
`OBJECTID`; USFS: its already-consolidated `TRAIL_NO` feature), so two genuinely distinct source
features are **never** merged. Cross-row same-name assembly is explicitly out of scope
(Correction / Does-NOT-include) — do not group by name across features.
**AC-3.3:** After the fix, `_build_canonical_id(source, ref, name)` and `_sr_uid(...)`
(`pipeline.py:80-96`) produce **one** `canonical_id` per named NPS trail, so
`load_canonical_trail` runs **once** and `route_geom_wkt` holds the whole geometry — the
last-fragment-wins overwrite (Correction 2) is gone. A pipeline-level test asserts a MultiLineString
NPS input yields one canonical node with all parts, not N.
**AC-3.4:** The merged geometry is accepted downstream unchanged — `assemble_geometry`
(`ingestion/route.py:136`) already collects LineString **and** MultiLineString parts; a test
confirms a merged-MultiLineString `Feature` survives `assemble_geometry` to a non-null route.
**AC-3.5:** The NPS bbox / name-selection behaviour is preserved: nameless features are still
dropped (`nps.py:79-81`), and the representative name is chosen like `usfs_convert` (first part
with a usable name). Input order is preserved by first occurrence.

### S4 — Pass length/gain through the loader (cross-side for matched, direct for spine)

**Given** `ingestion/pipeline.py` calls `load_canonical_trail` at **`pipeline.py:538`**
(auto-accept match, node built from OSM spine `m.a`) and **`pipeline.py:603`** (unmatched spine
feature) without any length/gain,
**When** it loads,
**Then** the authoritative agency length reaches the canonical node with its source.

**AC-4.1:** At the matched call (`pipeline.py:538`), `load_canonical_trail` is passed the
length/gain from **whichever side carries it, agency-first**: `length_mi = m.b.length_mi if
m.b.length_mi is not None else m.a.length_mi`, and `length_source` **follows the chosen side**
(so it records the actual agency, never a bare `m.a` when `m.a` supplied it). Same pattern for
`gain_ft`/`gain_source`. **Why not just `m.b`:** today the spine is always OSM (`registry.spine`,
`pipeline.py:662`), so `Match.a` = OSM spine and `Match.b` = agency (`match.py`), and the length
lives on `m.b` (Correction 3). But AC-4.2 asserts an agency source *can* be the region spine; in
that (latent) case `m.a` = agency (has length) and `m.b` = OSM (`None`), so a bare `m.b` read
would silently drop the authoritative length on a matched agency-spine trail. The prefer-either
rule is correct in both worlds. (If you instead prefer a hard precondition, you MAY assert
"USFS/NPS are never `role=spine`" and read `m.b` only — but then state that precondition
explicitly and note AC-4.2's agency-spine case becomes unmatched-only.)
**AC-4.2:** At the unmatched-spine call (`pipeline.py:603`), the same four fields are passed from
`feat` itself — this covers the case where an agency source *is* the region's spine (its length
travels directly).
**AC-4.3:** When neither side has a length (`length_mi is None`), no length is written — the
loader already guards `if length_mi is not None` (re-grep the symbol; the guard is at
~`load.py:240`, with the `length_source` pairing at ~`load.py:242`), so passing `None` is a
no-op. No fabricated `0.0`, no stale carry-forward introduced by this epic.
**AC-4.4:** `length_source` is **always** non-empty whenever `length_mi` is set (a test asserts
the pair travels together). This epic performs **no** reconciliation of agency-vs-derived length
(none exists — Correction 1); provenance stays explicit so any *future* reconciliation is a
deliberate, sourced decision (Correction 5).

---

## Definition of Done
- [ ] All ACs covered by at least one passing test (unit tests for `Feature`, `usfs.fetch`,
      `usfs_convert.consolidate_by_trail_no` GIS_MILES aggregation, `nps.fetch` collapse; a
      DB-free `pipeline`-level test that a MultiLineString NPS feature yields one canonical node
      with length/source passed through — mirror `tests/test_pipeline.py` fixture style, no
      `@pytest.mark.neo4j` required for the wiring assertions).
- [ ] `make check` green (`ruff format --check` + ruff + mypy + `pytest -m "not neo4j"`).
- [ ] GIS_MILES branch documented in the PR body as **spec-verified: per-segment → sum**
      (settled above against the raw `S_USA.TrailNFS_Publish`; no worktree data access required —
      the consolidated `data/usfs/trails.geojson` cannot disambiguate it).
- [ ] **Inertness disclosed in the PR body:** the GIS_MILES aggregation lives in
      `usfs_convert.consolidate_by_trail_no`, which runs **offline inside `scripts/fetch_usfs.py`
      (~:125)**, NOT in the ingestion pipeline. The existing checked-out `data/usfs/trails.geojson`
      was generated *before* this change and carries only one representative segment's length
      (multi-segment trails currently undercount). The whole-trail length therefore reaches the
      live corpus **only after an operator re-runs `scripts/fetch_usfs.py` to regenerate the
      geojson AND re-ingests** — the code change is inert on the pre-consolidated file. State this
      so the "source-backed length" claim is not read as already-live. (`scripts/fetch_usfs.py`
      needs no edit — it just calls the modified `consolidate_by_trail_no`; keep it out of
      `files_touched`.)
- [ ] Targeted self-review agent run over the diff; every CRITICAL fixed, MODERATE+ documented.
- [ ] Merge-sensitive seam (`ingestion/pipeline.py`) called out in the PR body — **including the
      concurrent-Epic-026 collision** on `Feature` + `pipeline.py:538/603` (see Architectural
      context): 023/026 cannot both merge blind; second to land rebases on the first.
- [ ] Committed and pushed; PR opened into `main`; epic copied into `docs/epics/` and a row
      added to `docs/epics/README.md` (status `REVIEW`).
