// ─────────────────────────────────────────────────────────────────────────
// Adventure Planner — graph/schema.cypher
// Stage 2 thin-v0 graph: constraints, indexes, and a seeded example.
//
// Implements docs/research/stage-2-schema.md with the resolved v0 decisions:
//   1. CanonicalTrail = named loop (no :Route yet)
//   2. Geometry computed at ingest (Python/Shapely/GDAL); Neo4j stores the
//      graph + a representative Point + the line as geom_wkt. No PostGIS in v0.
//   3. Attribute provenance via facts-on-:SourceRecord + computed best-view
//   4. Confidence computed on read (only inputs stored here)
//   5. Ownership via owner_id property (personal overlay; not seeded here)
//   6. Commons in same DB via severed-link :CommonsObservation (reserved)
//
// Community-edition safe: single-property uniqueness only (composite keys are
// modeled as a synthetic `sr_uid = "<source>:<source_id>"`).
//
// Idempotent: MERGE throughout; safe to re-run. Run with:
//   cypher-shell -f graph/schema.cypher
// ─────────────────────────────────────────────────────────────────────────

// ── 0. Schema meta ──────────────────────────────────────────────────────
MERGE (m:Meta {id: "schema"})
  ON CREATE SET m.schema_version = "0.1.0", m.created_at = datetime()
  ON MATCH  SET m.schema_version = "0.1.0", m.updated_at = datetime();

// ── 1. Constraints (uniqueness / integrity) ─────────────────────────────
CREATE CONSTRAINT area_id          IF NOT EXISTS FOR (a:Area)           REQUIRE a.area_id        IS UNIQUE;
CREATE CONSTRAINT canonical_id     IF NOT EXISTS FOR (t:CanonicalTrail) REQUIRE t.canonical_id   IS UNIQUE;
CREATE CONSTRAINT segment_id       IF NOT EXISTS FOR (s:Segment)        REQUIRE s.segment_id     IS UNIQUE;
CREATE CONSTRAINT junction_id      IF NOT EXISTS FOR (j:Junction)       REQUIRE j.junction_id    IS UNIQUE;
CREATE CONSTRAINT trailhead_id     IF NOT EXISTS FOR (h:Trailhead)      REQUIRE h.trailhead_id   IS UNIQUE;
CREATE CONSTRAINT source_record_id IF NOT EXISTS FOR (r:SourceRecord)   REQUIRE r.sr_uid         IS UNIQUE;
CREATE CONSTRAINT source_id        IF NOT EXISTS FOR (src:Source)       REQUIRE src.name         IS UNIQUE;
// Personal overlay (reserved; enforced now so the boundary is right early — T2)
CREATE CONSTRAINT person_id        IF NOT EXISTS FOR (p:Person)         REQUIRE p.member_id      IS UNIQUE;
CREATE CONSTRAINT household_id     IF NOT EXISTS FOR (hh:Household)     REQUIRE hh.household_id  IS UNIQUE;

// ── 2. Indexes ───────────────────────────────────────────────────────────
// Spatial "near my origin" lookups (Decision Log §5: origin as runtime param)
CREATE POINT INDEX trailhead_point IF NOT EXISTS FOR (h:Trailhead) ON (h.point);
CREATE POINT INDEX junction_point  IF NOT EXISTS FOR (j:Junction)  ON (j.point);
CREATE POINT INDEX area_point      IF NOT EXISTS FOR (a:Area)      ON (a.point);
// Spatial lookup on trail centroids (fallback when no Trailhead nodes exist)
CREATE POINT INDEX canonical_trail_point IF NOT EXISTS FOR (t:CanonicalTrail) ON (t.point);
// Name lookups
CREATE TEXT INDEX trail_name       IF NOT EXISTS FOR (t:CanonicalTrail) ON (t.name);
CREATE TEXT INDEX area_name        IF NOT EXISTS FOR (a:Area)           ON (a.name);
// Re-sync key for idempotent monthly refresh (source, source_id) + version
CREATE INDEX sr_source_version     IF NOT EXISTS FOR (r:SourceRecord) ON (r.source, r.ingest_version);
// Hybrid GraphRAG vector index (reserved — embeddings populated later, §6).
// Requires Neo4j 5.x. Comment out if your dev version predates vector indexes.
CREATE VECTOR INDEX trail_embedding IF NOT EXISTS
  FOR (t:CanonicalTrail) ON (t.embedding)
  OPTIONS { indexConfig: { `vector.dimensions`: 1536, `vector.similarity_function`: 'cosine' } };

// ── 3. Source registry (authority-tier lookup; feeds confidence on read) ──
// authority is per (source, data_kind); stored as a JSON string. See Stage 1 §4.
MERGE (osm:Source {name: "OSM"})
  SET osm.license = "ODbL-1.0", osm.separable = true,
      osm.authority = '{"geometry":"med-high","attributes":"low-med","rules":"low"}';
MERGE (usfs:Source {name: "USFS"})
  SET usfs.license = "public-domain",
      usfs.authority = '{"existence":"tier1","allowed_use":"tier1","geometry":"mid"}';
MERGE (nps:Source {name: "NPS"})
  SET nps.license = "public-domain",
      nps.authority = '{"existence":"tier1","geometry":"tier1","park_content":"tier1"}';
MERGE (ntd:Source {name: "USGS_NTD"})
  SET ntd.license = "public-domain",
      ntd.authority = '{"existence":"tier2","geometry":"tier3"}';

