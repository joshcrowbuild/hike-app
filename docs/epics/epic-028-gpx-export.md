# Epic 028 — GPX export (`GET /trail/{id}/export.gpx`) + Send-to-device on Detail

**Status:** IN_PROGRESS
**Phase:** 1 (Phase-A app-completeness; CoMaps borrow wave 2, item D4)
**Spec refs:** CoMaps borrow plan §D4 (verifier corrections D4.2 / D4.3) · CLAUDE.md Rule #1 (source-or-silence) · Rule #5 (private-by-default overlay; share the derived conclusion, never the raw substrate) · Epic 016 (route geometry) · Epic 017 (3DEP elevation profile)
**Depends on:** Epic 022, Epic 024 (merge AFTER both) — this PR is wave-2 and rides on their groundwork.

---

## Files touched (the true surface — for parallel-lane collision detection)

Declared so the scheduler sees the real edit surface. **Two of these are merge-hot** — flag them in the PR merge-risk section.

**Backend (new):**
- `api/gpx.py` (new module — the serializer)
- `tests/test_gpx.py` (new — serializer unit tests)
- `tests/test_gpx_export_endpoint.py` (new — endpoint tests)

**Backend (edited, merge-sensitive seam):**
- `api/app.py` — adds ONE new route + `Response` to the `fastapi.responses` import; no change to `/plan` or existing handlers. (AGENTS.md merge-sensitive seam — call out in PR.)

**Frontend (edited — shared source, MERGE-HOT):**
- `frontend/src/screens/Detail.tsx` — new chip in the `detail-actions` row + an `Icon` import.
- `frontend/src/data/geo.ts` — new `gpxExportUrl(id)` helper beside `trailheadDirectionsUrl`.
- `frontend/src/screens/glyphs.ts` — **MERGE-HOT: Epic 021 (icons lane) also writes this file.** Add a single `download: Download` entry (Lucide `Download`). Verified: glyphs.ts currently has no `download`/`hardDrive`/`export` entry, so the "add if none fits" branch of AC-3.3 fires and this edit is mandatory. Add only the one line + the `Download` import; do not reorder or touch other glyphs.
- `frontend/src/screens/Detail.test.tsx` (edited — extend the existing tests)

**Docs (edited):**
- `docs/epics/epic-028-gpx-export.md` (copied in), `docs/epics/README.md` (index row).

> If a concurrent wave-2 lane also declares `frontend/src/data/geo.ts` or `frontend/src/screens/glyphs.ts`, reconcile ordering before parallel-scheduling — do not let two lanes write glyphs.ts blind.

---

## Capability statement
A user viewing any trail can download a standards-valid **GPX 1.1** file of that trail's **world/corpus** route (one track, an altitude-guarded elevation, one trailhead waypoint) and load it onto a Garmin/Coros watch or any GPX-consuming app — from an anonymous, unauthenticated session, because it exports only shared world data.

## Architectural context
**Builds on:**
- `graph/queries.py::trail_detail` (verified `graph/queries.py:135-160`) — the existing world-only trip/detail projection that already returns `route_geom_wkt`, `segment_wkts`, `trail_point`, `trailhead_point`, `profile_distances_m`, `profile_elevations_m`, `elev_source`, `elev_resolution_m`. GPX export reuses this exact read — no new Cypher, no new graph fields.
- `ingestion/route.py::wkt_to_geojson` / `assemble_route` (verified `ingestion/route.py:149-184`) — WKT → coordinate lists; the same route-resolution + segment-assembly fallback the detail endpoint already uses (`api/app.py::_geometry_and_confidence`, `api/app.py:559-575`).
- `api/app.py::trail_detail` GET handler (verified `api/app.py:689-714`) — the sibling endpoint whose scoped-session read, 404-on-unknown, and `_authorize_viewer` posture this endpoint mirrors.
- CoMaps `libs/kml/serdes_gpx.cpp` (reference clone) — borrow the **GPX 1.1 wire format and the altitude gate only**: header `serdes_gpx.cpp:40-47`, `TrackHasAltitudes` gate `serdes_gpx.cpp:516-523`, `SaveTrackData` trk/trkseg/trkpt/`<ele>` loop `serdes_gpx.cpp:532-593`, `SaveBookmarkData` `<wpt>` `serdes_gpx.cpp:488-514`, `CoordToString` 8-sig-fig `serdes_gpx.cpp:437-443`, footer `serdes_gpx.cpp:47`.

