# Trail Connectivity & Loop Composition — Problem Definition and Landscape

*How trails link into networks and hikes compose into loops/out-and-backs: the problem defined in three layers, where today's architecture stands, the open-source foundations, the bad-loop screen, the "worth recommending" scale, and a sequenced adoption path. Idea credit: Carter.*

**Last verified:** 2026-07-11 · **Owner:** research · **Status:** `ACTIVE` (spike executed 2026-07-11 — §9; backlog entry B010)

> **Status:** analysis + executed spike — nothing is built in the product. §1–8 grounded against the repo at `main` (b7d876d) and external sources fetched 2026-07-09; the §8 spike ran 2026-07-11 against live Overpass data (results in §9, including the falsification-test pass). External claims carry URLs, repo claims carry `file:line`. Unverified items are flagged inline.
> **PO decisions (2026-07-11, Josh):** run the spike now ✅ (done, §9) · first build slice = **Layer-1 topology** ✅ · sequencing = **build at Phase E alongside E1**, path-to-complete spine intact ✅.
> **Legend:** ✅ established · 🔶 recommended, confirm · ❓ open

---

## 0. TL;DR

Every serious trail product treats a **hike** and a **trail** as different objects: a hike is a *composition* of trail segments through junctions (White Oak Canyon as an out-and-back, or joined with Cedar Run via two connectors into the classic 8-mile circuit). Our graph today is a **flat set of ~1.5–2.2k independent `:CanonicalTrail` nodes** — full geometry stored, but never noded into a network; two trails that physically touch share no structure. The good news: the Stage-2 schema *designed* for exactly this (`:Junction`, `CONNECTS_TO`, a deferred `:Route` node) and deliberately deferred it, so this is a build on a prepared foundation, not a rework.

The recommended shape is **enumerate–screen–curate, not generate**: derive a junction/segment network at ingest (the pattern AllTrails documents for its own OSM-derivative segment database), enumerate bounded candidate compositions offline in the background-ranking layer, screen them non-compensatorily (access/informal/sac_scale/ford/closure — the OSM Trails Stewardship Initiative tag set), and surface only compositions that pass — each carrying **composition provenance** (agency-published circuit ≻ OSM route relation ≻ our derived inference, hedged per Rule 7). This is the honesty-first counter-position to AllTrails' AI route generator, which drew documented search-and-rescue criticism in 2025 precisely because generated compositions inherited the trust of curated entries. The *build* is **gated on Phase A identity stability** (the slug-collision audit + re-runnable ingest) and lands at Phase E alongside E1; the one-region spike **has been run and its falsification target passed** — the enumerator rediscovered the NPS Cedar Run–Whiteoak Circuit from structure alone and ranked it #1 (§9).

---

## 1. The problem, defined precisely

"AllTrails links trails together" compresses three distinct problems. Naming them separately is most of the refinement:

**Layer 1 — Topology (a data problem).** Which trails physically connect, where? This is a *derived structural fact*: junctions are computable from geometry we already store (`route_geom_wkt`, per-segment `geom_wkt`). Output: a noded network — junction vertices, segment edges, and trail-to-trail adjacency. Slow-changing, deterministic, belongs in the corpus (Rule 3: slow/structural).

**Layer 2 — Composition (a modeling problem).** What is a *hike* as a first-class object? A named trail is not a hike; a hike is an ordered walk over the network with a shape:

