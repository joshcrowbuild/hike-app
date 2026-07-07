# Epic 033 — OpenTopoData fallback ElevationSampler (degrade-and-disclose)

**Status:** DONE ✅
**Phase:** 1 (Track: elevation durability)
**Spec refs:** discovery sweep §4 (`/Users/joshcrow/.hike-lanes/oss-sprint/research/discovery.md:38-43`) · Epic 017 (terrain elevation enrichment) · CLAUDE.md rules #1 (source-or-silence), #3 (graph holds slow/structural — elevation is structural corpus data), #6 (degrade-and-disclose), #10 (secrets/paths from config)

---

## Capability statement
When the local 3DEP DEM raster is absent (the recurring "elevation kept disappearing on Render" pain — the DEM lived in a transient worktree and no `rasterio` is installed on the API/ingest box), an operator can point ingestion at a hosted **OpenTopoData** endpoint (self-hosted Docker, or the public host for light use) and get a **degrade-and-disclose** elevation path: elevation is still sampled at ingest from the NED10m dataset (our USGS-3DEP equivalent), missing samples still return `None` (never a guess), and the transport origin is disclosed on every fact.

## Architectural context
**Builds on:**
- The `ElevationSampler` Protocol seam — `ingestion/elevation.py:43` (`def sample(self, lon: float, lat: float) -> float | None`). The profile math (`build_profile` / `build_profile_from_wkt`) is transport-agnostic and already honors `None` as the source-or-silence signal (coverage gate at `elevation.py:225-232`, interior-hole gate at `:211-216`).
- `RasterioDEMSampler` — `ingestion/sources/usgs_3dep.py:45` (the local-raster transport) — the sibling this new sampler sits alongside.
- The sampler-selection point — `UsgsThreeDEPSource.from_config`, `ingestion/sources/usgs_3dep.py:122-141` — which today builds a `RasterioDEMSampler` from `settings.dem_path` or degrades to a no-sampler instance.
- The config seam — `orchestration/config.py` `Settings` (`dem_path` at `:135`, `from_env` at `:167-234`).
- The injectable-`httpx.Client` test idiom used across ingestion sources (e.g. `ingestion/fetch/osm.py:36-50`, `ingestion/sources/nps.py:33`).

**Enables:** a cloud/Render ingest or enrich run to produce elevation profiles with no local `.tif` and no `rasterio` dependency on the box — closing the DEM-durability saga (viewer-path 500 / "Richmond got 0 elevation" class of bug) without persisting any live data.