**Enables:** the "take it to my device" leg of the plan→go loop — the first export surface in the app.

**Does NOT include:**
- KML export (CoMaps supports it; out of scope).
- Garmin `gpxx:TrackExtension` / `gpx_style` / OSMAnd color extensions (`serdes_gpx.cpp:548-561`) — dropped for the minimal core.
- Any nav-app framing, turn-by-turn, or routing.
- Exporting a **viewer's personal episode geometry** (a recorded track / FIT line). This epic serializes the **world route only** — see the binding Rule #5 correction below.
- Per-vertex `<time>` timestamps (`serdes_gpx.cpp:585-586`) — world routes have no timeline.
- Multi-track / multi-waypoint files, `FileData`/`MultiGeometry`/`CategoryData` machinery (`serdes_gpx.cpp:596-605`). One trk, one seg, at most one wpt.
- Persisting or caching the GPX; it is serialized JIT per request from the graph read.

---

## Binding verifier corrections (from the CoMaps borrow plan §D4 — embedded because the builder cannot read the plan)

**D4.2 — Rule #5 is the LIVE risk (the single most important constraint in this epic).**
Serialize the **WORLD/corpus `route_geom_wkt`** (the shared `CanonicalTrail` node) — **NEVER** the viewer's personal episode geometry. The cautionary tale is the Strava privacy-zone leak: exporting a personal recorded track leaks where a person actually was (home, etc.). The export reads through the same world-only `trail_detail` projection the public `GET /trail/{id}` uses; it MUST NOT touch `:Episode`, `:Belief`, `owner_id`-scoped nodes, or anything on the personal overlay. **Consequence:** because it exports only shared world data, the endpoint needs **NO auth** and is **anonymous-friendly** — it mirrors `GET /trail/{id}`'s posture exactly (`_authorize_viewer` still called with the query `viewer_id`, which defaults to `"anonymous"`, so a non-anonymous viewer is still auth-gated but the anonymous world-browse path is fully open).

**D4.3 — the `<ele>` gate maps 1:1 to the existing null-on-no-DEM discipline.**
Elevation is emitted only when it is real. CoMaps' `TrackHasAltitudes` (`serdes_gpx.cpp:516-523`) refuses to write `<ele>` when the altitude is the sentinel "default/invalid" value. Our equivalent: emit `<ele>` **only** when the trail carries a genuine 3DEP profile — i.e. `elev_source` is present AND the elevation samples align 1:1 with the route vertices. No DEM → no `elev_source` → no `<ele>` on any point. This is the same source-or-silence discipline `api/app.py::_elevation_profile` already applies (`api/app.py:614-649`: returns `None` when `elev_source` is absent, never a faked curve).

