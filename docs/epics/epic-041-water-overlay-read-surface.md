# Epic 041 — Water overlay read surface (Detail answer + map markers)

**Status:** REVIEW
**Phase:** 1 (personal-intelligence app; Detail-page surface)
**Spec refs:** Epic 035 (the three primitives this consumes) ·
`docs/research/ux-review-conditions-2026-07.md` (the "answer, not a ledger row"
critique this epic must honor) · CLAUDE.md **Rule #1** (source-or-silence) ·
**Rule #3** (water POIs are slow/structural, correctly persisted) · CDP-02
(three-way legible silence) · design-system §4.3 (never color alone) / §7
(hedge without clutter).

---

## Capability statement

The 288 ingested `:WaterSource` nodes become an **answer on the Detail page**:
one quiet line in the trail-facts area that answers *"can I refill, or do I
carry everything?"*, plus quiet markers on the existing Detail map showing
*where*. No feed/card change (the feed is contested by two concurrent lanes
and the UX review says cards are already overloaded). Today
`water_sources_near` is called by **nothing** — classic data-without-an-answer.

## Architectural context

**Builds on:**
- `graph/queries.py::water_sources_near` — Epic 035's pure `(cypher, params)`
  world-public read: `:WaterSource` within `radius_m` of a **single point**,
  nearest first. It is point-proximity, NOT route-proximity — so any copy that
  claims "near the route" must be earned by API-layer math over the route
  geometry, never asserted from a bare point query.
- `api/app.py::trail_detail` (`GET /trail/{canonical_id}`) — the Detail
  endpoint; already reads the trail row (route WKT, trailhead, elevation).
- `frontend/src/screens/Detail.tsx` + `map/TerrainMap.tsx`/`MapPanel.tsx` —
  the Detail surface and its MapLibre map (marker precedent:
  trailhead/summit/cursor markers).
- The `PlannerClient` seam (`frontend/src/data/source.ts`) — mock ⇄ live
  swap point; the water read gets its own method so mock mode can demonstrate
  all three states.

**Does NOT include:**
- **No feed/card change** — no `FeedCardResponse` field, no card UI. The two
  in-flight feed lanes (`claude/epic-040-two-phase-render`,
  `claude/ux-lane1-one-sky-one-verdict`) stay unblocked.
- **No conditions-system change.** Water is a **trail fact** (slow/structural
  corpus data), NOT a seventh condition kind — it never enters
  `ConditionStates`, the six-state vocabulary, or the eval condition goldens.
  (NB: the existing condition kind literally named `"water"` is USGS
  **streamflow** — `orchestration/adapters/base.py` — an unrelated live probe.
  The wire field here is `water_sources` to keep the namespaces visibly apart.)
- **No potability claim, positive or negative** (Epic 035 Guard 2 carries
  over): location + type + seasonality only. No "safe", no "treat first" —
  disclosure of non-verification is allowed; advice about treatment is not.
- **No ingest change.** Known gap, disclosed not papered over: the water
  runner (`ingestion/ingest_water.py`) writes `ingest_version = region_id`,
  not a date — so **no honest ingest timestamp exists** on these nodes. The
  surface therefore shows source + an explicit "not verified live" hedge and
  **no fabricated stamp**. Follow-on: persist a real `fetched_at` at ingest,
  then add the stamp here.
- **No StaticRoute (non-WebGL fallback) markers** — the fact line above the
  map still carries the whole answer; markers are the secondary "where".

### Binding decisions

