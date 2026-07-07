# Epic 036 — Deterministic OSM PBF transport (pyosmium; additive, default not flipped)

**Status:** REVIEW
**Phase:** A (corpus / ingestion — same phase family as Epics 023–027)
**Spec refs:** `/Users/joshcrow/.hike-lanes/oss-sprint/research/pyosmium-extracts.md` (the binding research brief — read end-to-end) ·
CLAUDE.md **Rule #1** (source-or-silence) · **Rule #3** (graph holds slow/structural only) ·
**Rule #6** (degrade-and-disclose) · source-seams **SS-2** (wrap proven output) · **SS-3** (spine is a declared role) · **SS-10** (from_config: blank-fails-loud / missing-degrades)
**Depends on:** Epic 034 (shared `orchestration/config.py` — a new `Settings` field; 034 edits `config.py` near lines 82/209 while this lane adds a field near 126/225 → a **real conflict surface**). **Merge AFTER 034.** · Epic 035 is **independent — no shared edit surface**: 035 only *adds* a sibling `fetch_water` to `ingestion/fetch/osm.py`, and this lane never edits that file — it only *imports* the pre-existing `fetch` and `_TRAIL_HIGHWAYS` (both predate 035). This lane **may merge in any order relative to 035** (write the parity test against the current `osm.fetch`, which 035 does not change). No idle wait on 035.

> Line numbers below were read on **2026-07-07** and **may drift** — always re-grep the named
> symbol before editing, never trust a bare line number.

---

## Capability statement
The corpus gains a **second, deterministic OSM geometry-spine transport**: it reads trails from a
local Geofabrik `.osm.pbf` extract with **pyosmium** (`FileProcessor().with_locations()` +
`WKTFactory`) and emits the **byte-identical `Feature` contract** the Overpass transport produces
today — behind a new `OsmPbfSource` registered as `"osm-pbf"`. It is **additive**: the default
`ADVENTURE_CORPUS_SOURCES` still names `"osm"` (Overpass), so nothing cuts over this sprint. A
committed synthetic-PBF **parity test** is the guard that the two transports classify identically,
so a later cutover cannot drift silently.

## Architectural context

**Builds on:**
- `ingestion/fetch/osm.py` — the Overpass transport this mirrors. The trail `fetch(bbox, *,
  client, timeout)` returns `Feature`s backed by Shapely `LineString`s (`osm.py:36-105`); the
  trail-way filter is `_TRAIL_HIGHWAYS = "path|footway|track|bridleway|steps"` (`osm.py:33`); the
  trail-worthiness gate is `is_trail_worthy(tags, coords)` (`osm.py:76`, `ingestion/trail_filter.py:78`);
  the ref scheme is `f"{el['type']}/{el['id']}"` (`osm.py:79`); the captured attributes are
  `way_type = tags.get("highway")`, `path_grade`, `psurface`, `foot_access` via
  `classify_path_grade/classify_surface/classify_foot_access` (`osm.py:90-95`,
  `ingestion/classify.py:23,131,195`).
- `ingestion/sources/usfs.py` — the **exact template** for a local-bulk-file geometry source:
  `from_config` reads a path from `Settings` and fails loud only on an explicitly-blank value
  (`usfs.py:42-51`), while a runtime missing/corrupt file degrades to `[]` inside `fetch`
  (`usfs.py:53-60`). `ingestion/fetch/usfs.py` is the local-file, bbox-clipped transport
  precedent (`usfs.py:74-142`), defaulting to `data/usfs/trails.geojson` (`usfs.py:37`).
- `ingestion/sources/registry.py` — `SOURCE_REGISTRY` (`registry.py:30-36`) is the one place
  sources are registered; `spine()` resolves the spine by **declared role**, not by name
  (`registry.py:65-77`), so swapping `"osm"`→`"osm-pbf"` in the config is all a cutover needs.
- `ingestion/sources/base.py` — the `CorpusSource` contract (`base.py:115-192`), `Region`
  (`base.py:68-77`, `bbox = (south, west, north, east)`), and the re-exported `Feature`.
- `regions/usfs_manifest.json` + `scripts/fetch_usfs.py` — the manifest + fetch-script pattern to
  mirror for the state-PBF download (URL + vintage + checksum recorded, the artifact never
  committed under gitignored `data/`).