// ── 4. Seeded example — Old Rag Loop, Shenandoah NP ──────────────────────
// A realistic minimal slice: one Area, one CanonicalTrail with OSM + NPS
// SourceRecords joined by SAME_AS, two Segments, a Junction, and a Trailhead.
// Geometry: a representative Point for spatial lookup + the line as geom_wkt
// on the Segment (computed at ingest; default #2). WKT here is truncated/
// illustrative — real lines carry full vertex lists. Values illustrative.

MERGE (shen:Area {area_id: "nps:shen"})
  SET shen.name = "Shenandoah National Park",
      shen.manager = "National Park Service",
      shen.point = point({latitude: 38.49, longitude: -78.46}),
      shen.permit_required = true,                       // backcountry permit (RIDB)
      shen.ridb_recarea_id = "2933",
      shen.ingest_version = "2026-06";

MERGE (oldrag:CanonicalTrail {canonical_id: "ct:old-rag-loop"})
  SET oldrag.name = "Old Rag Loop",
      oldrag.region = "mid-atlantic/va",
      oldrag.point = point({latitude: 38.5519, longitude: -78.2861}),
      oldrag.is_loop = true,
      // computed best-view cache of facts (recomputed on ingest from SourceRecords):
      oldrag.length_mi = 9.1, oldrag.length_source = "NPS",
      oldrag.gain_ft = 2415, oldrag.gain_source = "USGS_3DEP",
      // live-overlay resolution keys (NOT live values — §8):
      oldrag.nws_grid_ref = "LWX/96,70",
      oldrag.ingest_version = "2026-06";

MERGE (shen)-[:CONTAINS]->(oldrag);

// Provenance: source records + SAME_AS (the entity-resolution hub, §3)
MERGE (sr_osm:SourceRecord {sr_uid: "OSM:relation/123456"})
  SET sr_osm.source = "OSM", sr_osm.source_id = "relation/123456",
      sr_osm.raw_name = "Old Rag Mountain",
      sr_osm.raw_geom_wkt = "LINESTRING(-78.2861 38.5707, ...)",   // truncated; full line set at ingest
      sr_osm.fetched_at = datetime(), sr_osm.ingest_version = "2026-06";
MERGE (sr_nps:SourceRecord {sr_uid: "NPS:OBJECTID=4021"})
  SET sr_nps.source = "NPS", sr_nps.source_id = "OBJECTID=4021",
      sr_nps.raw_name = "Old Rag", sr_nps.trl_use = "hiker/pedestrian",
      sr_nps.raw_geom_wkt = "LINESTRING(-78.2861 38.5707, ...)",   // truncated
      sr_nps.fetched_at = datetime(), sr_nps.ingest_version = "2026-06";

MERGE (oldrag)<-[so:SAME_AS {source: "OSM"}]-(sr_osm)
  SET so.source_id = "relation/123456", so.match_method = "name+geom",
      so.matched_on = ["name"], so.match_score = 0.88,
      so.reviewed_by = "josh", so.reviewed_at = date(), so.ingest_version = "2026-06";
MERGE (oldrag)<-[sn:SAME_AS {source: "NPS"}]-(sr_nps)
  SET sn.source_id = "OBJECTID=4021", sn.match_method = "name+ref+geom",
      sn.matched_on = ["TRLNAME"], sn.match_score = 0.95,
      sn.reviewed_by = "josh", sn.reviewed_at = date(), sn.ingest_version = "2026-06";

// Segments (conflation unit) + a Junction + the Trailhead
MERGE (seg1:Segment {segment_id: "seg:old-rag-ridge"})
  SET seg1.geom_wkt = "LINESTRING(-78.2898 38.5546, ...)", seg1.length_mi = 2.9,
      seg1.source_seg_ids = ["OSM:way/111","NPS:OBJECTID=4021a"],
      seg1.point = point({latitude: 38.5546, longitude: -78.2898});
MERGE (seg2:Segment {segment_id: "seg:saddle-fire-road"})
  SET seg2.geom_wkt = "LINESTRING(-78.2820 38.5490, ...)", seg2.length_mi = 6.2,
      seg2.source_seg_ids = ["OSM:way/112"],
      seg2.point = point({latitude: 38.5490, longitude: -78.2820});
MERGE (oldrag)-[:HAS_SEGMENT]->(seg1);
MERGE (oldrag)-[:HAS_SEGMENT]->(seg2);

MERGE (jx:Junction {junction_id: "jx:byrds-nest-saddle"})
  SET jx.point = point({latitude: 38.5512, longitude: -78.2845});
MERGE (seg1)-[:ENDS_AT]->(jx);
MERGE (seg2)-[:STARTS_AT]->(jx);

MERGE (th:Trailhead {trailhead_id: "th:old-rag-lot"})
  SET th.name = "Old Rag Parking / Fee Station",
      th.point = point({latitude: 38.5707, longitude: -78.2861}),
      th.ridb_facility_id = "234567";
MERGE (th)-[:ACCESSES]->(oldrag);
MERGE (th)-[:LOCATED_IN]->(shen);

// ── 5. Reference: the scopedQuery seam (T2) ──────────────────────────────
// Personal-overlay reads MUST go through a data-access wrapper that injects
// the viewer's permission set. World/commons nodes are unowned → public.
// Illustrative shape (the only sanctioned pattern for owned data):
//
//   MATCH (p:Person)-[:DID]->(e:Episode)-[:ON]->(t:CanonicalTrail)
//   WHERE e.owner_id = $viewer_id OR e.owner_id IN $granted_ids
//   RETURN ...
//
// No raw Cypher touching owned nodes may bypass this wrapper. A property-based
// test fuzzes $viewer_id/$granted_ids to assert no ungranted node ever returns.

RETURN "schema v0.1.0 applied + Old Rag seed loaded" AS status;
