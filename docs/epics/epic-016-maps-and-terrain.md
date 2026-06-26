# Epic 016 — Maps & Terrain (topographic Detail map · route · elevation profile)

**Status:** DEFINED
**Phase:** 1 (pulled forward — first dogfood finding; realizes the Stage-10 Detail spec)
**Spec refs:** `home-curation-prototype-spec-v0.3` §C3 + Detail block `[2. map / terrain]` · `stage-1-data-sources` (OSM geometry spine, USGS 3DEP elevation) · CLAUDE.md Rule #1 (source-or-silence) · Rule #2 (confidence) · Rule #4/#5 (access-scoped personal data) · T6 / roadmap R1 (ODbL licensing)

> **Ratified 2026-06-26 (PM + Josh):** (1) **MapLibre GL JS** is the engine (D1). (2) **First ship includes the elevation profile** — *not* a topo-only Phase A; the route map and the elevation chart land together (changes the build sequence + DoD below). (3) **Offline (S7) is a fast-follow**, not in the first ship (D8). Topo source (D2) stands as proposed: **USGS National Map primary, OpenTopoMap fallback** (revisit if non-US coverage is needed). **Consequence:** the USGS-3DEP elevation enrichment (S5a) is now a **gating prerequisite** for the first ship — likely its own corpus/ingestion epic that this one depends on (see Open Question 4/5).

---

## Capability statement
A user can see **where a recommended hike actually is and what the day's terrain looks like** — an interactive topographic map on the Detail screen showing the trail's real route over USGS contours, with an elevation profile of the climb — so a trip can be judged spatially, not just read as text. (Closes the first dogfood finding: *"maps, we have no maps. i can't see shit."*)

## Architectural context

**Builds on:**
- **The geometry already exists in the graph.** `CanonicalTrail.geom_wkt` holds the route line (computed at ingest via Shapely/GDAL), `Trailhead.point` + `CanonicalTrail.point` hold coordinates (POINT-indexed). The data to draw the route and locate the trailhead is present today — it is simply **not exposed through the API**.
- **The typed data-source seam** in the frontend (Home/Detail render off a mock/HTTP seam). The map consumes the same trip contract, extended with geometry — no new data path, just new fields.
- **Epic 013 (LiveAdapter seam, TTL).** Topo/imagery tiles are external sources; tile fetching belongs to the map library, but the attribution + degrade-and-disclose posture mirrors 013.

**Enables:**
- Spatial judgment of every recommendation — the "place-making" the v0.3 design deliberately moved from the card to Detail.
- A foundation for later spatial features: a personal-history overlay ("you've been here" — ties to the Epic 006 `been_on` producer), a multi-trip map view, and in-field orientation.

**Does NOT include:**
- Turn-by-turn / on-trail GPS navigation. (Deep-linking the native maps app for *driving to the trailhead* is in scope; on-trail nav is not.)
- Trail drawing/editing.
- Building the USGS 3DEP elevation-enrichment pipeline beyond what S5 specifies — if that ingestion seam is unbuilt, the elevation **profile** is a phased follow-on (see S5 + Risks). Total ascent already exists; only the *curve* needs 3DEP.
- Full offline-region download. (S7 caches only an *opened* trail; a region downloader is future.)

## Design decisions (proposed — ⭐ ratify before build)

**D1 — Map library: MapLibre GL JS. ✅ RATIFIED.** Open-source (BSD), zero per-tile vendor cost or lock-in (unlike Mapbox/Google), renders raster topo tiles **and** vector route overlays **and** optional hillshade/3D terrain — the ceiling for "interactable + topographic." React integration via `react-map-gl` (maplibre mode). (Leaflet was the simpler fallback; not chosen.)

⭐ **D2 — Topographic basemap: USGS The National Map (USGS Topo) as primary.** Public-domain, authoritative USGS quad topography with **contour lines baked into the tiles** — so "see the terrain shape" needs *no new backend data*. Layers, all free + license-clean: **Topo** (default) · **Imagery** (USGS aerial) · **Hillshade**. *Global fallback outside US coverage:* OpenTopoMap (OSM + SRTM, ODbL/CC-BY-SA). Aligns with the project's existing USGS/3DEP/open-data posture.

**D3 — Route geometry: the graph's `geom_wkt`, exposed as GeoJSON at the API boundary.** Convert WKT → GeoJSON LineString server-side; the trailhead `point` becomes the start marker. (S1.)