- `ingestion/pipeline.py` — `run_pipeline` fetches the spine via `spine_source.fetch(region)`
  and runs `consolidate_osm_segments` + `_check_fetch_sanity` on it (`pipeline.py:870-880`). Since
  `OsmPbfSource` emits identical `Feature`s, **the pipeline needs no edit** — the swap is entirely
  behind the `CorpusSource.fetch` seam.

**Enables:** a future cutover of the spine to a deterministic, cacheable, offline OSM read
(pin an OSM vintage; remove the three-mirror Overpass failover); the Epic-024 B2 composite
build-ID's OSM-date component; named long-trail identity via route relations. **None of those are
in this epic.**

**Does NOT include:**
- **No flip of `ADVENTURE_CORPUS_SOURCES`.** `"osm"` (Overpass) stays the default spine —
  additive, no cutover this sprint (the Epic-026 "persisted for a later phase; nothing reads them
  yet" precedent). The PR body must disclose that `"osm-pbf"` is registered but **not** in the
  default source list, so nothing in the shipped default pipeline calls it yet.
- **No `ingest_version` change** (the region-scoped prune anchor — epic-024 binding correction
  A4.1). The PBF replication-timestamp vintage is a *new recorded fact* in the manifest, never a
  repurposing of the prune key.
- **No PBF-vintage → `/health` plumbing, and no route-relation long-trail identity.** Both are
  explicit follow-ons named in the brief (§5, §6).
- **No `osmium-tool` (GPL binary) dependency** — bbox clip is pure-pyosmium (`shapely` `.bounds`
  vs `Region.bbox`). The optional `osmium extract` pre-clip is a documented escape hatch only,
  **not built** here.
- **No 386 MB Geofabrik state-PBF download in CI.** The parity test reads a tiny **committed
  synthetic** `.osm.pbf` fixture only — the key unattended-feasibility guard.
- **No `ingestion/pipeline.py` edit** (merge-sensitive shared seam; the swap is transparent).

### Binding decisions & guards (authoritative — the builder cannot re-derive these)

1. **`"osm"` stays the default; `"osm-pbf"` is additive.** Register the new source; do **not**
   touch the `corpus_sources` default tuple (`orchestration/config.py:125,186`). The one-region
   diff-and-flip rollout (brief §7) is a follow-on, not this PR.
2. **Byte-identical `Feature` contract.** The new transport must call the **same** gate and
   classifiers as `osm.py`: `is_trail_worthy(tags, coords)`, then `_TRAIL_HIGHWAYS` highway
   filter + `"name" in tags`, then emit `Feature(name=tags["name"], geom=LineString(...),
   source="OSM", ref=f"way/{id}", way_type=tags.get("highway") or None,
   path_grade=classify_path_grade(tags), psurface=classify_surface(tags),
   foot_access=classify_foot_access(tags))`. `source` is `"OSM"` (same spine identity so
   downstream conflation/canonical treatment is unchanged). **Import the real `is_trail_worthy`
   and `classify_*` — never re-implement them.**
3. **`.with_locations()` + `WKTFactory` are the one genuinely-new mechanic.** An OSM way stores
   node **IDs** only; `FileProcessor(path).with_locations()` builds the node→(lat,lon) index so
   `WKTFactory().create_linestring(way)` can resolve geometry. Parse the WKT with
   `shapely.wkt.loads` into the same `LineString` type `osm.py:83` builds. A way whose resolved
   geometry has `< 2` coords is skipped (parity with `osm.py:71-72`).
4. **bbox clip is pure-pyosmium, bounds-intersect.** Keep a way iff its shapely `.bounds`
   (min_lon, min_lat, max_lon, max_lat) **rectangle-overlaps** `Region.bbox`
   (south, west, north, east) — i.e. `not (maxx < west or minx > east or maxy < south or
   miny > north)`. Bounds-intersect (not any-vertex-inside) is deliberate: it never drops a long
   trail that *crosses* the bbox without a vertex inside it. No `osmium-tool`.
   **Boundary-membership caveat (disclose in the PR, do NOT try to assert in the parity test):**
   bounds-intersect is a deliberate **superset** of Overpass's server-side geometry-intersect — it
   keeps a way whose bounding box overlaps the bbox even if the line itself never enters (e.g. an
   L-shaped detour), so on real state PBFs `"osm-pbf"` can emit **more** boundary ways than Overpass
   for the same region. The AC-5.2 parity test runs on a controlled synthetic fixture and therefore
   proves only **classify + gate + ref + geometry** parity, **never bbox-membership** parity. No
   production impact this sprint (default not flipped); it is a cutover-time count-diff item (brief
   §7's one-region diff-and-flip), not something the parity guard asserts. Do not let the
   "byte-identical `Feature` contract" framing be read as proving boundary-set identity.
5. **SS-10 config split (mirror USFS exactly).** `from_config` reads the PBF path from `Settings`;
   an **explicitly-blank** value fails loud (`ValueError`), an **unset** value falls back to the
   transport's default path, and a **runtime missing/corrupt** file degrades to `[]` inside
   `fetch` (Rule #6). Copy the shape of `UsfsSource.from_config` (`usfs.py:42-51`) verbatim in
   spirit.
6. **Missing/partial PBF must never fabricate geometry.** A missing file → `[]` (source-or-
   silence). The existing `_check_fetch_sanity` floor (`pipeline.py:514-522`) is the truncation
   guard on the pipeline side; the transport itself must fail the read loudly (raise) on a
   **corrupt** PBF rather than returning a partial set that looks valid — but the *adapter*
   catches any raise and degrades to `[]` (Rule #6), exactly like `UsfsSource.fetch`
   (`usfs.py:53-60`). (Corrupt-file honesty lives in the transport's own read; adapter is the
   degrade boundary.)
7. **Vintage is recorded, not wired.** `scripts/fetch_osm_pbf.py` records the state PBF's
   `osmosis_replication_timestamp` (read via `osmium.io.Reader(path).header().get(
   "osmosis_replication_timestamp")`) into `regions/osm_pbf_manifest.json`. Threading it into
   `/health` is a follow-on; do **not** touch `ingest_version`.
8. **Single-path config this sprint; region→state auto-mapping is a follow-on.** The manifest MAY
   list multiple state entries (VA, NC) with URLs, but the source reads **one** configured PBF
   path (`ADVENTURE_OSM_PBF`), mirroring USFS's single `ADVENTURE_USFS_GEOJSON`. Automatic
   region→state file selection is deferred (brief §7 rolls out on one region, Shenandoah/VA).

### License & attribution (binding — the LICENSE GATE)
- **pyosmium (pip `osmium`) = BSD-2-Clause → PORT-OK as a normal dependency.** No source code is
  copied from it; it is added to `pyproject.toml` optional-deps `ingestion` like `shapely`. No
  file-header attribution required for a normal pip dependency.
- **`osmium-tool` CLI = GPL → NEVER ported and NOT used here.** The bbox clip is pure-pyosmium
  (Guard 4). Do not shell into or copy any `osmium-tool` code.
- **Geofabrik OSM data = ODbL — already compliant** (same class as the trail geometry we ingest;
  `source="OSM"` travels with every `Feature`). Geofabrik terms: free, attribution, no hammering
  (download once + cache; do **not** download in CI).
- **No third-party source code enters the repo in this epic.** The reference material
  (`/Users/joshcrow/.hike-lanes/oss-sprint/repos/*`, pyosmium docs) is read-and-re-derive; the
  only new dependency is the BSD `osmium` wheel.

---

## Stories

### S1 — pyosmium transport (`ingestion/fetch/osm_pbf.py`)

**Given** `ingestion/fetch/osm.py::fetch` fetches trail ways from Overpass and emits `Feature`s,
**When** a caller passes a region bbox and a local `.osm.pbf` path,
**Then** it gets the **same** `Feature` set the Overpass path would, read deterministically from
the local file.

**AC-1.1:** `fetch(bbox, *, pbf_path=None, factory=None) -> list[Feature]` is added to a new
`ingestion/fetch/osm_pbf.py`, signature-parallel to `osm.py:36`. `bbox` is
`(south, west, north, east)` (base.py:73 convention). `pbf_path=None` → a module `_DEFAULT_FILE =
Path("data/osm/region.osm.pbf")` (mirror `usfs.py:37`). Missing file → `[]` with a warning naming
the fetch script (mirror `usfs.py:85-91`). A test drives a missing path and asserts `[]`.
**AC-1.2:** The read uses `osmium.FileProcessor(str(path)).with_locations()` and iterates ways
(`o.is_way()`); geometry comes from `osmium.geom.WKTFactory().create_linestring(o)` parsed with
`shapely.wkt.loads`. A way whose parsed geometry has `< 2` coords is skipped (parity with
`osm.py:71-72`). A way with no geometry / a geometry-resolution error is skipped, not raised on
(logged at debug). A test over the synthetic fixture asserts a valid multi-node way yields a
`LineString` `Feature`.
**AC-1.3:** The trail filter is **identical** to Overpass: keep a way iff `tags.get("highway")`
matches one of `path|footway|track|bridleway|steps` (reuse the `_TRAIL_HIGHWAYS` values — import
the constant from `ingestion.fetch.osm` or re-derive a shared frozenset, no divergent copy) **and**
`"name" in tags` **and** `is_trail_worthy(tags, coords)` returns `True`. A test includes a
`highway=residential` way, an unnamed `highway=path` way, and a non-trail-worthy way, and asserts
all three are dropped.
**AC-1.4:** Each kept way emits `Feature(name=tags["name"], geom=<LineString>, source="OSM",
ref=f"way/{o.id}", way_type=tags.get("highway") or None,
path_grade=classify_path_grade(tags), psurface=classify_surface(tags),
foot_access=classify_foot_access(tags))` — importing the real `is_trail_worthy` and `classify_*`
(Guard 2). `tags` is `dict(o.tags)`. A test asserts the emitted `Feature` carries the classified
`path_grade`/`psurface`/`foot_access` for a way tagged `sac_scale`/`surface`/`access`.
**AC-1.5:** bbox clip is bounds-intersect per Guard 4 (pure shapely `.bounds`, no `osmium-tool`).
A test with a way wholly outside the bbox asserts it is dropped, and a way crossing the bbox with
**no vertex inside** asserts it is kept.
**AC-1.6:** A `data/osm/` layout note in the module docstring states the file is gitignored,
obtained via `scripts/fetch_osm_pbf.py`, and is ODbL Geofabrik data. The docstring names the
`.with_locations()` node-index mechanic and the BSD pyosmium dependency.

### S2 — Source adapter (`ingestion/sources/osm_pbf.py`)

**Given** `UsfsSource` is the local-bulk-file `CorpusSource` template (`usfs.py`),
**When** the registry instantiates the PBF source from config,
**Then** an `OsmPbfSource(role=spine, tier 2)` fetches via the S1 transport, degrading to `[]` on
any runtime failure.

**AC-2.1:** `OsmPbfSource(CorpusSource)` declares `name = "osm-pbf"`,
`kind = SourceKind.geometry`, `role = ConflationRole.spine`, `authority_tier = 2` — the same
declarations as `OsmSource` (`osm.py` source, lines 27-31), so it is a drop-in spine. Construction
passes `CorpusSource._validate` (a test instantiates it and asserts `.role is
ConflationRole.spine`).
**AC-2.2:** `from_config(settings)` reads `settings.osm_pbf_path` (the new S3 field). A value that
is present but blank (`str(raw).strip() == ""`) raises `ValueError` naming `ADVENTURE_OSM_PBF`
(mirror `usfs.py:44-50`, SS-10). Unset (`None`) is passed through so the transport uses its default
path. A test covers blank→`ValueError` and `None`→constructed source.
**AC-2.3:** `fetch(region)` calls the S1 transport with `region.bbox` and the configured path, and
returns `[]` on **any** exception (the adapter is the degrade boundary, Rule #6 — mirror
`usfs.py:53-60`). A test injects a transport that raises and asserts `fetch` returns `[]`, not a
raise.
**AC-2.4:** An injectable seam keeps the adapter test network-/file-free: the transport function
(or a `factory`) can be passed into the constructor so a test can drive `fetch(region)` without a
real PBF on disk (parity with `OsmSource`'s injectable `client`, `osm.py` source line 33).

### S3 — Registry + config wiring (`registry.py`, `orchestration/config.py`)

**Given** `SOURCE_REGISTRY` is the single registration point and `Settings` holds source paths,
**When** an operator names `"osm-pbf"` in `ADVENTURE_CORPUS_SOURCES` and sets `ADVENTURE_OSM_PBF`,
**Then** the pipeline resolves and runs the PBF spine, while the default config is unchanged.

**AC-3.1:** `SOURCE_REGISTRY` gains `"osm-pbf": OsmPbfSource` (`registry.py:30-36`). `"osm"`
(Overpass) **remains** registered and remains the default spine. A test asserts both keys resolve
and that `known_source_names()` includes `"osm-pbf"`.
**AC-3.2:** `Settings` gains `osm_pbf_path: str | None = None` (`orchestration/config.py`), read in
`from_env` from `ADVENTURE_OSM_PBF` **kept raw** (no `or None`) so an explicitly-blank value
reaches `OsmPbfSource.from_config` to fail loud — verbatim the `usfs_geojson_path` treatment
(`config.py:126,222-225`). A field comment states the additive-default-not-flipped decision. A
test builds `Settings.from_env({"ADVENTURE_OSM_PBF": ""})` and asserts the blank survives to the
field (so `from_config` can raise).
**AC-3.3:** `ADVENTURE_CORPUS_SOURCES` default is **unchanged** (`("osm", "nps", "usfs",
"usgs-3dep")`, `config.py:125,186`). A test asserts `Settings.from_env({})` still yields `"osm"`
(not `"osm-pbf"`) as its geometry spine name.

### S4 — Manifest + fetch script (`regions/osm_pbf_manifest.json`, `scripts/fetch_osm_pbf.py`)

**Given** `regions/usfs_manifest.json` + `scripts/fetch_usfs.py` are the reproducible-download
pattern,
**When** an operator runs the fetch script,
**Then** the state PBF is downloaded to gitignored `data/osm/`, and its source URL + replication
vintage are recorded in the checked-in manifest — the PBF itself never committed.

**AC-4.1:** `regions/osm_pbf_manifest.json` lists at least the Virginia state extract
(`download.geofabrik.de/north-america/us/virginia-latest.osm.pbf`) with `source_url`,
`replication_timestamp` (`null` until an operator records it — source-or-silence, never
fabricated, mirroring `usfs_manifest.json`'s `null` vintage/sha), and `output`
(`data/osm/virginia-latest.osm.pbf`). A `_comment` explains the ODbL/Geofabrik terms and the
"download once, cache, no hammering" rule. NC MAY be listed as a second entry.
**AC-4.2:** `scripts/fetch_osm_pbf.py` mirrors `scripts/fetch_usfs.py`: a `--dry-run` (stdlib-only,
prints the plan and downloads nothing), a real download to `data/osm/` (creating the dir), and a
`--write-manifest` that reads the downloaded PBF's `osmosis_replication_timestamp` header via
`osmium.io.Reader` and records it back into the manifest. The script **must not** download in a
test/CI path (`--dry-run` is the only stdlib-only mode). **Import `osmium` lazily INSIDE the
`--write-manifest` branch (not at module top)** so `--dry-run` stays genuinely stdlib-only and does
not `ImportError` if `osmium` is absent offline — mirroring how `fetch_usfs.py` defers its
`geopandas` import off the dry-run path (`fetch_usfs.py:83-88`, docstring `:19`). A test drives
`--dry-run` (or the plan-builder function) and asserts it downloads nothing and prints the manifest
URL.
**AC-4.3:** The script never commits the PBF (writes only under gitignored `data/osm/`); this is
stated in its docstring, matching `fetch_usfs.py:19-22`.

### S5 — Parity test (`tests/test_osm_pbf_parity.py`) — the anti-drift guard

**Given** the whole point of the additive source is a future no-drift cutover,
**When** the same trail data is expressed as an Overpass JSON response and as a synthetic `.osm.pbf`,
**Then** `osm_pbf.fetch` and `osm.fetch` produce the **identical** `Feature` set (same names,
refs, way_types, classified tags, and geometry).

**AC-5.1:** A tiny synthetic `.osm.pbf` fixture is **committed** under `tests/fixtures/`
(e.g. `tests/fixtures/synthetic_trails.osm.pbf`). It contains a handful of ways covering: (a) a
named trail-worthy `highway=path` with `sac_scale`+`surface`+`access` tags, (b) a named
`highway=track`, (c) a named `highway=footway`, (d) an **unnamed** `highway=path` (must be
dropped), (e) a `highway=residential` (must be dropped). A committed generator
`tests/fixtures/build_synthetic_pbf.py` documents how the fixture was produced with
`osmium.SimpleWriter` (BSD — provenance + reproducibility; it is the fixture's build recipe, not a
test dependency). **Coordinate discipline (binding — this is the single most likely spurious red):**
use **short-decimal** node coordinates (≤ 5 dp, matching `tests/test_fetch.py`'s existing
`[-78.28, 38.55]` style) that are **byte-identical on both sides** — the same lon/lat literals in
the `SimpleWriter` fixture and in the `_osm_element` Overpass mock. pyosmium round-trips node
locations through libosmium's int32 1e-7 fixed-point quantization + `WKTFactory` decimal
formatting, while the Overpass path keeps full float64; matched short decimals keep both
representations equal after the round-trip.
**AC-5.2:** The test builds the **equivalent** Overpass response for the same ways (reuse
`tests/test_fetch.py`'s `_osm_response`/`_osm_element` helpers pattern) with **matching OSM ids**,
runs `osm.fetch` through an `httpx.MockTransport`, and runs `osm_pbf.fetch` over the committed
fixture. It asserts the two `list[Feature]` are equal on the tuple
`(name, source, ref, way_type, path_grade, psurface, foot_access, coords)` for every
feature — i.e. **identical classify + gate + ref + geometry across transports** (Guard 2).
**Compare coordinates rounded to ~6 dp** (e.g. `tuple((round(x, 6), round(y, 6)) for x, y in
sorted(geom.coords))`), **not raw float-equal** — the pyosmium int32-1e-7 quantize + WKT-reformat
round-trip (see AC-5.1) can leave the last ULPs differing from the Overpass float64 side even for
matched short-decimal inputs; a 6-dp round absorbs that without hiding any real classify/geometry
drift.
**AC-5.3:** The parity test asserts the dropped ways (unnamed path, residential) appear in
**neither** transport's output — the `is_trail_worthy` + `_TRAIL_HIGHWAYS` + name gate is proven
identical, not just the kept-way attributes.
**AC-5.4:** The test imports **no** network and downloads **no** state PBF (the committed synthetic
fixture only — the unattended-feasibility guard). It carries **no** `@pytest.mark.neo4j`.

---

## Definition of Done
- [ ] All ACs covered by at least one passing test. New modules get tests **before** callers
      (CLAUDE.md): `tests/test_osm_pbf_parity.py` for S1/S5; adapter + config + registry tests
      alongside (may live in `test_osm_pbf_parity.py` or `tests/test_sources.py`/`test_config.py`
      as fits the existing layout). Network-free (`osmium.SimpleWriter`-built fixture,
      `httpx.MockTransport` for the Overpass side, injected transport for the adapter). **No
      `@pytest.mark.neo4j`.**
- [ ] `osmium>=4.0` added to `pyproject.toml` optional-deps `ingestion` (and `dev` if the parity
      test needs it at check time), alongside `shapely` — BSD-2-Clause, PORT-OK normal dependency.
- [ ] **Additive-default disclosed in the PR body:** `"osm-pbf"` is registered but **not** in the
      default `ADVENTURE_CORPUS_SOURCES` — nothing in the shipped default pipeline calls it yet.
      This is the Epic-026 "persisted for a later phase" precedent; state it so "PBF transport" is
      not read as already-live-as-spine.
- [ ] **License disclosed:** pyosmium BSD (dependency, no code ported), osmium-tool GPL (not used),
      Geofabrik data ODbL (already compliant, `source="OSM"` persisted). No file-header attribution
      needed (no source ported).
- [ ] **Parity-scope disclosed:** the AC-5.2 parity guard covers **classify + gate + ref +
      geometry**, NOT **bbox-membership** — bounds-intersect is a deliberate (over-inclusive)
      superset of Overpass's geometry-intersect at the boundary, so a real-PBF cutover may see a
      count-diff of boundary ways (a cutover-time diff-and-flip item, not a parity-test assertion).
- [ ] `make check` green (`ruff format --check` + ruff + mypy + `pytest -m "not neo4j"`); no
      `Any`-typed field; missing/corrupt PBF degrades to `[]`, never fabricates geometry.
- [ ] `ingest_version` untouched; `ingestion/pipeline.py` unedited (the swap is transparent behind
      `CorpusSource.fetch`).
- [ ] Targeted self-review agent run over the diff; every CRITICAL fixed, MODERATE+ documented.
- [ ] Committed and pushed on `claude/pyosmium-transport`; PR opened into `main` (title
      `Epic 036: Deterministic OSM PBF transport (pyosmium; additive) — FOR REVIEW`, the 5 sections,
      and **"merge AFTER Epic 34; independent of 35"**); epic copied into `docs/epics/` with **Status: REVIEW**;
      a row added to `docs/epics/README.md`; `scripts/gen_epic_index.py` re-run to sync status cells.