> **EXPECTED BEHAVIOUR — not a bug (answers author open-question #1).** `profile_elevations_m` is sampled on a **fixed distance grid** (`profile_distances_m`), whose length is keyed to the sampling stride, **not** to the `route_geom_wkt` vertex count (verified: `_elevation_profile`, `api/app.py:614-649`, and `_maps_fields` store parallel distance/elevation arrays independent of geometry vertices). For **essentially all current production trails** `len(profile_elevations_m) != len(coords)`, so the length-match gate will **correctly omit `<ele>` on the whole track**. This is the invariant-correct outcome (Rule #1 source-or-silence: better a silent, altitude-free track than a fabricated/mis-aligned curve). **Do NOT resample, interpolate, or nearest-neighbour the profile onto the route vertices to force a match** — that would violate Rule #1. Empty-`<ele>` is the accepted state of the minimal core; neither builder nor reviewer should treat it as a defect. The only cases that emit `<ele>` today are hand-aligned test fixtures (route verts == profile samples). **Follow-up (out of scope, file separately): a new epic to sample 3DEP elevation AT route vertices (or resample the route onto the profile distance grid) so real trails carry altitude — the real fix, deferred so this minimal core ships.**

---

## Stories

### S1 — Minimal GPX 1.1 serializer (`api/gpx.py`, new module)

**Given** a trail's world route coordinates (`[(lon, lat), …]`), an optional aligned elevation array, an optional trailhead point, and the trail name
**When** the serializer runs
**Then** it returns a standards-valid GPX 1.1 XML string with one `<trk>`/`<trkseg>`, altitude-guarded `<ele>`, and (when present) one trailhead `<wpt>` — with no personal data anywhere in it.

**AC-1.1:** New module `api/gpx.py` exposes a pure function (no I/O, no graph access), e.g. `build_gpx(name: str, coords: list[tuple[float, float]], *, elevations: list[float] | None, elev_source: str | None, trailhead: tuple[float, float] | None) -> str`. It returns a `str`; it never touches Neo4j, the filesystem, or any network. **Coordinate-order contract (pin it — a transposition here silently emits points at the wrong place):** both `coords` and `trailhead` are `(lon, lat)` order, matching the GeoJSON coords the endpoint extracts. The serializer transposes to GPX's `lat`-then-`lon` attribute order internally.
**AC-1.2:** The output opens with a GPX 1.1 preamble: `<?xml version="1.0"...?>` then `<gpx version="1.1" creator="Adventure Planner" xmlns="http://www.topografix.com/GPX/1/1">` and closes with `</gpx>` (borrowed shape: `serdes_gpx.cpp:40-47`, minus the gpxx/gpx_style/xsi extension namespaces we don't emit). `creator` is `"Adventure Planner"`, never `"CoMaps"`.
**AC-1.3:** Coordinates are emitted as `<trkpt lat="…" lon="…">` inside exactly one `<trk>` → one `<trkseg>`, in route order. `lat`/`lon` are formatted to ~8 significant figures (mirror `CoordToString`, `serdes_gpx.cpp:437-443`) — no scientific notation, no lat/lon transposition (a GPX `trkpt` carries `lat` then `lon`; the input coords are `(lon, lat)` GeoJSON order, so the serializer transposes correctly).
**AC-1.4:** The `<trk>` carries a `<name>` equal to the trail name, XML-escaped (`&`, `<`, `>`, `"`, `'` → entities) so a name like `Ridge & River <Loop>` cannot break the document or inject markup.
**AC-1.5 (altitude gate — D4.3):** `<ele>` is emitted on every `<trkpt>` **iff** `elev_source` is truthy **and** `elevations is not None` **and** `len(elevations) == len(coords)`. Otherwise **no** `<trkpt>` carries `<ele>` (all-or-nothing; never partial, never interpolated, never a fabricated altitude). Elevation values are metres, formatted like the coords.
**AC-1.6:** When `trailhead` is not `None` (a `(lon, lat)` tuple — see AC-1.1), exactly one `<wpt lat="…" lon="…">` with a `<name>` (e.g. `"{trail name} trailhead"`) is emitted, transposing `(lon, lat)` → `lat="…" lon="…"` (borrowed shape: `serdes_gpx.cpp:488-514`, minus `<extensions>`/color). When `trailhead` is `None`, no `<wpt>` appears. **Note for the endpoint (AC-2.5):** the graph's `trailhead_point` is read via a `_point_latlon`-style helper that returns `(lat, lon)` (verified `api/app.py:~550`), so the endpoint MUST transpose to `(lon, lat)` before handing it to `build_gpx`.
**AC-1.7:** The serialized string parses as well-formed XML (a test parses it with `xml.etree.ElementTree` and asserts the element/attribute structure), and contains **no** `gpxx:`, `gpx_style:`, `xsi:`, `<time>`, or `owner_id`/`episode`/personal substrings.

### S2 — `GET /trail/{canonical_id}/export.gpx` endpoint

**Given** a known trail canonical id
**When** a client GETs `/trail/{canonical_id}/export.gpx`
**Then** it receives the trail's world route as a downloadable `application/gpx+xml` file, 404 for an unknown trail, and the same anonymous-friendly / auth-gated posture as `GET /trail/{id}`.

**AC-2.1:** New route `@app.get("/trail/{canonical_id}/export.gpx")` in `api/app.py`, decorated `@limiter.limit(detail_limit)` (already imported, `api/app.py:34-41`). The handler signature mirrors the sibling (`api/app.py:691-696`) exactly, in this order: **`request: Request`** (first positional — **required by slowapi for per-IP keying**; the sibling carries it with the comment "required by slowapi for per-IP keying" — a handler that drops it breaks rate-limiting at runtime), then `canonical_id: str = Path(pattern=CANONICAL_ID_PATTERN)` (verified `api/schemas.py:18`), `viewer_id: str = Query(default="anonymous", pattern=VIEWER_ID_PATTERN)`, `x_dev_viewer_secret: str | None = Header(default=None)`.
**AC-2.2 (Rule #5 — D4.2):** The handler reads through `_graph_client.scoped_session(viewer_id)` + `trail_detail_query(canonical_id)` — the **same world-only projection** as `GET /trail/{id}`. It reads no `:Episode`/`owner_id`/personal-overlay node. A test asserts the Cypher the handler issues is exactly `trail_detail(...)` (no personal fields requested).
**AC-2.3:** `_authorize_viewer(viewer_id, x_dev_viewer_secret)` is called before the read (mirrors `api/app.py:703`): `viewer_id="anonymous"` is served openly; a non-anonymous `viewer_id` without a valid dev secret gets 403 (world data is still viewer-gated identically to the sibling — no new public identity surface).
**AC-2.4:** The route is resolved with the same discipline as the detail endpoint: prefer `route_geom_wkt`; on absent/unparseable, fall back to `assemble_route(segment_wkts)` (reuse `wkt_to_geojson`/`assemble_route`, `ingestion/route.py:149-184`). Coordinates are extracted from the resulting GeoJSON `LineString`/`MultiLineString` (a `MultiLineString` is flattened into one `<trkseg>` in part order — the minimal core is a single seg).
**AC-2.5:** Elevation is passed to the serializer only from the stored `profile_elevations_m` + `elev_source`; the altitude gate (AC-1.5) drops it whenever it doesn't align 1:1 with the extracted coordinates (**and per D4.3 that omission is the EXPECTED case for current trails — do not force a match**). Trailhead is `trailhead_point` when present, **transposed from the graph's `(lat, lon)` to the serializer's `(lon, lat)` contract** (see AC-1.6), else omitted (the derived trail-centroid fallback is out of scope — export the surveyed trailhead only, else no `<wpt>`).
**AC-2.6:** Unknown trail (`trail_detail_query` returns no rows) → HTTP 404 `{"detail": "Trail not found"}` (mirror `api/app.py:712-713`). A trail that **exists** but has no parseable geometry at all (no `route_geom_wkt`, no assemblable segments) → **HTTP 422** `{"detail": "Trail has no exportable route geometry"}` (never a 200 with an empty `<trkseg>`, never a fabricated line — Rule #1). Rationale (answers author open-question #3): **404 is reserved for an unknown `canonical_id`**; the trail here is known, its route is merely unprocessable, so 422 (unprocessable entity) keeps the API surface consistent with the sibling's 404-means-unknown contract. Test the 422 explicitly with a row that has neither geometry field.
**AC-2.7:** Response is a `fastapi.responses.Response` with `media_type="application/gpx+xml"` and header `Content-Disposition: attachment; filename="{safe_slug}.gpx"` where `safe_slug` is derived from the canonical id (ASCII, no path separators/quotes/control chars — a filename can never enable header injection).
**AC-2.8:** Graph read failure degrades exactly as the sibling: caught, logged server-side, re-raised as HTTP 500 `{"detail": "Internal error"}` (mirror `api/app.py:709-711`) — never leaks internals (Rule #10).

### S3 — Send-to-device action on Detail

**Given** the Detail screen for a trail with a mapped route
**When** the user taps "Send to device" (or "Download GPX")
**Then** the browser downloads `{id}.gpx` from the export endpoint; the action is hidden when the trail has no route geometry (never a dead link — Rule #1).

**AC-3.1:** A new action is added to the `detail-actions` row in `frontend/src/screens/Detail.tsx` (verified `frontend/src/screens/Detail.tsx:99-102`, alongside `<SaveButton>`/`<DirectionsLink>`). It renders **only** when `card.geo?.geometry` is non-null (a route exists to export). When geometry is `null`, the action does not render.
**AC-3.2:** The action is an `<a download href="{apiBase}/trail/{encodeURIComponent(card.id)}/export.gpx">` (a real download link, not a fetch) — `card.id` is the canonical id (verified `frontend/src/data/http/httpPlanner.ts:64` maps `id: c.canonical_id`). `apiBase` comes from `import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'`, matching the existing pattern (`frontend/src/data/PlannerProvider.tsx:20`); factor it into a small helper `gpxExportUrl(id)` in `frontend/src/data/geo.ts` (next to `trailheadDirectionsUrl`, `frontend/src/data/geo.ts:249`) so the base-URL rule lives in one place.
**AC-3.3:** The action styles as an `action-chip` consistent with `<DirectionsLink>`/`<SaveButton>` and carries an accessible label (e.g. `aria-label="Download the {name} route as a GPX file"`) and a Lucide glyph via the existing `<Icon glyph={…}>` wrapper. **glyphs.ts has no fitting entry** (verified: no `download`/`hardDrive`/`export`), so add exactly one `download: Download` entry + the `Download` import to `frontend/src/screens/glyphs.ts` (MERGE-HOT — see Files-touched). The label is text, never colour/glyph-only (a11y parity with the sibling chips). **Build the chip INLINE in `Detail.tsx` as an `<a download>` — do NOT add a new component to `frontend/src/screens/cardParts.tsx`** (cardParts is out-of-fence and merge-hot, Epic 020×021). Detail.tsx does not currently import `Icon`, so add `import { Icon } from '../components'` to Detail.tsx (verified: `Icon` is exported from `../components`, alongside `Confidence`/`Signal`/`Staleness` which Detail already imports from there).
**AC-3.4:** A vitest test (mirroring `frontend/src/screens/Detail.test.tsx`) asserts: the link is present with the correct `href` when `card.geo.geometry` is set, and absent when `card.geo` is undefined or `card.geo.geometry` is `null`.

---

## Definition of Done
- [ ] All ACs covered by at least one passing test (`api/gpx.py` unit tests + `GET …/export.gpx` endpoint tests with a fake GraphClient in the `tests/test_trail_detail_endpoint.py` style; `Detail.test.tsx` frontend test).
- [ ] `make check` green (`ruff format --check` + `ruff check` + `mypy` + `pytest -m "not neo4j"`).
- [ ] Frontend green: `npm run build` (tsc `--noEmit` + vite build) and `npm run test` (vitest) in `frontend/`.
- [ ] Rule #5 guard test present: the endpoint issues the world-only `trail_detail` Cypher and reads no personal-overlay node (AC-2.2).
- [ ] Elevation gate test asserts the **expected empty-`<ele>`** path (length mismatch → no altitude anywhere) as well as the aligned-fixture path; **empty-`<ele>` on real trails is documented as expected, not a bug (D4.3)** — no resampling/interpolation added.
- [ ] Existing-trail-with-unprocessable-geometry returns **422** (not 404, not a 200 with an empty seg) and is tested (AC-2.6).
- [ ] `frontend/src/screens/glyphs.ts` edit limited to one `download: Download` line + import (MERGE-HOT with Epic 021 — flag in PR).
- [ ] Targeted self-review over the diff; every CRITICAL fixed.
- [ ] Epic file copied into `docs/epics/`, index row added to `docs/epics/README.md`.
- [ ] Committed and pushed on `claude/gpx-export`; PR opened into `main`, titled `Epic 028: GPX export + Send-to-device — FOR REVIEW`, stating it must merge AFTER Epics 22 and 24.
