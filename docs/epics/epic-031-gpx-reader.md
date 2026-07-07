# Epic 031 — GPX reader-tolerance module (dedupe · <2pt-drop · timestamp-derived-flag)

**Status:** DONE ✅
**Phase:** C (Phase-C history import — C1; built pre-Phase-C as an additive, DB-free module)
**Spec refs:** CoMaps borrow plan §C1 (`docs/research/comaps-borrow-plan.md` wave C) · research brief `gpx-import-patterns.md` · `docs/strategy/path-to-complete.md` (C1 reader tolerance; Open Decision #10 map-matching) · CLAUDE.md Rule #1 (source-or-silence), Rule #3 (graph holds slow/structural only), Rule #5 (private-by-default; strip raw substrate)

> Line numbers in this doc were read on **2026-07-07** and **may drift** — re-grep the named
> symbols (`_FIT_REQUIRED`, `parse_fit`, `FITSummary`, `gps_track`, the `ingestion`/`dev`
> extras in `pyproject.toml`) if an anchor no longer matches.

---

## Capability statement
The ingestion layer can turn a noisy real-world GPX export (Strava/Garmin) into a list of
cleaned, free-floating tracks — consecutive near-duplicate points dropped, degenerate
(<2-point) segments removed, and partial/missing timestamps corrected with **every
synthesized timestamp flagged `derived`** so interpolated moving-time can never later pose as
measured — via one pure function `read_gpx()` that touches no database, no network, and no
auth surface.

## Architectural context
**Builds on:**
- `ingestion/ingest_episode.py` — `parse_fit()` (`ingest_episode.py:65`) is the FIT analog of
  this reader; it returns `FITSummary.gps_track: list[tuple[float, float]]` (lat,lon)
  (`ingest_episode.py:62`). `fitdecode` is **lazy-imported** and gated on
  `_FIT_REQUIRED = "fitdecode"` (`ingest_episode.py:35,67-71`). This epic mirrors that exact
  lazy-import discipline for `gpxpy`.
- `pyproject.toml` — base `dependencies = []` (`:14`); real deps live in optional extras. This
  epic adds `gpxpy>=1.6` to the `ingestion` extra (`:18`) **and** the `dev` extra (`:36-49`)
  — see the load-bearing note in AC-1.1.

**Enables (all OUT of this epic — do not build):**
- Phase-C map-matching (raw track → corpus trail-node `been_on` binding) — a separate **L**,
  **Open Decision #10**, "decide at Phase-C build start". This epic produces cleaned
  free-floating tracks; binding is a later step.
- The Phase-C authed-episode HTTP endpoint + `create_episode` wiring — gated on the Supabase
  auth decision. This epic does **not** call `create_episode`, does **not** open a route.

**Does NOT include (scope fence — the single biggest scope-creep risk is map-matching):**
- **NO map-matching / snap-to-network / HMM.** No corpus lookup, no `CanonicalTrail` query, no
  `been_on` edge. Output is free-floating lat/lon only.
- **NO `create_episode` call, NO HTTP endpoint, NO FastAPI route, NO DB write.** No
  `ScopedSession`, no Cypher, no Neo4j import anywhere in the module or its tests.
- **NO gap-bridging / no segment stitching.** A privacy-zone truncation shows up as a **gap**;
  the reader must **not** bridge it. Dropping a <2-point segment and NOT stitching across
  segments is correct behavior, not a bug (Rule #5 — the Strava privacy-zone leak is the
  cautionary tale).
- **NO persistence of the polyline.** Same discipline as `FITSummary.gps_track` (consumed
  in-memory, never written to `:Episode` — Rule #3). This epic never writes anything.

---

## Binding corrections (from the borrow plan / research brief — embedded because the builder cannot read the plan)

- **BC-1 (borrow type):** Port the **~3 cleaning heuristics only**, NOT CoMaps' C++ XML-SAX
  parser (`libs/kml/serdes_gpx.cpp`). Layer the heuristics on **gpxpy** (Apache-2.0, the
  parser we build on). This is what keeps the effort honestly **S**.
- **BC-2 (Rule #1 — the HARD gate):** `CheckAndCorrectTimestamps`' interpolation manufactures
  interior timestamps. Every synthesized timestamp **must** carry a per-point `derived` flag;
  a measured timestamp must **never** be flagged derived, and a derived one must **never** be
  presentable as measured. This is elevated to a load-bearing test (AC-3.4), not a nicety.
- **BC-3 (license):** `gpxpy` = **Apache-2.0**, PORT-OK — add as a dependency, no code copied
  (it is imported, not vendored). CoMaps `serdes_gpx.cpp` + wanderer (Flomp/wanderer, AGPL-3.0)
  + Dawarich (Freika/dawarich, AGPL-3.0) = **PATTERN-AND-SPEC ONLY**: read to learn the
  heuristics/UX, re-derive from scratch, **zero code copied**. The only code that lands is our
  own module + the `gpxpy` dependency. The 3-heuristic spec is already extracted in the borrow
  plan and restated in the ACs below, so the builder needs no AGPL source at all.
- **BC-4 (Rule #5 — privacy on read):** Strip residual device/extension metadata at parse
  time. Keep **only** geometry + timestamps. Never read/emit GPX `<extensions>` (Garmin
  `TrackPointExtension` hr/cad/atemp), track/segment names, `<desc>`, `<cmt>`, `<src>`,
  waypoints, or routes.

---

## The contract (net-new API)

**New module `ingestion/gpx_reader.py`** exposes:

```python
_GPX_REQUIRED = "gpxpy"  # mirrors ingest_episode._FIT_REQUIRED

@dataclass(frozen=True)
class CleanTrack:
    points: list[tuple[float, float, float | None]]   # (lat, lon, ele|None)
    timestamps: list[datetime | None]                 # one per point (parallel)
    timestamps_derived: list[bool]                    # True iff synthesized (Rule #1)
    timestamps_cleared: bool                          # True iff >50% invalid → all cleared

def read_gpx(source: str | Path | bytes) -> list[CleanTrack]: ...
```

**Structural invariants (each an assertion the tests enforce):**
- For every returned `CleanTrack`: `len(points) == len(timestamps) == len(timestamps_derived)`
  and `len(points) >= 2` (degenerate segments are dropped, never returned).
- `points[i][0:2] == (lat, lon)` — **same lat-first ordering as `parse_fit`'s `gps_track`**, so
  a later Phase-C map-matcher can consume it. `ele` is the optional 3rd element (`None` when the
  GPX point has no `<ele>`).
- When `timestamps_cleared is True`: every `timestamps[i] is None` and every
  `timestamps_derived[i] is False` (cleared ≠ derived — an absent timestamp is silence, not a
  synthesized value).

---

## Stories

### S1 — Dependency + module skeleton + lazy import (mirror the FIT seam)

**Given** `gpxpy` is not declared anywhere and no GPX reader exists
**When** the module and dependency are added
**Then** `read_gpx` parses GPX 1.0 and 1.1, from both a filesystem path and raw bytes, with
`gpxpy` lazy-imported exactly like `fitdecode`.

- **AC-1.1:** `gpxpy>=1.6` is added to **both** the `ingestion` extra (`pyproject.toml:18`)
  **and** the `dev` extra (`pyproject.toml:36-49`). The `dev` addition is **load-bearing and
  differs from `fitdecode`**: `test_ingest_episode.py` never actually calls `parse_fit`, so
  `fitdecode` need not be installed for `make check`; but `test_gpx_reader.py` **does** call
  `read_gpx`, which imports `gpxpy` — so `gpxpy` must be in `dev` or `make check` fails at
  import. (`all` already pulls `dev` via `pyproject.toml:50`, so `gpxpy` flows into `all`
  through both paths.)
- **AC-1.2:** `read_gpx` lazy-imports `gpxpy` inside the function body, guarded by
  `_GPX_REQUIRED = "gpxpy"`, mirroring `ingest_episode.py:35,67-71` (a clear error / `sys.exit`
  or a raised `ImportError` with the install hint — match the surrounding FIT pattern; a raised
  exception is preferable to `sys.exit` in a library function, note this in the PR). Importing
  the module itself (`from ingestion.gpx_reader import read_gpx, CleanTrack`) must **not** import
  `gpxpy` at module load (so the import is free on non-GPX paths).
- **AC-1.3:** `read_gpx` accepts `source: str | Path | bytes`. A `str` or `Path` is treated as a
  **filesystem path** (read then parse); `bytes` is treated as **raw GPX content** (decode
  utf-8, parse). A test parses the same fixture both ways and asserts identical output.
- **AC-1.4:** A minimal **GPX 1.1** file and a minimal **GPX 1.0** file (differing namespaces)
  both parse to the same `CleanTrack` geometry (gpxpy handles both; the test locks it in).
- **AC-1.5:** `CleanTrack` is a `frozen=True` dataclass with exactly the four fields in the
  contract above; the module has **no** import of `graph`, `orchestration.*` DB code, `neo4j`,
  `httpx`, or `fastapi` (assert by grep in review; the module is pure/DB-free/auth-free).

### S2 — Geometry cleaning: consecutive-dedupe + <2-point-segment drop (no stitching)

**Given** a real GPX export carries consecutive near-identical points (stationary GPS jitter)
and occasional 1-point degenerate segments
**When** `read_gpx` cleans each track segment
**Then** consecutive near-duplicates are dropped and segments with <2 surviving points are
removed entirely, with **no bridging across the drop**.

- **AC-2.1 (dedupe):** For each segment, iterate points in order; drop point `i` when the
  **haversine** distance from the last *kept* point to point `i` is `< EPSILON_M`
  (module constant, default `EPSILON_M = 1.0` meters — the analog of CoMaps
  `kMwmPointAccuracy`; parametrizable via a keyword arg with that default). The **first** point
  of a run is always kept; only later near-duplicates are dropped. Re-derived from CoMaps
  `Pop()`-at-`kTrkPt` — **not** gpxpy's `reduce_points`, because that reshuffles indices and
  breaks the parallel timestamp arrays. (A tiny local haversine, or `gpxpy.geo.haversine_distance`
  — Apache-2.0, fine to call — is acceptable; state which in the PR.)
- **AC-2.2 (dedupe test):** A segment `[A, A', A'', B]` where `A/A'/A''` are within `EPSILON_M`
  of each other and `B` is far → cleans to `[A, B]` (2 points). The kept points retain **A's**
  and **B's** original timestamps (dedupe drops the later dup's data, never the survivor's).
- **AC-2.3 (<2pt drop):** A segment that reduces to `<2` points (e.g. a lone point, or an
  all-near-duplicate run collapsing to 1) is **dropped** — it produces **no** `CleanTrack`. A
  file whose only segment is degenerate returns `[]`.
- **AC-2.4 (multi-segment, no stitch):** A GPX with one `<trk>` containing **two** `<trkseg>`s
  (a privacy-zone gap between them) yields **two** `CleanTrack`s — one per surviving segment.
  The last point of track 1 and first point of track 2 are **not** merged/bridged. (Each
  surviving track-**segment** maps to exactly one `CleanTrack`; a multi-`<trk>` file likewise
  fans out per segment.)
- **AC-2.5 (multi-track):** A GPX with two `<trk>`s each with one segment yields two
  `CleanTrack`s, in document order.

### S3 — Timestamp correction with the derived flag (Rule #1 hard gate)

**Given** GPX exports carry partial, missing, or out-of-order timestamps
**When** `read_gpx` corrects timestamps per surviving `CleanTrack`
**Then** interior gaps are interpolated and edges filled, **every synthesized timestamp is
flagged `derived`**, and a track that is >50% invalid has **all** timestamps cleared.

- **AC-3.1 (invalidity pre-pass):** Before counting, a point's timestamp is treated as
  **invalid** (normalized to `None`) if it is missing, OR if it is **not strictly greater** than
  the previous *valid* timestamp in the segment (non-monotonic / zero / duplicate time — CoMaps
  treats these as invalid too). This normalization happens on the post-dedupe point list.
  **Mixed tz-awareness is fail-soft, never a crash:** if a point's timestamp is tz-inconsistent
  with the previous valid timestamp (one naive, one aware), the `>` compare and the later
  `t_j - t_i` subtraction would raise `TypeError("can't subtract offset-naive and offset-aware
  datetimes")` — so treat such a point as **invalid** (normalize to `None`) rather than raising.
  Degrade at the surface; do **not** let a malformed single-exporter mix hard-crash `read_gpx`.
  (Add a mixed-tz fixture asserting no exception is raised.)
- **AC-3.2 (>50%-invalid clear):** If the count of invalid timestamps is **> 50%** of the
  segment's points, clear the whole track: `timestamps = [None]*n`,
  `timestamps_derived = [False]*n`, `timestamps_cleared = True`. (Boundary: exactly 50% invalid
  is **kept** — the rule fires strictly above half. Lock the boundary in a test.)
- **AC-3.3 (interior interpolation + edge fill):** When the track is kept
  (`timestamps_cleared is False`):
  - **Interior gap:** for a run of invalid points between two valid anchors at indices `i`
    (`t_i`) and `j` (`t_j`), fill index `k` (`i<k<j`) with
    `t_i + (t_j - t_i) * (k - i) / (j - i)` (linear-by-index; the CoMaps "naive interpolation").
  - **Leading edge:** invalid points before the first valid anchor take the first anchor's time.
  - **Trailing edge:** invalid points after the last valid anchor take the last anchor's time.
  - Each filled index sets `timestamps_derived[k] = True`; every originally-valid index sets
    `timestamps_derived == False`.
- **AC-3.4 (Rule #1 — LOAD-BEARING TEST):** A track with a valid start and end but **missing
  interior** timestamps → the interior `timestamps` are filled (non-None) **and** their
  `timestamps_derived[i] is True`, while the two measured endpoints have
  `timestamps_derived is False`. An assertion must prove a derived timestamp is distinguishable
  from a measured one. **This is the invariant that stops interpolated moving-time from ever
  posing as measured; it is not optional.**
  **Size the fixture so interior-invalid stays ≤50%, or the AC-3.2 clear rule preempts
  interpolation and this test never runs** — e.g. 4 points = 2 measured ends + 2 derived
  interior (2/4 = exactly 50%, kept per AC-3.2's strict-`>`-half boundary). A naive 5-point
  fixture (3 interior invalid = 60% > 50%) would be **cleared** by AC-3.2, not interpolated, and
  fail this assertion. If this test fails, **resize the fixture — do NOT weaken AC-3.2**; the
  two rules interact by design.
- **AC-3.5 (fully-timestamped passthrough):** A track where every point has a valid, strictly
  increasing timestamp → `timestamps_derived == [False]*n`, `timestamps_cleared is False`,
  timestamps unchanged.
- **AC-3.6 (no timestamps at all):** A track with **zero** timestamps (all missing, i.e. 100%
  invalid > 50%) → `timestamps_cleared is True`, all `timestamps` `None`, all
  `timestamps_derived` `False`.

### S4 — Privacy on read: strip device/extension metadata (Rule #5)

**Given** Garmin/Strava GPX carries `<extensions>` (heart-rate, cadence, temperature, device
id), track names, and sometimes waypoints/routes
**When** `read_gpx` parses the file
**Then** only geometry (lat/lon/ele) + timestamps survive; all other metadata is discarded.

- **AC-4.1:** A GPX with `gpxtpx:TrackPointExtension` (hr/cad/atemp) and a device `<src>` on
  each `<trkpt>` → the returned `CleanTrack` carries **none** of it. `CleanTrack` has no field
  for extensions; the reader never reads `point.extensions`.
- **AC-4.2:** A GPX carrying `<wpt>` waypoints and/or a `<rte>` route → those are **ignored**;
  `read_gpx` reads only `<trk>/<trkseg>/<trkpt>`. (Waypoints/routes are not tracks and carry POI
  metadata we must not ingest.)
- **AC-4.3:** Track/segment `<name>`, `<desc>`, `<cmt>` are never read into the output.

---

## Reference material (license class stated)

| Source | Path / URL | License | Use |
|---|---|---|---|
| gpxpy | `https://github.com/tkrajina/gpxpy` · PyPI `gpxpy>=1.6` | **Apache-2.0** | **Dependency** — import & call. Attribution header in `gpx_reader.py`. No code copied. |
| CoMaps `serdes_gpx.cpp` | (borrow plan §C1 has the spec extracted) | Apache-2.0, but treated pattern-only per borrow plan | **PATTERN/SPEC ONLY** — the 3 heuristics are restated in the ACs; re-derive, copy nothing. |
| wanderer | `/Users/joshcrow/.hike-lanes/oss-sprint/repos/` (not cloned; brief covers it) · `github.com/Flomp/wanderer` | **AGPL-3.0** | **PATTERN ONLY** — confirms the real-world mess (dupes/degenerate segments/partial ts). Never copy code. |
| Dawarich | `github.com/Freika/dawarich` | **AGPL-3.0** | **PATTERN ONLY** — async import-pipeline shape (Phase-C UX, not this lane). Never copy code. |

`gpx_reader.py` header must carry an attribution line for the gpxpy dependency and a one-line
note that the cleaning heuristics are re-derived from the CoMaps C1 spec (pattern-only, no code
copied).

---

## Definition of Done
- [ ] All ACs covered by at least one passing test in `tests/test_gpx_reader.py` (pure
      function; **no** `ScopedSession`, **no** `@pytest.mark.neo4j`, **no** DB/network — runs in
      plain `make check`). Fixtures are inline GPX strings/bytes (Strava/Garmin-shaped): a
      consecutive-dupe track, a 1-point degenerate segment, a partial-timestamp track (interior
      derived), a >50%-invalid track (cleared), a multi-track/multi-segment file, GPX 1.0 vs
      1.1, ele present/absent, an `<extensions>`-laden track.
- [ ] `AC-3.4` (Rule #1 derived-flag) is present as an explicit, load-bearing assertion.
- [ ] `make check` green (`ruff format --check` + `ruff check` + `mypy` + `pytest -m "not neo4j"`).
- [ ] `gpx_reader.py` imports **no** `graph`/`neo4j`/`httpx`/`fastapi`/`orchestration` DB code;
      no `create_episode` call; no HTTP route; no map-matching/corpus lookup (scope fence held).
- [ ] `gpxpy>=1.6` added to **both** the `ingestion` and `dev` extras in `pyproject.toml`.
- [ ] Targeted self-review agent run over the diff; every CRITICAL fixed.
- [ ] Epic file copied into `docs/epics/`; a row added to `docs/epics/README.md`, then
      `scripts/gen_epic_index.py` run to sync the Status cell.
- [ ] Committed on `claude/epic-031-gpx-reader`; PR into `main` titled with the "FOR REVIEW"
      convention and the five sections (summary / why / scope / validation / merge-risk).