**D4 — Elevation profile: precomputed at ingest from USGS 3DEP, stored as a sampled array on the trail, exposed via the API.** Precompute (not runtime terrain queries) = fast, offline-capable, cheaper per the R5 cost posture. *This is the one piece that depends on the as-yet-unbuilt 3DEP enrichment seam* → phased (S5; see Risks).

**D5 — Honesty on geometry (Rule #1 source-or-silence, applied to maps):** never fabricate a route. No `geom_wkt` → trailhead point + *"route not mapped — trailhead only."* Low-confidence conflation geometry → a **dashed** "approximate route" + a confidence note, reusing the existing Confidence/Staleness primitives. The map obeys the same honesty contract as the cards.

**D6 — Performance: the map library is code-split and mounted only on Detail.** The scrolling feed **never** mounts a live map — cards carry a static, pre-rendered terrain/elevation *glyph* (an SVG sparkline), per the v0.3 rule that the rich map lives on Detail. Protects the calm feed and the bundle.

**D7 — Attribution (T6/R1): persistent, legible credit on every map** — USGS (basemap) + OpenStreetMap / ODbL (the route geometry is OSM-derived). Non-dismissable, in the map chrome. License compliance is a release gate, not a nicety.

**D8 — Offline scope: ✅ RATIFIED as a fast-follow** (not in the first ship). S7 ships an opt-in *"make available offline"* cache of an **opened** trail (its in-view tiles + the route + the profile) via the PWA service worker — enough that a trail you opened at home works at the trailhead with no signal — but as the build immediately *after* the first map ships. Full offline-region download is explicitly future.

## UX deep-dive

### A. The feed card (at rest) — a glyph, not a map
Per v0.3 C3, the scrolling card carries "enough to read the shape of the day," not a live map. Add a compact, **static terrain glyph**: a small SVG elevation sparkline (the climb's profile shape) alongside the ascent figure already shown. It reads the *character* of the day at a glance — a punchy 2,500-ft wall vs a flat amble — without the cost or distraction of a live map in the feed. Tapping the card does exactly one thing: Open Detail (v0.3 C2). No profile data → the glyph degrades to the ascent figure alone; never a faked curve.

### B. The Detail screen — the map block (`[2. map / terrain]`)
Layout: directly under the viability summary (drive · distance · ascent · duration), a map panel ~40–55% of viewport height, with the elevation profile as a linked strip beneath it.

**At rest (default view):**
- Topographic basemap, centered + zoomed to fit the trail's bounds.
- The **route** drawn as a clear line — solid for confident geometry, dashed for approximate (D5).
- A **trailhead marker** at the start; a subtle ▲ summit/end marker where known.
- Contour lines (free from the topo tiles) give an immediate terrain read.
- Persistent attribution (D7) + a scale bar.

**Interactions (interactable):**
- Pan / pinch-zoom / (MapLibre) rotate + tilt.
- **Layer switch:** Topo ↔ Imagery ↔ Hillshade (a small control).
- **Tap the route →** a callout with elevation + distance-from-start at that point, which drops a synchronized marker on the elevation profile — and the reverse: scrubbing the profile moves a marker along the route. This map↔profile link is the heart of the place-making.
- **Fullscreen:** the Detail map is compact; a tap expands it to a full-screen explorable map (back gesture returns) — real exploration without leaving the calm of Detail.
- **Locate me:** device-GPS blue dot, permission-gated and lazy (only on tap), so at the trailhead you see yourself relative to the route.
- **Directions to trailhead:** deep-link the native maps app for *driving* directions to the trailhead point (complements the Valhalla drive-time already computed — Epic 005/013). On-trail navigation is explicitly out of scope.

### C. The elevation profile
A chart beneath the map: x = distance, y = elevation; total gain/loss + max grade labeled in text (which doubles as the accessibility fallback). Scrub-syncs with the map marker (B). If 3DEP profile data is absent (S5 not yet landed), the strip degrades to the ascent figure + a one-line *"detailed elevation profile coming soon"* — honest, not faked.

### D. Empty / low-confidence / offline states (honesty)
- **No geometry:** trailhead marker + *"route not mapped — trailhead only."*
- **Low-confidence geometry:** dashed route + *"approximate route (low source agreement)."*
- **No signal, trail not cached:** last-cached tiles (or a neutral background) + the route, which is app data and always renders + a *"map tiles unavailable offline"* notice. The route shows even when tiles don't.
- **Tiles fail to load:** the route over a neutral background + a retry; never a blank panel with no context.

### E. Accessibility
- All controls keyboard-operable + labeled (React-Aria).
- The map has a text equivalent (the viability summary gives distance/ascent/duration); the profile exposes an accessible summary (total gain/loss, steepest grade and where).
- Color is never the only signal — confidence uses the existing typographic tier, not hue alone (v0.3 C4).

## Stories

**Build sequence (ratified):** the **first ship = S1–S6** (the topo map **and** the elevation profile together). The elevation backend (S5a) is now its own epic — **Epic 017 (terrain elevation enrichment)** — which builds **in parallel** with this one: the map + route stories (S1–S4, S6) build against mock data while Epic 017 produces the real profiles; the two lanes converge at **S5b** (the chart consuming real elevation). The shared **elevation-profile contract (Epic 017 S0)** is the only thing that must be frozen before the lanes split. **S7 (offline) is the fast-follow; S8 is future.** (The earlier topo-only "Phase A first" split is retired by the ratified decision.)

### Phase A — core slice

**S1 — API exposes route geometry + trailhead**
**Given** the graph stores `geom_wkt` + `Trailhead.point` / `CanonicalTrail.point`
**When** the app requests a trip's detail
**Then** the contract returns the route as GeoJSON + the trailhead coordinate.
**AC-1.1:** The trip/detail response includes `geometry` (GeoJSON `LineString`, WGS84) derived from `geom_wkt`, plus a `trailhead {lat, lon}` from the trailhead (or representative) point.
**AC-1.2:** A trail with no `geom_wkt` returns `geometry: null` + the trailhead point (drives D5's "trailhead only" state) — never an empty or fabricated line.
**AC-1.3:** WKT→GeoJSON conversion is unit-tested incl. a multi-segment line; coordinate order is `(lon, lat)` per the GeoJSON spec.
**AC-1.4:** The frontend trip type + **both** data-source adapters (mock + HTTP) carry the new fields; the **mock fixture gains real sample coordinates** so the map renders before live-data wiring (closes the "mock has no coordinates" gap).

**S2 — Detail topographic map with the route**
**Given** a trip detail with geometry
**When** the Detail screen renders
**Then** a topographic map shows the route + trailhead, fit to bounds.
**AC-2.1:** MapLibre (⭐D1) renders the USGS Topo basemap (⭐D2) **on Detail only**; the library is code-split — a bundle check confirms the feed route does not import the map lib (D6).
**AC-2.2:** The route `LineString` renders fit-to-bounds with a trailhead marker; solid line for confident geometry.
**AC-2.3:** Pan + pinch-zoom work on touch; the panel does not hijack page scroll (a one-finger page-scroll passes over it; the map pans on direct interaction).
**AC-2.4:** Persistent USGS + OSM/ODbL attribution and a scale bar are visible (D7).

**S3 — Honest geometry states**
**Given** trails with missing or low-confidence geometry
**When** Detail renders the map
**Then** the map discloses rather than fabricates.
**AC-3.1:** `geometry: null` → trailhead marker + "route not mapped — trailhead only"; no line drawn.
**AC-3.2:** Low-confidence geometry → dashed route + an "approximate route" note via the existing confidence primitive.
**AC-3.3:** Tile-load failure → the route still renders over a neutral background + a non-blocking notice; never a blank panel.

**S4 — Feed card terrain glyph**
**Given** the scrolling feed
**When** a card renders
**Then** a static terrain/elevation glyph reads the shape of the day, with no live map mounted.
**AC-4.1:** Each card shows a static SVG elevation sparkline derived from the profile (ascent-only fallback) — no map library on the feed code path.
**AC-4.2:** Cards with no profile degrade to the ascent figure; no faked curve.
**AC-4.3:** Tapping a card opens Detail (no in-card map expansion) — preserves v0.3 C2.

### Phase B — richness

**S5 — Elevation profile (USGS 3DEP) + map↔profile sync** ⭐ *(depends on the 3DEP enrichment seam)*
**Given** 3DEP elevation sampled along the route
**When** Detail renders
**Then** an elevation profile strip shows the climb and scrubs in sync with the map.
**AC-5.1:** An enrichment step samples 3DEP elevation along `geom_wkt`, stores a profile array on the trail, and exposes it via the API (extends S1).
**AC-5.2:** The strip plots distance × elevation with total gain/loss + max grade labeled; absent data degrades to the ascent figure + an honest "coming soon."
**AC-5.3:** Scrubbing the profile moves a synchronized marker on the route; tapping the route moves the profile cursor.
> If the 3DEP enrichment seam is unbuilt, S5 splits: **S5a** = backend enrichment (sample + store + expose), **S5b** = the chart + sync. S5b can ship behind the "coming soon" degrade until S5a lands. *This is the determinant of whether Phase B is near or far — see Open Question 4.*

**S6 — Layers, fullscreen, locate-me, navigate**
**AC-6.1:** A layer control switches Topo / Imagery / Hillshade (all free sources).
**AC-6.2:** A fullscreen toggle expands the map to a full-screen explorable view; back returns to Detail.
**AC-6.3:** "Locate me" requests device geolocation **only on tap** (permission-gated) and shows the user dot; denial degrades with a note.
**AC-6.4:** "Directions to trailhead" deep-links the native maps app to the trailhead point (driving) — no in-app on-trail nav.

### Phase C — future (flagged, not committed in this epic)

**S7 — Opt-in offline cache of an opened trail** ⭐D8
**AC-7.1:** A "make available offline" action caches the in-view topo tiles + the route + profile via the service worker so the opened trail renders with no signal.
**AC-7.2:** The route + profile (app data) always render offline even when tiles can't; a clear offline indicator shows.
> Ratify whether S7 ships in this epic or as a fast-follow.

**S8 — Personal-history overlay** *(future)*
**AC-8.1:** Past episodes' tracks render as a "you've been here" overlay, **access-scoped to the viewer** (Rule #4/#5); novelty / `been_on` shading ties to Epic 006. Out of scope for the first build; captured so the map foundation anticipates it.

## Definition of Done (first ship = S1–S6, route map **and** elevation)
- [ ] S1–S6 ACs covered by passing tests; `make check` green; frontend tests green.
- [ ] **S5a prerequisite met:** USGS-3DEP elevation is sampled along each trail's `geom_wkt`, stored, and exposed via the API (its own epic if scoped that way — Open Q 4/5).
- [ ] Detail shows a USGS topo map with the real route + trailhead (fit to bounds) **and** the elevation profile that scrubs in sync with the map, on a phone; the feed stays map-free and fast.
- [ ] Honest states (S3) verified incl. a no-geometry case and a tile-failure case.
- [ ] Attribution (USGS + OSM/ODbL) present and non-dismissable.
- [ ] Map library (MapLibre) is code-split — feed bundle unaffected (measured).
- [ ] Deployed to the Vercel preview and scrolled on a real phone.
- [ ] **S7 (offline) is the fast-follow**; S8 (personal-history overlay) is future.

## Open questions / NEEDS-PM-DESIGN
1. ✅ **Map library** — MapLibre (ratified).
2. ✅ **Topo source** — USGS National Map primary + OpenTopoMap fallback (stands; revisit for non-US coverage).
3. ✅ **Offline (S7)** — fast-follow (ratified).
4. **3DEP enrichment (S5a) — now on the critical path.** The first ship includes elevation, so the USGS-3DEP enrichment must land first. Is the corpus enrichment seam (Stage 3 §7) ready, or does it need building? This is the single biggest unknown on the timeline.
5. **Ownership of the elevation precompute** — the *sample + store* (S5a) likely belongs to its **own corpus/ingestion epic** that Epic 016 depends on; the *chart + sync* (S5b) stays here. **Next PM step:** scope that elevation-enrichment epic so S5a has a home.

## Risks / notes
- **Elevation dependency (S5a):** the 3DEP enrichment join is the known unbuilt seam (corpus-source enrichment gap). Phase A is designed to ship *without* it — contours come free from the topo tiles, so "see the terrain" does not wait on 3DEP.
- **Tile rate limits / cost:** heavy USGS tile use may warrant a cache/proxy later (ties the R5 cost posture); not a Phase-A concern at personal scale.
- **Bundle size:** MapLibre is non-trivial; D6's code-split (Detail-only) is the mitigation and is an explicit AC (AC-2.1).
- **Licensing (T6/R1):** the route geometry is OSM-derived → ODbL attribution is mandatory and is gated by AC-2.4; this is the same separability/attribution thread that gates the public commons.
