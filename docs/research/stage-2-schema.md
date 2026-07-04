# Stage 2 — Graph Schema & Provenance/Confidence Model (draft proposal)

*Workplan Stage 2. Draft v0.1 — June 19, 2026. Designed against Stage 1 findings (`stage-1-data-sources.md`).*

> **STATUS: IMPLEMENTED** — schema shipped (Neo4j v0.2.0): commons fork by Epic 010, the `scopedQuery`/`ScopedSession` access seam by Epic 011, live-Neo4j CI guardrail by Epic 015. *(Design below kept as spec provenance; "DRAFT" framing is historical.)* This is the first concrete schema proposal. Decisions marked 🅓 are open for Josh's call (§10). The goal of Stage 2 is to settle the **core shape** — the part expensive to retrofit (Decision Log §23) — while keeping the thin-v0 discipline (§6: "don't let it become a schema project").

> **What this produces (per workplan):** canonical world nodes (trail/segment/trailhead/area) · the provenance model (source attribution as edges, `SAME_AS` resolution) · attachment points for the private overlay and the commons · the confidence model's storage vs. computation · a schema-versioning approach. Honors **T2** (access-control-at-query-layer) from here on.

---

## 1. Design principles (inherited, non-negotiable)

1. **Graph holds slow/structural data only** (Rule #3). Weather/streamflow/AQI/permit-availability are **never nodes** — they're a JIT overlay keyed by ids stored on nodes.
2. **Provenance is structure, not a property.** "Which source said what" must be a *traversal*, not a buried JSON blob (§6).
3. **Confidence is one property with three axes** (freshness · authority · corroboration), computed on read, never penalizing rank (Rule #2, §7).
4. **Three layers on shared nodes:** World (shared) · Personal overlay (private-by-default) · Commons (derived-on-shared) (§11–12). Each hangs off the same canonical world nodes.
5. **Access control at the query layer** (Rule #4, T2). Every traversal is parameterized by the viewer's permission set — designed in now, even before grants exist.
6. **ODbL separability** (Stage 1 §5.1): the OSM-derived geometry layer must stay *separable* so a future public commons can be a Collective Database. → provenance-per-source makes this free.

---

## 2. The world layer — node taxonomy

The central modeling question: **what *is* a "destination" vs. a trail vs. a segment?** Stage 1's segmentation finding (the same trail is a named route in one source, many segments in another, with junctions shared) drives a **three-granularity** model:

| Node | What it is | Example | Source of truth |
|---|---|---|---|
| **`:Area`** | A bounded place that *contains* trails — a park, forest, or recreation area. The "destination" you drive *to*. | Shenandoah NP; GWJ NF; a state park | PAD-US / NPS / USFS / agency |
| **`:CanonicalTrail`** | A **named route** — the thing we present and rank. The unit of recommendation. | "Old Rag Loop"; "Riprap–Wildcat Loop" | conflated (OSM spine) |
| **`:Segment`** | A single continuous geometry piece between junctions; the conflation unit. Many segments compose a trail. | a 0.7 mi stretch of tread | conflated geometry |
| **`:Junction`** | A shared network node where segments meet. | a 3-way trail intersection | derived from geometry |
| **`:Trailhead`** | An access point (parking/start) onto trails. The thing drive-time routes *to*. | Old Rag parking lot | OSM `highway=trailhead` / agency |
| **`:SourceRecord`** | One source's raw assertion about a trail/segment — the provenance anchor (see §3). | "USFS row TRAIL_CN=…"; "OSM way 12345" | each source, verbatim |

**Relationships (world layer):**
```
(:Area)-[:CONTAINS]->(:CanonicalTrail)
(:CanonicalTrail)-[:HAS_SEGMENT]->(:Segment)
(:Segment)-[:STARTS_AT|ENDS_AT]->(:Junction)
(:Trailhead)-[:ACCESSES]->(:CanonicalTrail)
(:Trailhead)-[:LOCATED_IN]->(:Area)
(:CanonicalTrail)-[:CONNECTS_TO]->(:CanonicalTrail)   // shared junctions → alternatives/extensions
```

**Why "destination = Area, recommendation = CanonicalTrail."** You decide *where to go* at the Area level (drive-time, land manager, permits-required) but you *do* a CanonicalTrail. The feed card is a CanonicalTrail; the Area gives it context (rules, permits, closures). Segments exist so we never have to re-solve cross-source segmentation per query, and so the commons (effort topology, "where people slow") can attach at sub-trail resolution later.

🅓 **Open: loops & multi-trail routes.** A "hike" is often a *composed loop* across several CanonicalTrails. Option A: CanonicalTrail = the composed named loop (matches how people talk: "Old Rag Loop"). Option B: add a `:Route` node above CanonicalTrail for user/agency-defined itineraries. **Recommend A for v0** (named loops are how trails are signed and searched), add `:Route` only when personalization/party planning needs custom itineraries (Stage 5+).

**Geometry storage (Decision 2 — resolved).** Geometry **compute** (conflation buffers, Hausdorff/Fréchet, DEM sampling) happens at **ingest time in Python** (Shapely/GeoPandas/GDAL — what OSM Merge itself uses). Neo4j stores the **graph + a representative `Point`** per Segment/Junction/Trailhead (for spatial "near my origin" via a point index) **+ the canonical line as a `geom_wkt`/GeoJSON property** on the Segment (for rendering). **No standing PostGIS in v0** — stand it up only if a query genuinely needs server-side spatial that ingest-precompute or Valhalla can't cover. This keeps the stack to one database (Neo4j) for the thin v0.

---

## 3. The provenance model — `SourceRecord` + `SAME_AS`

This is the differentiator (§6). Every canonical node is an **entity-resolution hub**: source records join to it by `SAME_AS`, preserving "which source said what" as queryable structure.

```
(:CanonicalTrail {canonical_id, name, region})
   <-[:SAME_AS {                       // one edge per source record
        source:        "USFS",         // OSM | USFS | NPS | USGS_NTD | VA_OPEN | FAIRFAX
        source_id:     "TRAIL_CN=0210...",   // the source's OWN stable PK (for re-sync)
        match_method:  "name+ref+geom",
        matched_on:    ["TRAIL_NAME","ref:usfs"],
        match_score:   0.94,
        reviewed_by:   "josh",         // human-in-the-loop (Stage 1 §7)
        reviewed_at:   "2026-06-19",
        ingest_version:"2026-06" }]-
   (:SourceRecord {source:"USFS", source_id, raw_name, raw_attrs, geom_ref, fetched_at})
```

**Attribute-level provenance.** A fact like *length* or *allowed_use* can differ per source. Two options:

- **3a (recommended for v0): facts live on `:SourceRecord`**, and the CanonicalTrail exposes a **computed "best view"** at read time (pick the highest-authority non-null per attribute, per §4 tiering). "Why do you believe length=4.2mi?" → traverse to the SourceRecord that won. Cheap, ODbL-clean (OSM facts stay on the OSM SourceRecord — separable).
- **3b (later, if needed): reified `:Assertion` nodes** `(:SourceRecord)-[:ASSERTS]->(:Assertion {key, value, confidence})-[:ABOUT]->(:CanonicalTrail)` for full fact-level granularity + conflicting-claim display. More expressive, heavier. **Defer** unless the UI needs per-fact source badges everywhere.

**Conflict handling (Stage 1 rule): never auto-merge conflicting access/usage.** Keep both source records; the read-time view surfaces *"USFS: bikes discouraged · OSM: no restriction"* with each source's authority. This is source-or-silence applied to the world layer.

**ODbL separability falls out for free:** OSM-originated facts only ever live on `:SourceRecord {source:"OSM"}`. A future public commons can export everything *except* the OSM-derived layer (Collective Database), or re-attribute it — without untangling a merged blob.

---

## 4. The confidence model — stored inputs, computed score

Confidence is **computed on read**, from **stored inputs** — because two of its three axes are time- or context-dependent (Decision Log §7).

| Axis | Stored where | Computed how |
|---|---|---|
| **Freshness** | `fetched_at`/`updated_at` timestamp on the SourceRecord (and on the live overlay) | `age` relative to that data kind's rate-of-change (geometry decays over years; a forecast over minutes) → at read time |
| **Authority** | `source` label + a small **`authority_tier` lookup keyed by (source, data_kind)** (the §4 table from Stage 1, stored as config/a `:Source` node) | direct lookup |
| **Corroboration** | count of `SAME_AS` source records agreeing; for crowd facts, the contributor count `n` on the commons stat | `count()` traversal / stored `n` |

**Output (computed, not stored):** a single `confidence` ∈ [0,1] (or a small ordinal: high/medium/low/floor) that drives **three things and one non-thing** (§7):
- **Floor:** below threshold → don't state the fact (source-or-silence).
- **Presentation:** sets phrasing (plain vs. hedged-with-reason).
- **Safety flag:** low-confidence *conditions* → "verify before you go."
- **NON-thing:** never penalizes ranking.

**Why computed-on-read, not stored:** a stored score goes stale the moment the clock moves (freshness) or the viewer changes (a crowd fact's corroboration may be below the k-floor for one viewer's context). Store the *inputs*; compute the score in the read layer. 🅓 *Optional:* cache a computed score with a short TTL if read-cost becomes a problem (measure first).

**One gate, two jobs:** the commons **k-anonymity threshold = the confidence floor** (§7) — a crowd fact below `k` contributors is both privacy-unsafe and too thin to trust. Store `k` as one config value.

---

## 5. Personal overlay — private-by-default attachment

Hangs off the *same* world nodes; never duplicated (§11). Private by default; access enforced at query layer (§7 below).

```
(:Household)-[:HAS_MEMBER]->(:Person {member_id, ...})       // each = own login, overlay, grants
(:Person)-[:HAS_DEPENDENT]->(:Dependent {name:"Ruby", type:"dog"})   // not an account
(:Person)-[:DID]->(:Episode)-[:ON]->(:CanonicalTrail)         // a completed trip
(:Belief)-[:DERIVED_FROM]->(:Episode)                          // "why do you believe this?"
(:Belief)-[:ABOUT]->(:Person|:Dependent|:CanonicalTrail)
(:Episode)-[:HAS_OUTCOME]->(:Outcome {rating, ...})
```

**Every `:Belief` carries provenance + confidence + timestamp + type** (Rule #7): `{type: stated|inferred, axis: constraint|taste|capability|preference, confidence, source_episode_ids, created_at, decays}`. Capability ≠ preference is a **property on the belief**, not a guess at query time. Beliefs `DERIVED_FROM` episodes = the legible, user-editable store that doubles as the correction surface (§9).

**Detail deferred to Stage 5** (belief entry schema, episode→semantic promotion, decay params). Stage 2 only fixes the **attachment points** (`:Person`, `:Episode`, `:Belief` labels + their edges to world nodes) so the world schema doesn't need retrofitting later.

---

## 6. Commons layer — derived-on-shared

Slow *derived* statistics on shared nodes (§12), gated by `k`. Lives in the graph, on `:Segment`/`:CanonicalTrail`.

```
(:CanonicalTrail|:Segment)-[:HAS_COMMONS_STAT]->(:CommonsStat {
    kind:        "pace_on_grade" | "effort_topology" | "crowding_by_time" | "heat_exposure",
    capability_band: "moderate",     // computed contributor-side, never raw
    value, n,                         // n = contributor count; gate: n >= k
    computed_at })
```

**The forked write (T3, build now even in Phase 0):** a completed `:Episode` writes (a) to the private overlay AND (b) a **de-identified, endpoint-trimmed `:CommonsObservation`** with the person→observation link **severed at write time**. Accretes from day one, dormant until `n >= k`. The de-identification (sever link, trim track endpoints, capability-band) is a *pipeline* concern (Stage 9) — Stage 2 just reserves the `:CommonsObservation` label and guarantees **no edge ever links it back to a `:Person`** (a security/privacy test target, §17).

🅓 **Open:** whether `:CommonsObservation` lives in the same Neo4j DB (simplest; revocation = "nothing was copied" only holds for *person* nodes, not the severed observation) or a separate store. Decision Log §11 says one shared graph for trusted-household; revisit for strangers. **Recommend same DB, severed-link, for v0.**

---

## 7. Access control at the query layer (T2 — honored from now)

**Principle:** never emit a Cypher query that *could* return ungranted nodes (Rule #4). Enforced in the **data-access layer**, not the agent, since Neo4j fine-grained security is enterprise-only (§11).

**v0 mechanism (before grants exist):**
- Every personal-overlay node carries an **`owner_id`** property.
- The data-access layer takes a **viewer context** `{viewer_id, granted_ids:[]}` and parameterizes *every* traversal: `WHERE n.owner_id = $viewer_id OR n.owner_id IN $granted_ids`.
- World/commons nodes are unowned → always readable (the anonymous product, §13).
- A single **`scopedQuery(cypher, viewer)`** wrapper is the *only* path to the graph; no raw Cypher escapes it. This is the seam the Stage-8 grant system slots into — the boundary can move because it was built right early (§22 cross-cutting).

**Test (§17):** does the access layer *ever* emit an ungranted node? A property-based test fuzzes viewer contexts against a seeded graph. Written when the wrapper is.

🅓 **Open:** `owner_id` property vs. a `(:Person)-[:OWNS]->()` edge. Property is simpler/faster to filter; edge is more graph-native and supports multi-owner. **Recommend property for v0**, edge if multi-owner (shared household objects) appears.

---

## 8. Live overlay — explicitly NOT in the graph

Confirming Rule #3 in schema terms. The graph stores the **resolution keys**; the Verifier fetches live and overlays at decision time:

```
(:CanonicalTrail|:Trailhead) {
    nws_grid_ref,            // resolved /points → grid (cache the resolution, not the forecast)
    usgs_site_id, usgs_site_dist_m,   // nearest gauge + distance (disclose representativeness)
    airnow_nearest_dist_m,
    ridb_facility_id, ridb_permit_id  // permit availability fetched live
}
```
Nothing time-varying is persisted as a node. The "freshness" disclosure (gauge is 6 mi away) uses the stored `*_dist_m`.

---

## 9. Schema versioning & integrity

- **`ingest_version`** (e.g. `"2026-06"`) on every `:SourceRecord` and `:SAME_AS` → monthly refresh is idempotent and reconcilable (re-sync by `(source, source_id)`); stale records pruned by version.
- **`:Meta {schema_version}`** singleton node; migrations are versioned Cypher scripts in `graph/migrations/` (monorepo), forward-only, each bumping `schema_version`. 🅓 *(tool choice: hand-rolled migration runner vs. a library — defer to Stage 0/3.)*
- **Constraints & indexes (v0):** uniqueness on `canonical_id`, `(source, source_id)`; spatial point index on `:Trailhead(point)`, `:Junction(point)`.
- **Hygiene on ingest (§17):** validate + drop malformed; flag incomplete (RIDB blank coords); provenance integrity = every world fact traces to a `:SourceRecord`.

---

## 10. Design decisions — RESOLVED ✅ *(June 19, 2026)*

| # | Decision | Resolution |
|---|---|---|
| 1 | Composed loops | ✅ **CanonicalTrail = named loop** now; add `:Route` only when custom itineraries are needed (Stage 5+). |
| 2 | Geometry | ✅ **Ingest-time Python geometry (Shapely/GDAL); WKT + representative Point in Neo4j.** No standing PostGIS in v0. |
| 3 | Attribute provenance | ✅ **3a — facts on `:SourceRecord` + computed best-view.** Promote individual high-conflict attrs (allowed-use/dog/closures) to richer modeling later only if the UI demands it. |
| 4 | Confidence | ✅ **Computed on read** from stored inputs; no cache until reads are measured slow. |
| 5 | Ownership | ✅ **`owner_id` property** on personal-overlay nodes; revisit `:OWNS` edge if multi-owner appears. |
| 6 | Commons store | ✅ **Same Neo4j DB**, severed person→observation link; revisit a separate store for the stranger case (§11). |

*Net effect: a single-database (Neo4j) thin v0; geometry handled in the ingestion pipeline, not a second spatial store.*

---

## 11. What Stage 2 deliberately defers
- Belief-entry schema, episode→semantic promotion, decay (→ Stage 5).
- Grant tuple semantics + the full permission model (→ Stage 8); Stage 2 only builds the `scopedQuery` seam.
- Commons aggregation math, k-value, capability-band computation (→ Stage 9); Stage 2 only reserves labels + the severed-link guarantee.
- Conflation match-score *thresholds* for our data (→ Stage 3, tuned empirically).

## 12. Next
The concrete artifact now exists: **`graph/schema.cypher`** — constraints + indexes + a Source registry + a seeded example (Shenandoah NP → Old Rag Loop with OSM+NPS SourceRecords + `SAME_AS`, two Segments, a Junction, a Trailhead). It encodes the six recommended v0 defaults and is small enough to be the thin-v0 graph (§6), real enough to write the first `scopedQuery` test against. **Not yet run against a live Neo4j** (no DB in this planning environment) — first execution + the access-layer test is the opening step of Stage 3. Any of the §10 🅓 defaults can be revised before then.