**Does NOT include (scope fence — binding):**
- **NOT primary.** Local-first raster stays the default. When a real DEM raster is present it MUST win; the network sampler is only selected when the raster is absent (see AC-2.x).
- **No `api/app.py` changes.** This is an ingest/enrich-time transport swap only.
- **Elevation is NOT reclassified as fast/live data.** It remains structural corpus data sampled once at ingest and written to `CanonicalTrail` (rule #3). This epic swaps the SAMPLER transport; it does not add a JIT/live overlay, does not persist any per-request live elevation, and does not touch the LiveAdapter seam.
- **No batching API on the Protocol.** `sample()` stays one-point-in / one-value-out (see Open Questions for the batching note).

**License / attribution (binding — LICENSE GATE):** OpenTopoData (`ajnisbet/opentopodata`) is **MIT → PORT-OK**. We are writing a thin REST *client* that mirrors its Google-Elevation-compatible request/response contract (`/v1/{dataset}?locations=lat,lon` → `{"results":[{"elevation":…}],"status":"OK"}`); the new file `ingestion/sources/opentopodata.py` MUST carry an attribution header naming OpenTopoData, its MIT license, and the upstream repo URL. The **NED10m dataset served by OpenTopoData is USGS 3DEP-derived → public-domain data** (same provenance class as our local DEM); ODbL/API-terms do not bar it. For heavy ingest use the **self-hosted** Docker instance (the public `api.opentopodata.org` is rate-limited — see Open Questions).

---

## Stories

### S1 — `OpenTopoDataSampler` implements the `ElevationSampler` Protocol as a network transport

**Given** a configured OpenTopoData base URL and dataset
**When** the profile builder calls `sample(lon, lat)` for a densified route point
**Then** the sampler performs one hosted-elevation lookup and returns a metres float, or `None` on any miss — never a guessed value.

New file: `ingestion/sources/opentopodata.py`.

**AC-1.1:** A class `OpenTopoDataSampler` exists with signature `__init__(self, *, base_url: str, dataset: str = "ned10m", client: httpx.Client | None = None, timeout: float = 30.0)` and a `sample(self, lon: float, lat: float) -> float | None` method. `__init__` normalizes `base_url` by stripping any trailing slash (`self._base_url = base_url.rstrip("/")`) so an operator who pastes `http://host:5000/` cannot produce a double-slashed request URL. It is structurally compatible with the `ElevationSampler` Protocol (`ingestion/elevation.py:43`) — verified by a test that binds an `OpenTopoDataSampler` to a variable typed `ElevationSampler` (mypy) and by `build_profile` accepting it.
**AC-1.2:** `sample(lon, lat)` issues `GET {base_url}/v1/{dataset}?locations={lat},{lon}` — **lat,lon order** (Google-Elevation / OpenTopoData convention), dataset in the path. A test asserts the exact request path + query captured via `httpx.MockTransport`. The test includes a `base_url` with a **trailing slash** (e.g. `http://host:5000/`) and asserts the emitted path has no double slash (`/v1/…`, never `//v1/…`) — pinning the normalization from AC-1.1.
**AC-1.3:** On HTTP 200 with `status == "OK"` and a numeric `results[0].elevation`, `sample` returns `float(elevation)`. Test with a mocked `{"results":[{"elevation":1611.0,...}],"status":"OK"}` asserts `== 1611.0`.
**AC-1.4 (source-or-silence, rule #1):** `sample` returns `None` — never 0.0, never a guess — for every miss: `elevation` is JSON `null` (point outside the dataset / nodata), `results` empty, `status != "OK"`, HTTP status != 200, malformed/non-JSON body, or any raised exception (connect/timeout/etc.). Each case has its own test. `None` from `null` elevation is the case that keeps OpenTopoData's out-of-coverage behavior feeding the existing `<60%` coverage gate.
**AC-1.5:** The sampler reuses a single `httpx.Client` across `sample()` calls (injected `client` when given, else one lazily constructed with `timeout`), and exposes `close()` that closes only a client it owns (an injected client is left open — mirrors `RasterioDEMSampler.close`). Test asserts an injected client is not closed by `close()`.
**AC-1.6 (disclosure, rule #7):** The sampler carries a disclosable origin string, `self.source == f"opentopodata:{dataset}"` (e.g. `"opentopodata:ned10m"`), used to disclose the transport on emitted facts (S2).

### S2 — Selectable alongside `RasterioDEMSampler`, local-raster-first, transport disclosed

**Given** `Settings` that may carry a local `dem_path`, an `opentopodata_url`, both, or neither
**When** `UsgsThreeDEPSource.from_config(settings)` builds the source
**Then** it picks the raster when a real local DEM is present, else the network sampler when a URL is configured, else no sampler — and the resulting facts disclose which transport produced them.

Edits: `ingestion/sources/usgs_3dep.py` (selection at `:122-141`) · `orchestration/config.py` (new config field + `from_env`).

**AC-2.1 (config):** `Settings` gains `opentopodata_url: str | None = None` and `opentopodata_dataset: str = "ned10m"`. `from_env` reads `ADVENTURE_OPENTOPODATA_URL` (→ `None` when unset/blank) and `ADVENTURE_OPENTOPODATA_DATASET` (default `"ned10m"`). Documented inline in `config.py` next to `dem_path` (rule #10: URL from config, never the repo). The inline comment MUST state that **self-hosted OpenTopoData Docker is the supported ingest path; the public `api.opentopodata.org` is light-use only (~1 req/s, 1000 calls/day) and will fail a full re-ingest** — so an operator can't accidentally point a full re-ingest at the rate-limited public host. A test builds `Settings.from_env({...})` and asserts both fields.
**AC-2.2 (local-first — NOT primary):** In `from_config`, when `settings.dem_path` is set **and the raster file exists on disk** (`os.path.exists`), a `RasterioDEMSampler` is built (unchanged behavior) even if `opentopodata_url` is also set. Test: `dem_path` → an existing temp file + a set `opentopodata_url` ⇒ the source's sampler is a `RasterioDEMSampler`.
**AC-2.3 (degrade path):** When the local raster is absent (`dem_path` is `None` — the Render case: `default_dem_path` already returns `None` via its `is_file()` guard at `config.py:29-34` when the `.tif` was never fetched, so `from_env` hands `from_config` a `None` there — **or** `dem_path` is set to a path that does not exist, which only arises from an explicit `ADVENTURE_3DEP_DEM` override pointing at a not-yet-fetched file) **and** `opentopodata_url` is set, `from_config` builds an `OpenTopoDataSampler(base_url=…, dataset=…)`. The `os.path.exists` check in `from_config` (AC-2.2) is what catches the explicit-override-to-missing-file case, since `default_dem_path` can never hand back a nonexistent path. Two tests: (a) `dem_path=None` + URL, (b) `dem_path="/no/such.tif"` + URL — both ⇒ sampler is an `OpenTopoDataSampler`.
**AC-2.4 (no-op still safe):** When neither a usable raster nor a URL is configured, `from_config` still degrades to the no-sampler instance (existing behavior at `:131-137`), whose `enrich` returns `[]` (rule #6). Test asserts `_sampler is None` and `enrich(...) == []`.
**AC-2.5 (disclosure through to facts, rule #7):** When the OpenTopoData path is selected, the emitted `elev_source` fact discloses the network origin (value `"opentopodata:{dataset}"`, from the sampler's `source`), distinct from the raster path's `"usgs-3dep"`; `elev_version` reflects the dataset. Implemented by threading an `elev_source`/version into `UsgsThreeDEPSource` at `from_config` (do not hardcode `ELEV_SOURCE` when the network sampler is used). Test drives `enrich` with a `MockTransport`-backed `OpenTopoDataSampler` over a ramp and asserts the `elev_source` fact value discloses OpenTopoData.

### S3 — End-to-end profile through the network sampler (mocked HTTP, no DB)

**Given** a stored route WKT and an `OpenTopoDataSampler` backed by an `httpx.MockTransport` that returns a monotonic ramp keyed on coordinate
**When** `build_profile_from_wkt` samples the route through it
**Then** a normal `ElevationProfile` is produced with disclosed `source`, and an out-of-coverage mock (all `elevation: null`) yields `None` via the existing coverage gate.

**AC-3.1:** A test builds a profile end-to-end through `build_profile_from_wkt(_WKT, OpenTopoDataSampler(...), source="opentopodata:ned10m")` with a MockTransport ramp; asserts `total_gain_m > 0` and `source == "opentopodata:ned10m"`.
**AC-3.2:** A MockTransport that returns `elevation: null` for every point yields `build_profile_from_wkt(...) is None` (coverage below the `0.6` floor → source-or-silence). This proves the network miss behavior composes with the existing gate unchanged.
**AC-3.3 (test hygiene — binding):** All tests mock HTTP via `httpx.MockTransport`; **no network**, **no `@pytest.mark.neo4j`**, no DB. New tests live in `tests/test_opentopodata_sampler.py`.

---

## Definition of Done
- [ ] All ACs covered by at least one passing test in `tests/test_opentopodata_sampler.py`
- [ ] `ingestion/sources/opentopodata.py` carries the MIT attribution header (OpenTopoData `ajnisbet/opentopodata`)
- [ ] `make check` green (`ruff format --check` + ruff + mypy + pytest)
- [ ] Targeted self-review agent run; every CRITICAL fixed, MODERATE+ documented
- [ ] Epic file copied to `docs/epics/epic-033-opentopodata-fallback-sampler.md` (Status header set to REVIEW at PR-open) + a row added to `docs/epics/README.md`; `scripts/gen_epic_index.py` re-run to sync status cells
- [ ] Committed and pushed on `claude/opentopodata-fallback-sampler`; PR opened "Epic 033: … — FOR REVIEW"

## Open questions (non-blocking; note in PR)
1. **Batching / rate limits.** The `ElevationSampler` Protocol is one-point-per-call, so a full-corpus ingest issues one HTTP request per densified route point (hundreds per trail). This is fine against a **self-hosted** OpenTopoData Docker (local, fast) — the intended deployment — but the public `api.opentopodata.org` allows ~1 req/s, 100 locations/call, 1000 calls/day and is unsuitable for a full re-ingest. Document self-hosting as the supported path; a future batched sampler method (100 `locations=` per call) is a clean follow-up but out of scope here (Protocol change).
2. **Optional in-sampler LRU cache** for repeated coordinates across overlapping trails — a small win, deferred; note only.
3. **Selection precedence when both are set** is resolved here by "raster wins iff the file exists." Confirm with PM that an operator wanting to force the network path on a box that *does* have a stale raster would unset `dem_path` (or we add an explicit `ADVENTURE_ELEV_SAMPLER` override later).