1. **Distance honesty.** `water_sources_near` measures from one point. The API
   fetches coarsely (30 km from the trail's anchor point) and then computes
   each source's distance as the **minimum great-circle distance to the route
   vertices** (`basis: "route"`); a trail with no drawable route falls back to
   distance from its start point (`basis: "start"`). Copy must name the basis
   ("of the route" / "of the start") — never claim route proximity that wasn't
   computed.
2. **CDP-02 three-way silence** (the load-bearing distinction):
   - **Answered (sources):** water within the near radius → the one fact line
     + markers.
   - **Answered-empty:** the coarse fetch proves the corpus has water mapped
     around this trail, but none within the near radius → a calm
     "No mapped water … — carry what you need." This is an ANSWER, styled
     calm — never the terracotta couldn't-verify treatment.
   - **Silence (not-fetched):** the coarse fetch returns nothing (region never
     water-ingested) or the read fails → `water_sources: null` on the wire and
     **no row at all** in the UI. Absence of coverage is silence, never an
     answered-empty claim.
3. **Degrade, never 500.** The water read is enrichment on the Detail payload:
   any exception inside it degrades to `null` (silence) with a log line —
   mirroring the maps batch-read posture.
4. **Attribution (ODbL).** Every rendered water fact names OpenStreetMap; the
   Detail map already carries the persistent "© OpenStreetMap" credit.
5. **Near radius = 200 m** (`~650 ft`), a constant on the API (`radius_m` is
   echoed on the wire so the client renders the number it was actually
   filtered by, not a hardcoded twin).

---

## Stories

### S1 — API: the water read on `GET /trail/{canonical_id}`

**AC-1.1:** `api/schemas.py` gains `WaterSourceResponse` (`water_id`,
`water_type`, `name`, `lat`, `lon`, `distance_m`, `seasonal`, `source`) and
`TrailWaterResponse` (`state: "sources"|"none_nearby"`,
`basis: "route"|"start"`, `radius_m`, `source`, `sources`); `TripDetailResponse`
gains `water_sources: TrailWaterResponse | None = None`. No field name contains
`potable`/`drinkable`/`safe`/`drink` as a claim token (the `drinking_water`
OSM category value is exempt, per Epic 035 Guard 2). A test asserts the guard
over the new schema field names.
**AC-1.2:** `api/app.py::_water_sources(session, row)` implements binding
decision 1 + 2: coarse `water_sources_near(anchor, 30_000 m)` → route-vertex
(or start-point) exact distance → filter to ≤ 200 m, sorted nearest-first,
capped. Tests cover: sources found (route basis), start-point fallback
(no geometry), answered-empty, coverage-silence (`None`), and exception →
`None`.
**AC-1.3:** The endpoint attaches the result; the maps wire-contract test
(`tests/test_maps_contract.py`) stays green and gains the new wire types in
its `EXPECTED` table (three-way lock: TS ⇄ EXPECTED ⇄ Pydantic).
**AC-1.4:** `FeedCardResponse` is untouched (no feed change).

### S2 — Frontend: one answer line in the Detail facts area

**AC-2.1:** A `trailWater(id, scope)` method on `PlannerClient`; the HTTP
adapter GETs `/trail/{id}` and maps `water_sources` → `TrailWaterVM`
(null on HTTP failure/404 — silence, never an error surface); the mock adapter
returns fixtures demonstrating all three states.
**AC-2.2:** `Detail.tsx` renders ONE water line under the decision facts:
- sources: `Water: 2 springs, 1 tap within ~650 ft of the route` + a one-line
  hedge `From OpenStreetMap — not verified live` (appending `· springs may be
  seasonal` when any spring or `seasonal`-tagged source is present).
- answered-empty: `No mapped water within ~650 ft of this route — carry what
  you need.` (calm, muted; NOT the flagged treatment) + the same OSM basis note.
- null: **no row** (silence).
A pure helper (`frontend/src/data/water.ts`) derives the copy (counts by type,
pluralization, ft/mi formatting, basis word) and is unit-tested.
**AC-2.3:** The line uses semantic type tokens only (no new hardcoded rems)
and the Lucide `Droplet` glyph via the `<Icon>` wrapper (aria-hidden +
sr-only label, Epic 021 pattern). Glyph meaning registered once in
`glyphs.ts`: mapped water source, nothing else.

### S3 — Frontend: quiet markers on the Detail map

**AC-3.1:** `MapPanel` renders one small, quiet marker per near source
(distinct from trailhead/summit/cursor/me markers), with an accessible name
(`role="img"` + `aria-label`, e.g. "Spring — Furnace Spring, about 120 ft
from the route") and a native `title` label carrying type + name + "OSM".
Never color alone: the marker is a distinct shape/glyph, not just a hue.
**AC-3.2:** Markers appear only in the `sources` state; the static fallback
and the no-geo state render no markers (the fact line still answers).

### Definition of Done
- [ ] All ACs covered: backend in `tests/test_water_surface.py` (hermetic — no
      DB, no network) + contract test updated; frontend in `water.test.ts`,
      `httpPlanner.test.ts`, `Detail.test.tsx`.
- [ ] `make check` green; frontend `npm test` + `npm run test:a11y` green;
      condition-state goldens untouched.
- [ ] Rule #1 guard test over the new schema field names.
- [ ] Ingest-timestamp gap disclosed in the PR body (no fabricated stamp).
- [ ] Epic row added to `docs/epics/README.md`; `scripts/gen_epic_index.py`
      run; status flipped on merge-readiness.