| Shape | Definition | Product prevalence |
|---|---|---|
| Out-and-back | to a point and return on the same tread | AllTrails route type 1 |
| Loop | closed walk, minimal repeated tread | AllTrails route type 2 |
| Lollipop | out-and-back stick + loop candy | folded into "Loop" by AllTrails; named formally by NPS ([Acadia](https://www.nps.gov/acad/planyourvisit/hike-loops.htm)) |
| Figure-8 | two loops sharing a junction | NPS publishes named ones ([Bryce](https://www.nps.gov/thingstodo/figure-8-combination.htm)) |
| Point-to-point / shuttle | start ≠ end | AllTrails route type 3 |

AllTrails ships only three route types as a first-class filter ([route types](https://support.alltrails.com/hc/en-us/articles/360019246371-Trail-route-types)); the finer shapes collapse into them. **Hiking Project has the cleanest public data model**: a *trail* (single named tread, as on a printed map) is explicitly distinct from a *recommended route* (a guidebook-style composed hike over one or more trails) ([overview](https://www.hikingproject.com/help/21/overview-of-site-name-features)). That trail-vs-route split is the industry-consensus model, and it is exactly the `:CanonicalTrail` vs `:Route` split our decision-log already names and defers (`docs/decision-log.md:238`, §28).

**Layer 3 — Judgment (a curation problem).** Of the combinatorially many walks the network permits, which are *hikes a person would want*? This is where every incumbent either spends human editors (AllTrails' moderator-verified routes), community exhaust (komoot's Smart Tours from recorded-tour density), or gets in trouble (generated routes with no judgment layer — §5). Judgment decomposes into a **hard screen** (never propose: private land, social trails, dangerous fords…) and a **soft score** (worth proposing: highlight anchoring, low connector fraction, low repeated tread, right effort band) — which is precisely our Principle 11 shape: *non-compensatory screen, then compensatory rank*.

### The grounding example: Whiteoak Canyon, Shenandoah

One canyon trail, at least four products, all NPS-published:

- **Lower falls out-and-back** — ~2 mi RT, ~500 ft ([NPS](https://www.nps.gov/thingstodo/lower-whiteoak-falls.htm)).
- **Upper falls out-and-back** from Skyline Drive — 4.6 mi RT, ~1,040 ft ([NPS](https://www.nps.gov/thingstodo/upper-whiteoak-falls.htm)).
- **Cedar Run–Whiteoak Circuit** — 8.1 mi, 2,794 ft, "very strenuous": down Cedar Run Trail, up Whiteoak Canyon Trail past six waterfalls, closed by **two connectors** — the Whiteoak Canyon Fire Road and the Skyland–Big Meadows Horse Trail ([NPS](https://www.nps.gov/thingstodo/cedar-run-whiteoak-circuit.htm)).
- **Longer variants** via Hawksbill summit or the Limberlost junction ([NPS junction page](https://www.nps.gov/places/whiteoak-trail-limberlost-trail-junction.htm)).

Three structural lessons sit in this one example. (1) **The loop exists only because of two "boring" connectors** — a fire road a guidebook calls "a relatively dull and uneventful connector" ([Live and Let Hike](https://liveandlethike.com/2018/07/09/whiteoak-canyon-cedar-run-trail-loop-shenandoah-national-park-va/)); connector tolerance is a scoring dimension, not a bug. (2) **"The loop" is a family, not a point** — published lengths vary 8.1–9.5 mi depending on which trailhead anchors it and the direction of travel; a route object must be anchored to a trailhead + direction. (3) **AllTrails encodes each composition as a separate curated entry** (four+ distinct "trails" for this canyon, e.g. [the circuit](https://www.alltrails.com/trail/us/virginia/white-oak-canyon-and-cedar-run-trail-loop) with 3,580 reviews) — their "linking" is largely *human curation over an auto-derived segment graph*, not a route generator.

---

## 2. Where today's architecture stands

**Designed for it, deliberately deferred, materially absent.** The evidence:

What exists ✅:
- Full assembled geometry per trail (`route_geom_wkt`) and per `:Segment` (`geom_wkt`), loaded at `graph/load.py:189-270`; ordered polyline stitching already exists (`ingestion/route.py` `_assemble_lines`).
- The schema design names the whole substrate: `:Junction` ("a shared network node where segments meet… derived from geometry"), `(:Segment)-[:STARTS_AT|ENDS_AT]->(:Junction)`, `(:CanonicalTrail)-[:CONNECTS_TO]->(:CanonicalTrail)` (`docs/research/stage-2-schema.md:24-42`) — and §28 of the decision-log settles "composed loops = a named `:CanonicalTrail` for v0; `:Route` deferred to Stage 5+" (`docs/decision-log.md:238`).
- An endpoint-connectivity primitive exists in one place: the 40 m same-name union-find in `consolidate_osm_segments` (`ingestion/pipeline.py:240-308`) — but it is *deliberately name-gated* and cannot connect differently-named trails.
- Card 16 of the graph-architecture review already adopted the routing discipline for when we build this: geometry immutable, costs query-time, an `analyzeGraph`-style topology-integrity gate in ingest, "no route" as a sourced empty-state, and **no precomputed CH-style shortcuts over ephemeral costs** (`docs/research/graph-architecture-patterns.md:277-288`). CDP-20 sits on the adopt-queue for Phases C/E (`docs/strategy/path-to-complete.md:120`).

What is missing (all confirmed by code survey):
1. **No junction/network model** — zero `:Junction` nodes, zero `CONNECTS_TO`/`STARTS_AT`/`ENDS_AT` edges anywhere in code. Two touching trails share nothing.
2. **Segments are intra-trail conflation units**, not network edges; their endpoints are never reified as shared vertices.
3. **OSM route relations are not ingested** — the fetch is way-only (`ingestion/fetch/osm.py:59`), so the AT superrelation and every named multi-way route is dropped (gap already logged at `docs/research/comaps-borrow-plan.md:201`, proposal E1).
4. **No `:Route` object; a recommendation is a single trail.** The `FeedCard` (`orchestration/engine.py:106-117`) is one `:CanonicalTrail`; the hike *is* the trail.
5. **`is_loop` exists in the schema but is never populated by ingest** (only the hand-seeded Old Rag node, `graph/schema.cypher:92`); `route_type`/out-and-back exist nowhere.
6. **No trail-routing engine** — Valhalla is wired for road drive-time only (`orchestration/adapters/valhalla.py`); B005 already flags the open question "Neo4j traversal or a dedicated router?" (`docs/process/backlog-ideas.md:101`).

So: **no, we are not solving this today — but the architecture anticipated it.** The raw material (WKT geometry in a property graph chosen partly for this) is present; the missing piece is an ingest-time noding pass + junction edges + a composition object + a judgment layer.

---

## 3. Open-source foundations — build on vs. learn from

### 3a. Data models (adopt the pattern)

- **OSM itself is the segment-vs-named-trail model**: ways (`highway=path/footway`, with `sac_scale`, `trail_visibility`, `surface`) are the tread; **route relations** (`type=route` + `route=hiking/foot`, with `network=lwn/rwn/nwn/iwn`) are named trails spanning many ways ([Tag:route=hiking](https://wiki.openstreetmap.org/wiki/Tag:route%3Dhiking)). We currently discard the relation half.
- **AllTrails documents doing exactly the noding pass we lack**: it pulls walkable OSM ways, then **re-cuts them into segments that start/end at way intersections**, stored in a derived database that powers its tiles and custom-route tool ([OSM derivative database methodology](https://support.alltrails.com/hc/en-us/articles/360019246411-OSM-derivative-database-derivation-methodology) — published *because ODbL share-alike obliges disclosure*, which will apply to our derivative too; see §7). Verified routes are hand-curated polylines *layered over* that segment graph ([verified routes vs OSM segments](https://support.alltrails.com/hc/en-us/articles/4410231246100-Verified-routes-vs-OSM-OpenStreetMap-segments)).
- **OpenTrails / Open Trail System Specification** (Code for America, 2014) formalized `trail_segments` (geometry) vs `named_trails` (grouping referencing segment IDs) + trailheads + stewards ([spec](https://github.com/codeforamerica/OpenTrails)); effectively dormant since ~2015 (🔶 judgment, not documented) — learn from, don't adopt.
- **Waymarked Trails** is the working reference implementation of relation assembly (incremental OSM→PostgreSQL preprocessing via [osgende](https://github.com/waymarkedtrails/osgende); GPL-3.0 — fine to study/run beside, don't embed).
- **USFS EDW trail centerlines** ship names/attributes but **no guaranteed noded topology** ([FSGeodata](https://data.fs.usda.gov/geodata/edw/datasets.php?xmlKeyword=trails)) — planarize ourselves regardless of source.

### 3b. Engines & algorithms (learn from; mostly don't need to run)

- **GraphHopper** (Apache-2.0) has the only first-class OSS round-trip algorithm: project N waypoints outward as a rough polygon of the target perimeter, route the legs, and penalize already-used edges ×5 via `AvoidEdgesWeighting` to force a genuine loop ([RoundTripRouting.java](https://github.com/graphhopper/graphhopper/blob/master/core/src/main/java/com/graphhopper/routing/RoundTripRouting.java)). **openrouteservice** (GPL-3.0) exposes the same idea as `round_trip.length/points/seed`; **BRouter** (MIT) added a round-trip mode in [PR #759](https://github.com/abrensch/brouter/pull/759); Valhalla and OSRM have none (verified by absence).
- **Trail Router** (closed, but the best public writeup of a hiking loop generator): custom foot profile + a precomputed per-way **green index** (fraction of a 30 m buffer overlapping park/forest/water) + generate-many-candidates-then-score ([How Trail Router works](https://trailrouter.com/blog/how-trail-router-works/)).
- **Academic frame**: fixed-length loop-finding is **NP-hard even optimizing length alone** — Gemsa/Pajor/Wagner/Zündorf, *Efficient Computation of Jogging Routes* (SEA 2013; greedy-faces and partial-shortest-paths heuristics run at interactive speed) ([Springer](https://link.springer.com/chapter/10.1007/978-3-642-38527-8_25)); the "maximize attractiveness under a length budget" version is the **Arc Orienteering Problem** family (Verbeeck et al. 2014, [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S1366554514000751); Gavalas et al. survey, [J. Heuristics 2014](https://link.springer.com/article/10.1007/s10732-014-9242-5)). Lesson: don't chase optimality; bounded heuristic enumeration + scoring is the state of practice everywhere.
- **OSMnx** (MIT) does the topological simplification step (collapse interstitial nodes, keep true geometry as an edge attribute) as a library ([Boeing 2024](https://arxiv.org/html/2407.00258v1)) — the natural tool for the ingest noding pass prototype; **momepy COINS** groups segments into continuous "strokes" by deflection angle ([docs](http://docs.momepy.org/en/latest/api/momepy.COINS.html)) — useful for continuation inference where names/relations are missing.

**The strategic conclusion from the landscape:** the freeform *generator* (GraphHopper-style random polygons) solves a different product — "give me any 10 km from my door" (a runner's problem). Our problem is **compositional**: enumerate the small set of *meaningful* walks over *named* trails anchored at trailheads and highlights. At region scale (thousands of segments post-noding), that is native graph work — Cypher/NetworkX-grade, done **offline in the background-ranking layer** where the four-layer architecture already has a home for it. We don't need to run a routing engine to ship this; GraphHopper/BRouter become relevant later for B005's freeform snap-to-trail drawing.

---

## 4. The recommended shape for us

### 4a. Three provenance tiers of a `:Route` — the honesty frame

The single most important design decision: **a composed route is a claim, and it carries provenance like any other claim** (Rule 7). Three tiers, in descending authority:

1. **Agency-published circuits** ✅ — the NPS *Cedar Run–Whiteoak Circuit* is a named, authority-tier-1, source-backed route (8.1 mi, 2,794 ft, "very strenuous", with warnings). These are *ingestable facts*, not inferences — NPS publishes them as structured "things to do" pages per park. Highest trust, ~zero judgment risk, and they double as ground truth for everything below.
2. **OSM route relations** ✅ — community-named multi-way trails (the AT, blazed loops). Real names, real identity, moderate authority; the CoMaps borrow plan's E1 already scopes fetching them.
3. **Derived compositions** 🔶 — *our* inference: "these 4 segments form an 8.3 mi loop from this trailhead." Presented hedged, never dressed as a named trail, always decomposable into its member segments with per-segment sources — "assembled from OSM segments (fetched …); NPS attests 2 of 4 legs."

This tiering is the differentiator. The documented failure of the field (§5) is *generated compositions inheriting the trust of curated entries*; our invariants make the counter-position nearly free.

### 4b. Data model (extends the settled taxonomy; no rework)

```
(:Junction {junction_id, point, degree})                      // derived at ingest from noded geometry
(:Segment)-[:STARTS_AT|ENDS_AT]->(:Junction)                  // segments re-cut at junctions
(:CanonicalTrail)-[:CONNECTS_TO {via_junction}]->(:CanonicalTrail)   // derived adjacency, symmetric
(:Route {route_id, shape, length_mi, gain_ft, provenance_tier, anchor_trailhead_id, direction})
(:Route)-[:HAS_LEG {order, reversed}]->(:Segment)
(:Route)-[:DERIVED_FROM]->(:SourceRecord | derivation record)  // tier 1/2: source; tier 3: derivation
(:Trailhead)-[:ACCESSES]->(:Route)
```

Everything here is Rule-3-compliant slow/structural data: junctions and adjacency are deterministic functions of geometry; routes reference immutable segments; **live conditions are never composed into the route object** — at plan time the Verifier runs JIT per-leg exactly as it does per-trail today, and weakest-link fusion (Principle 10) means one red leg caps the whole loop's verdict. Access control needs no new concept: routes are world-layer nodes; the personal overlay attaches to them as it does to trails.

Segment re-cutting changes segment identity → **this collides with the same Phase-A identity work as CoMaps E1** (`comaps-borrow-plan.md:212`) and must sequence behind the slug audit / `canonical_id` back-fill; do the identity scheme once (relations + noding together).

### 4c. Pipeline shape: enumerate → screen → score → curate

1. **Node the network** (ingest, per region): planarize all trail + connector geometries, quantize shared endpoints/crossings (the CoMaps O(n) endpoint-hash idiom E1 already borrows), emit `:Junction` + re-cut `:Segment` + `CONNECTS_TO`. Run the Card-16 integrity gate here: isolated components and dead-end pseudo-junctions are *found and quarantined at ingest*, and "no connected path" becomes a sourced empty-state. **This layer alone ships user value before any loop exists**: "connects to Cedar Run Trail, Limberlost Trail" on the Detail screen, honest `is_loop`/`route_shape` classification of every existing trail (closed geometry test — finally populating the dormant `is_loop`), and graph-aware proximity (a euclidean-near but unconnected trailhead stops appearing reachable).
2. **Enumerate candidates** (background ranking layer, offline): for each trailhead/anchor-highlight, bounded-depth cycle enumeration over the junction graph within an effort budget (say ≤ 20 mi perimeter, ≤ 6 junction-decisions) + the out-and-back/lollipop variants of every dead-end highlight. NP-hardness says don't seek optimal; region scale says exhaustive-within-bounds is fine offline.
3. **Screen** (non-compensatory, Principle 11): drop any candidate containing a forbidden edge (§5). A killed candidate is explainable: "ruled out — crosses private land (OSM access=private)."
4. **Score & keep top-N** (compensatory, §6), store survivors as tier-3 `:Route` candidates with confidence; the Curator ranks them with taste/novelty/party exactly as it ranks trails today. The feed stays finite: a handful of *verified compositions* per area, not an infinite generator.

---

## 5. Bad loops — the screen, and the cautionary record

**The documented failure mode.** AllTrails' AI "Custom Routes" (Peak tier, June 2025) drew on-record criticism from search-and-rescue: BC AdventureSmart's coordinator — "AI definitely encourages overconfidence" ([National Observer](https://www.nationalobserver.com/2025/06/17/news/alltrails-ai-tool-search-rescue-members), corroborated by [InsideHook](https://www.insidehook.com/adventure/experts-concerns-ai-generated-hiking-routes)). Before AI entered: rescues off phantom paths the app showed but the mountain didn't have ([Causey Pike](https://outdoorsmagic.com/article/news-mountain-rescue-called-out-after-hiker-gets-misled-by-popular-navigation-app/)), a seven-week cluster of police callouts in Australia including the **braided-trail feedback loop** — each lost party's recorded track reinforces the false trail for the next ([trailhiking.com.au](https://www.trailhiking.com.au/navigation/issues-with-alltrails/)), and repeated rescues off a nonexistent Google Maps trail on Mount Fromme. The common root: **a router that treats every `highway=path` edge as equally traversable.**

**The tag vocabulary exists and is getting better.** The OSM US **Trails Stewardship Initiative** (OSM US + federal/state land managers, USGS-endorsed) exists precisely to make these distinctions machine-readable: `informal=yes` (social trail), `operator=*` (someone maintains this), `access=no/private/discouraged`, with `sac_scale` and `trail_visibility` for difficulty/followability ([TSI wiki](https://wiki.openstreetmap.org/wiki/United_States/Trails_Stewardship_Initiative); Utah pilot: 1,100+ trail-miles updated ([OSM US](https://openstreetmap.us/news/2024/12/tsi-utah-update/))). The `sac_scale` wiki explicitly advises routers to exclude/heavily penalize `demanding_mountain_hiking`+ in default foot profiles.

**Our screen (hard, non-compensatory — a beautiful loop is never bought back):**

| Kill condition | Signal | Notes |
|---|---|---|
| Illegal / private | `access=no/private`, boundary layers | Rule-4 analog: filter at the query/data layer |
| Social / informal trail | `informal=yes` | never a proposed leg; disclose if adjacent |
| Officially discouraged | `access=discouraged` | TSI's legal-but-don't tag |
| Unmaintained / phantom-risk | no `operator` **and** poor `trail_visibility` | 🔶 combined test, not either alone — sparse tagging would over-kill |
| Scramble beyond band | `sac_scale ≥ demanding_mountain_hiking` | per-party override later (capability floor, not taste) |
| Unbridged ford | `ford=yes` on a leg | *structural* flag → **JIT streamflow overlay at plan time answers "today?"** — our existing USGS adapter slots in perfectly |
| Closure | agency closure feeds | fast data → JIT overlay, never a graph node (Rule 3) |

Two disciplines the incident record demands beyond the table: **whitelist, not blacklist** — a connector leg qualifies by *positive* evidence (operator present, formal, access allowed), with sparse-tagged edges landing in a hedged "unverified connector" state rather than silently qualifying (source-or-silence applied to topology); and **never let tier-3 inherit tier-1 dress** — a derived composition always looks like an inference (§4a). Note the tension flag: strict whitelisting in a sparsely-tagged region yields *few or no* proposable loops — that is the honest outcome, surfaced through the existing four empty-states, and it degrades gracefully as TSI tagging accretes.

---

## 6. What is "worth recommending" — the scale

No published quantitative standard exists for loop quality (verified gap — connector-fraction and loop-premium thresholds appear in no source we found; incumbents handle it editorially). That is a chance to define the rubric, not copy one. Proposed dimensions, all computable from structure we hold or will hold:

1. **Effort band fit** ✅ — Naismith's rule (3 mph + 1 hr / 2,000 ft) turns length+gain into hours; band the candidates: short (<2 h) · half-day (2–4 h) · day (4–8 h) · big day (8–12 h). Survey data puts comfortable day hikes at 8–12 mi for average hikers, ≤16 for strong ones ([decideoutside survey](https://decideoutside.com/how-far-can-i-hike-in-a-day/)). Later, the personal capability floor (watch-derived, non-ranking) replaces the generic band — the composed-route case is exactly what the effort-floor-as-cost design in Card 16 anticipated.
2. **Anchor quality** 🔶 — a loop worth doing is *about* something: waterfalls, a summit, a view. Structural proxy today: elevation profile prominence + water-adjacency; properly powered by the Wave-E POI overlay (E3: viewpoints, falls, huts). A loop with no anchor scores near zero no matter how round it is.
3. **Connector fraction** 🔶 — share of distance on way-types that are means-not-ends (fire road, track, road-walk). Soft penalty with full disclosure ("2.4 mi of this loop is fire road"), not a hard kill — the NPS's own flagship circuit carries ~2 mi of it. Straw threshold to tune in the spike: penalize > ~30%, heavily penalize any true road-walk.
4. **Loop premium** 🔶 — the loop must *beat its own out-and-back*: compare the loop against the plain out-and-back to the same best anchor; the extra miles must buy non-repeated scenery (hikers' actual vocabulary: "don't hike the same stretch twice"). Repeated-tread fraction is directly computable on the network.
5. **Shape sanity** — roundness/compactness and low junction-decision count (the jogging-routes paper optimizes exactly these); a 14-turn spaghetti loop is not calm.
6. **Taste, novelty, party** ✅ — the Curator's existing job, unchanged: the structural score proposes, taste ranks, confidence never penalizes rank (Rule 2 — a poorly-tagged but promising loop reads *hedged*, not buried; and the no-Matthew-effect refusal means we don't need a popularity heatmap to justify a recommendation, which we don't have anyway — structure + agency curation substitute, and the Phase-3 commons could one day add k-anonymized "hiked this way" corroboration).

**"Interesting" over "optimal":** the enumerator will find the White Oak–Cedar Run circuit; the score explains *why it's the classic* (two waterfall-canyon legs = anchors; fire-road connector fraction ~25%; day band; near-zero repeated tread). The rubric is falsifiable against tier-1 ground truth: **NPS-published circuits should score at/near the top of their areas — every one our screen kills or buries is a rubric bug** (the golden-loop test, the composition analog of the golden trips in the eval harness).

---

## 7. Sustainability over time

- **Topology is a derivation, not an asset to hand-tend.** Junctions/adjacency/tier-3 routes are deterministic functions of corpus geometry → regenerated on every re-ingest. This *requires* the Phase-A re-runnable-ingest bar and rides the refresh cadence we already planned (daily/weekly regional diffs via the pyosmium transport, Epic 036; OSM retains replication diffs ~3 months, so cadence must never lapse longer — [planet diffs](https://wiki.openstreetmap.org/wiki/Planet.osm/diffs)).
- **Change-resilience via provenance, not vigilance.** Route identity: tier 1/2 keyed on source IDs; tier 3 keyed on the ordered junction sequence (stable iff geometry is stable; a reroute *should* change it). When a member segment changes or vanishes on re-ingest, every dependent `:Route` gets flagged through the same transitive-staleness walk the graph already owns (Pillar 5) — a reroute upstream marks the composed loop stale instead of silently serving last year's line. This is the structural answer to the TSI-documented problem that downstream apps lag corrected data by weeks-to-months.
- **The input data improves on its own trend.** TSI is actively getting land managers to tag the exact fields our screen consumes; our whitelist discipline means coverage growth converts directly into more proposable loops, region by region, with zero relaxation of the screen.
- **ODbL obligation** ❓ — a junction-noded segment database derived from OSM is a *derivative database*; AllTrails publishes its derivation methodology for exactly this reason. Fold into the t6 licensing doc's Stage-9 public-release gate before anything ships publicly.
- **Cost stays flat.** Enumeration/scoring is offline background ranking (no LLM required for the structural score); plan-time cost is the same JIT verification we already run, just per-leg. No always-on router service.

---

## 8. Sequencing, collisions, and the first step

**Hard gate:** Phase A identity stability. Noding re-cuts segments and E1's relation assembly changes `canonical_id` derivation — both collide with the in-flight slug-collision audit + `canonical_id` back-fill (`comaps-borrow-plan.md:212`). Design the post-audit identity scheme **once** for relations + junctions + re-cut segments.

**Natural companions:** E1 (OSM relation fetch — tier 2 falls out of it), E3 (POI overlay — the anchor-quality term), B005 (user-authored routes — same junction substrate, so building topology first makes B005 mostly UI), B001/B002 (the "spatial-query axis" already identified in the backlog cross-read).

**First step — a bounded spike, not an epic** ✅ *(executed 2026-07-11 — results in §9; plan kept below for provenance)*: offline notebook against one region's already-fetched geometry (no schema change, no pipeline change):
1. Node the Shenandoah network (OSMnx/Shapely); report junction count, degree distribution, connected components, and how many existing trails classify as loop/out-and-back/point-to-point (→ sizes the `is_loop` back-fill for free).
2. Run bounded cycle enumeration from the Whiteoak/Cedar Run trailheads.
3. **Falsification target:** the enumerator must rediscover the NPS Cedar Run–Whiteoak Circuit from structure alone, and the straw rubric (§6) must rank it top-3 for its area while the screen kills the obviously-bad variants (road-walk closures via Skyline Drive shoulder, informal cut-throughs).
4. Deliverables: junction-density stats (is 40 m quantization right?), enumeration counts vs. bounds (does the candidate set explode?), a screened+scored candidate list eyeballable against AllTrails' four curated entries, and a go/no-go + epic sketch.

**Open questions** ❓
- ~~Where do *connector* ways live in the corpus?~~ **Answered by the spike (§10):** the flagship circuit's connectors are *named* ways already in the corpus; region-wide, unnamed walkable ways outnumber named ~11:1, so Layer-1 should ingest unnamed in-boundary ways as connector-class network edges (never as recommendable trails).
- `:Route` as first-class feed citizen vs. Detail-screen "extensions & loops" tray — which surface first? (Lean: Detail-screen connectivity first — value without feed-ranking changes.)
- Direction/trailhead anchoring: one `:Route` per (geometry, trailhead, direction) or one with variants? (NPS treats direction as advice — "descend Cedar Run, ascend Whiteoak" — which suggests variants-on-one.)
- Does a tier-3 route ever earn a *name*? (Lean: never fabricate; display as "Loop via X + Y from Z Trailhead.")

---

## 9. Spike results (executed 2026-07-11)

The §8 spike ran in-session against live Overpass data (three mirrors, same set as `ingestion/fetch/osm.py:27-31`). Method: fetch all walkable ways (`highway~path|footway|track|bridleway|steps`, named **and** unnamed) for a Whiteoak/Cedar Run sub-bbox `(38.51,-78.42)–(38.60,-78.32)`; node the network by **shared-vertex re-cut** (OSM ways that join at a junction share a node, so identical coordinates *are* the junctions — no geometric intersection needed, the same re-cut AllTrails documents); collapse degree-2 chains; run bounded edge-simple DFS cycle enumeration; score with the §6 straw rubric (length band + anchor fraction + connector-fraction penalty past 30%; no DEM in the spike, so Naismith's climb term was omitted). Region-wide numbers came from Overpass `out count` queries. Scripts were session-scratch; the method above + the queries are sufficient to reproduce, and a productionized noding pass is Layer-1 epic scope.

**✅ FALSIFICATION TEST PASSED.** From structure alone, the enumerator rediscovered the NPS Cedar Run–Whiteoak Circuit and the straw rubric ranked it **#1** (its direction/micro-variant twin ranked #2): 7.5 mi in-graph (vs. 8.1 NPS-published — NPS measures from the Hawksbill Gap lot including the parking approach; confirms §1's route-must-anchor-at-a-trailhead lesson), **connector fraction 29% vs. the blind 30% straw threshold** — the flagship circuit lands exactly at the boundary the rubric guessed, which is encouraging calibration. Composition found: Cedar Run Trail → White Oak Canyon Trail → Whiteoak Canyon Fire Road → Skyland–Big Meadows Horse Trail.

**Measured findings:**

1. **The feared long pole isn't (inside park units).** All five legs of the circuit are *named* ways that pass today's `is_trail_worthy` filter (verified against `ingestion/trail_filter.py` directly) — **the entire NPS circuit is already in the corpus as five disconnected `:CanonicalTrail` nodes.** Region-wide, however, unnamed walkable ways outnumber named ~**11:1** (2,886 named vs. 33,079 unnamed) — mostly out-of-park fragments (sub-bbox ratio is 76:59). → Layer-1 recommendation: ingest unnamed in-boundary walkable ways as **connector-class network edges** (topology only, never recommendable, never a `:CanonicalTrail`) — a new, cheap corpus concept.
2. **Noding works and the network is small.** 135 ways → 196 noded edges, 200 nodes, **76 junctions (deg ≥ 3)**; degree distribution {1: 94, 2: 30, 3: 67, 4: 8, 5: 1}; 21 components (bbox clipping + genuine isolates — the Card-16 quarantine gate has real work to do). Derived `CONNECTS_TO` came out correct on inspection: Cedar Run ↔ {White Oak Canyon Trail, Skyland–Big Meadows Horse Trail}; White Oak Canyon Trail ↔ Whiteoak Canyon Fire Road.
3. **No combinatorial explosion.** Exhaustive bounded enumeration from *every* junction in the largest component: **38 distinct cycles** total in 1–13 mi (5 under 3 mi, 21 in 3–8, 12 in 8–13), computed in **0.1 s**. Real trail networks are sparse; enumerate-screen-curate is trivially cheap offline. The NP-hardness caution in §3b matters for *optimal* freeform generation, not for this.
4. **TSI screen tags are too sparse to whitelist on (yet).** Named ways region-wide: `operator` 7%, `informal` 0.2%, `sac_scale` 7%, `trail_visibility` 4%, `ford` 0.4% (`surface` 71% is the exception); unnamed ways are worse. → **Revision to §5:** the whitelist's "someone maintains this" evidence must come primarily from **our own conflation layer** — an agency `SourceRecord` in the `SAME_AS` cluster *is* the maintained-trail attestation (stronger than OSM's `operator` tag, and it's the same distinct-origin walk CDP-01 builds) — plus park-boundary containment; the TSI tags serve as *kill switches where present* and grow into the whitelist as TSI adoption spreads. This also resolves the §5 tension flag honestly: inside attested park units, loops propose; in untagged backcountry, they don't.
5. **A live identity finding for the Phase-A audit:** OSM carries both **"White Oak Canyon Trail" and "Whiteoak Canyon Trail"** as different ways of the same physical trail. Today's name-gated consolidation (`pipeline.py:240-308`) necessarily splits it into 2+ `:CanonicalTrail`s. Junction topology plus E1's same-name-or-connected continuation guard is exactly what heals this class of split — one more reason the identity scheme (relations + noding) gets designed once, at Phase E, per the PO sequencing decision.

**Spike verdict: GO** for the Layer-1 topology epic at Phase E (junctions + re-cut segments + `CONNECTS_TO` + `is_loop`/route-shape backfill + "connects to…" on Detail + graph-aware proximity), with composition (`:Route`, screen, rubric) layered after. The write-up above stands with one revision (finding 4's whitelist-evidence source) and one addition (finding 1's connector-class edges).

## 10. Source appendix (external, fetched 2026-07-09)

Route-shape taxonomy: [WTA jargon](https://www.wta.org/go-outside/trail-smarts/a-guide-to-hiking-jargon) · [AllTrails route types](https://support.alltrails.com/hc/en-us/articles/360019246371-Trail-route-types) · [Hiking Project model](https://www.hikingproject.com/help/21/overview-of-site-name-features). Whiteoak/Cedar Run: [NPS circuit](https://www.nps.gov/thingstodo/cedar-run-whiteoak-circuit.htm) · [NPS upper falls](https://www.nps.gov/thingstodo/upper-whiteoak-falls.htm) · [NPS lower falls](https://www.nps.gov/thingstodo/lower-whiteoak-falls.htm). AllTrails model: [OSM-derivative methodology](https://support.alltrails.com/hc/en-us/articles/360019246411-OSM-derivative-database-derivation-methodology) · [verified routes vs segments](https://support.alltrails.com/hc/en-us/articles/4410231246100-Verified-routes-vs-OSM-OpenStreetMap-segments) (support.alltrails.com 403s direct fetch; content via search index + secondary coverage — flagged). SAR record: [National Observer](https://www.nationalobserver.com/2025/06/17/news/alltrails-ai-tool-search-rescue-members) · [InsideHook](https://www.insidehook.com/adventure/experts-concerns-ai-generated-hiking-routes) · [Outdoors Magic (Causey Pike)](https://outdoorsmagic.com/article/news-mountain-rescue-called-out-after-hiker-gets-misled-by-popular-navigation-app/) · [trailhiking.com.au](https://www.trailhiking.com.au/navigation/issues-with-alltrails/). Engines/algorithms: [GraphHopper RoundTripRouting.java](https://github.com/graphhopper/graphhopper/blob/master/core/src/main/java/com/graphhopper/routing/RoundTripRouting.java) · [BRouter PR #759](https://github.com/abrensch/brouter/pull/759) · [Trail Router writeup](https://trailrouter.com/blog/how-trail-router-works/) · [Gemsa et al. SEA 2013](https://link.springer.com/chapter/10.1007/978-3-642-38527-8_25) · [Gavalas et al. survey](https://link.springer.com/article/10.1007/s10732-014-9242-5) · [Lewis & Corcoran 2024](https://link.springer.com/article/10.1007/s42979-024-03223-3) · [OSMnx simplification](https://arxiv.org/html/2407.00258v1). Data models & stewardship: [Tag:route=hiking](https://wiki.openstreetmap.org/wiki/Tag:route%3Dhiking) · [OpenTrails spec](https://github.com/codeforamerica/OpenTrails) · [osgende](https://github.com/waymarkedtrails/osgende) · [USFS EDW trails](https://data.fs.usda.gov/geodata/edw/datasets.php?xmlKeyword=trails) · [TSI wiki](https://wiki.openstreetmap.org/wiki/United_States/Trails_Stewardship_Initiative) · [TSI Utah update](https://openstreetmap.us/news/2024/12/tsi-utah-update/) · [sac_scale](https://wiki.openstreetmap.org/wiki/Key:sac_scale) · [trail_visibility](https://wiki.openstreetmap.org/wiki/Key:trail_visibility) · [OpenTrailMap](https://opentrailmap.us/) · [Planet diffs](https://wiki.openstreetmap.org/wiki/Planet.osm/diffs). Effort bands: [decideoutside survey](https://decideoutside.com/how-far-can-i-hike-in-a-day/) · [Naismith via marathonhandbook](https://marathonhandbook.com/how-many-miles-can-you-hike-in-a-day/).
