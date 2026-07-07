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
  ON CREATE SET m.schema_version = "0.1.0", m.schema_format = 1, m.created_at = datetime()
  ON MATCH  SET m.schema_version = "0.2.0", m.schema_format = 1, m.updated_at = datetime();

// ── 1. Constraints (uniqueness / integrity) ─────────────────────────────
CREATE CONSTRAINT area_id          IF NOT EXISTS FOR (a:Area)           REQUIRE a.area_id        IS UNIQUE;
CREATE CONSTRAINT canonical_id     IF NOT EXISTS FOR (t:CanonicalTrail) REQUIRE t.canonical_id   IS UNIQUE;
CREATE CONSTRAINT segment_id       IF NOT EXISTS FOR (s:Segment)        REQUIRE s.segment_id     IS UNIQUE;
CREATE CONSTRAINT trailhead_id     IF NOT EXISTS FOR (h:Trailhead)      REQUIRE h.trailhead_id   IS UNIQUE;
CREATE CONSTRAINT source_record_id IF NOT EXISTS FOR (r:SourceRecord)   REQUIRE r.sr_uid         IS UNIQUE;
CREATE CONSTRAINT source_id        IF NOT EXISTS FOR (src:Source)       REQUIRE src.name         IS UNIQUE;
// Personal overlay (reserved; enforced now so the boundary is right early — T2)
CREATE CONSTRAINT person_id        IF NOT EXISTS FOR (p:Person)         REQUIRE p.member_id      IS UNIQUE;
CREATE CONSTRAINT household_id     IF NOT EXISTS FOR (hh:Household)     REQUIRE hh.household_id  IS UNIQUE;
// Epic 002: Outcome uniqueness — one Outcome per (episode_id, owner_id)
CREATE CONSTRAINT outcome_id       IF NOT EXISTS FOR (o:Outcome)        REQUIRE o.outcome_id     IS UNIQUE;

// ── 2. Indexes ───────────────────────────────────────────────────────────
// Spatial "near my origin" lookups (Decision Log §5: origin as runtime param)
CREATE POINT INDEX trailhead_point IF NOT EXISTS FOR (h:Trailhead) ON (h.point);
CREATE POINT INDEX area_point      IF NOT EXISTS FOR (a:Area)      ON (a.point);
// Spatial lookup on trail centroids (fallback when no Trailhead nodes exist)
CREATE POINT INDEX canonical_trail_point IF NOT EXISTS FOR (t:CanonicalTrail) ON (t.point);
// Name lookups
CREATE TEXT INDEX trail_name       IF NOT EXISTS FOR (t:CanonicalTrail) ON (t.name);
CREATE TEXT INDEX area_name        IF NOT EXISTS FOR (a:Area)           ON (a.name);
// Re-sync key for idempotent monthly refresh (source, source_id) + version
CREATE INDEX sr_source_version     IF NOT EXISTS FOR (r:SourceRecord) ON (r.source, r.ingest_version);

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
// SourceRecords joined by SAME_AS, two Segments, and a Trailhead.
// Geometry: a representative Point for spatial lookup + the line as geom_wkt
// on each Segment (computed at ingest; default #2). The two Segments share an
// endpoint vertex so they assemble into one route; `route_geom_wkt` on the trail
// is that precomputed assembled route (Epic 016 S1), served as GeoJSON by
// GET /trail/{id}. The elevation profile (Epic 017: route_geom_wkt is sampled into
// profile_distances_m / profile_elevations_m + total_gain_m / total_loss_m /
// max_grade_pct / elev_source / elev_resolution_m / elev_version) is populated by
// the 3DEP enrichment source, NOT seeded — an un-enriched trail correctly serves
// `elevationProfile: null` (source-or-silence). Coords short but valid WKT;
// values illustrative.

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
      // assembled route precomputed at ingest (Epic 016 S1) from the Segments below:
      oldrag.route_geom_wkt = "LINESTRING(-78.2898 38.5546, -78.2870 38.5530, -78.2845 38.5512, -78.2820 38.5490, -78.2800 38.5470)",
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

// Segments (conflation unit) + the Trailhead
MERGE (seg1:Segment {segment_id: "seg:old-rag-ridge"})
  SET seg1.geom_wkt = "LINESTRING(-78.2898 38.5546, -78.2870 38.5530, -78.2845 38.5512)", seg1.length_mi = 2.9,
      seg1.source_seg_ids = ["OSM:way/111","NPS:OBJECTID=4021a"],
      seg1.point = point({latitude: 38.5546, longitude: -78.2898});
MERGE (seg2:Segment {segment_id: "seg:saddle-fire-road"})
  SET seg2.geom_wkt = "LINESTRING(-78.2845 38.5512, -78.2820 38.5490, -78.2800 38.5470)", seg2.length_mi = 6.2,
      seg2.source_seg_ids = ["OSM:way/112"],
      seg2.point = point({latitude: 38.5490, longitude: -78.2820});
MERGE (oldrag)-[:HAS_SEGMENT]->(seg1);
MERGE (oldrag)-[:HAS_SEGMENT]->(seg2);

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

// ── 6. Stage 5 constraints — personal-overlay node types ─────────────────
// Every owned Stage-5 node carries owner_id; access is enforced by the
// scopedQuery(viewer) wrapper (Rule #4). Uniqueness enforced here so no
// duplicate node can be created on idempotent re-runs.
// Community Edition safe: single-property uniqueness constraints only.
CREATE CONSTRAINT episode_id      IF NOT EXISTS FOR (e:Episode)         REQUIRE e.episode_id   IS UNIQUE;
CREATE CONSTRAINT belief_id       IF NOT EXISTS FOR (b:Belief)          REQUIRE b.belief_id    IS UNIQUE;
CREATE CONSTRAINT phys_profile_id IF NOT EXISTS FOR (pp:PhysicalProfile) REQUIRE pp.profile_id IS UNIQUE;
// pp_profile_id name avoids clash with phys_profile_id above
CREATE CONSTRAINT pp_profile_id   IF NOT EXISTS FOR (pa:PartyProfile)   REQUIRE pa.profile_id  IS UNIQUE;
// Dependent: household sub-node (Ruby the dog, etc.). Not an account; no login.
CREATE CONSTRAINT dependent_id    IF NOT EXISTS FOR (d:Dependent)       REQUIRE d.dependent_id IS UNIQUE;
// Commons (Epic 010): the reserved :CommonsObservation realized. Born severed —
// no owner_id, no edge to any :Person/:Episode (de-identified at write, Stage 9
// §2.1). Community-Edition-safe single-property uniqueness on the random UUID.
CREATE CONSTRAINT commons_observation_id IF NOT EXISTS FOR (co:CommonsObservation) REQUIRE co.observation_id IS UNIQUE;

// ── 7. Stage 5 indexes ───────────────────────────────────────────────────
// all-my-episodes: primary access pattern for Episode
CREATE INDEX episode_owner         IF NOT EXISTS FOR (e:Episode)          ON (e.owner_id);
// belief retrieval by owner+subject (composite range; CE 5.x supports this)
CREATE INDEX belief_owner_subject  IF NOT EXISTS FOR (b:Belief)           ON (b.owner_id, b.subject_id);
// belief-type lookups (fetch all pace_on_grade beliefs for a person, etc.)
CREATE INDEX belief_key            IF NOT EXISTS FOR (b:Belief)           ON (b.key);
// all-my-profiles query for capability summary
CREATE INDEX phys_profile_owner    IF NOT EXISTS FOR (pp:PhysicalProfile) ON (pp.owner_id);

// ── 8. Stage 5 seeded example — Josh + Ruby on Old Rag ───────────────────
// Illustrative graph shape only. Values are marked; nothing here is real
// watch or biometric data. MERGE throughout — idempotent, safe to re-run.
//
// Key edges demonstrated:
//   (:Person)-[:DID]->(:Episode)-[:ON]->(:CanonicalTrail)
//   (:Episode)-[:WITH]->(:Dependent)
//   (:Episode)-[:HAS_OUTCOME]->(:Outcome)
//   (:Belief)-[:DERIVED_FROM]->(:Episode)        // Rule #7 provenance
//   (:Belief)-[:ABOUT]->(:Person)
//   (:Person)-[:HAS_PROFILE]->(:PhysicalProfile)
//   (:Person)-[:HAS_PARTY_PROFILE]->(:PartyProfile)
//
// Access invariant (Rule #4): every owned node below carries owner_id.
// No read of these nodes may bypass scopedQuery(viewer).

// Household + Person + Dependent
MERGE (hh:Household {household_id: "hh:crow"})
  SET hh.name = "Crow household";

// commons_opt_in (Epic 010 S6): per-member commons-contribution consent, default
// OFF. It gates *exposure* (Stage 9 aggregation), NOT the write — the severed,
// de-identified observation accretes regardless (Stage 9 §8.2 / S9-17). A Person
// with the property absent is treated as not-opted-in by any future reader.
MERGE (josh:Person {member_id: "mem:josh"})
  SET josh.display_name = "Josh",
      josh.household_id = "hh:crow",
      josh.commons_opt_in = false;

MERGE (ruby:Dependent {dependent_id: "dep:ruby"})
  SET ruby.display_name = "Ruby",
      ruby.kind         = "dog",
      ruby.household_id = "hh:crow";

MATCH (p:Person {member_id: "mem:josh"})
MATCH (h:Household {household_id: "hh:crow"})
MERGE (p)-[:MEMBER_OF]->(h);

MATCH (p:Person {member_id: "mem:josh"})
MATCH (d:Dependent {dependent_id: "dep:ruby"})
MERGE (p)-[:HAS_DEPENDENT]->(d);

// Episode: Josh + Ruby on Old Rag Loop, 2025-09-14 (all values illustrative)
MERGE (ep:Episode {episode_id: "ep:old-rag-2025-09"})
  ON CREATE SET
    ep.owner_id          = "mem:josh",
    ep.trail_id          = "ct:old-rag-loop",
    ep.date              = date("2025-09-14"),
    ep.source            = "watch_fit",
    ep.duration_min      = 285,
    ep.moving_min        = 245,
    ep.distance_m        = 14650,
    ep.ascent_m          = 735,
    ep.descent_m         = 735,
    ep.pace_on_grade     = 15.8,
    ep.party_members     = ["mem:josh", "dep:ruby"],
    ep.watch_activity_id = "garmin:act:ILLUSTRATIVE-001",
    ep.fit_parsed        = true,
    ep.created_at        = datetime("2025-09-14T18:30:00"),
    ep.updated_at        = datetime("2025-09-14T18:30:00");

MATCH (p:Person {member_id: "mem:josh"})
MATCH (e:Episode {episode_id: "ep:old-rag-2025-09"})
MERGE (p)-[:DID]->(e);

MATCH (e:Episode {episode_id: "ep:old-rag-2025-09"})
MATCH (ct:CanonicalTrail {canonical_id: "ct:old-rag-loop"})
MERGE (e)-[:ON]->(ct);

MATCH (e:Episode {episode_id: "ep:old-rag-2025-09"})
MATCH (d:Dependent {dependent_id: "dep:ruby"})
MERGE (e)-[:WITH]->(d);

// Outcome: post-hike reflect-back card
MERGE (oc:Outcome {outcome_id: "oc:old-rag-2025-09"})
  ON CREATE SET
    oc.owner_id       = "mem:josh",
    oc.episode_id     = "ep:old-rag-2025-09",
    oc.overall        = 3,
    oc.delta_question = "What was the best part?",
    oc.delta_answer   = "Summit scramble",
    oc.surfaces_at    = datetime("2025-09-15T08:00:00"),
    oc.completed_at   = datetime("2025-09-15T08:03:00"),
    oc.skipped        = false;

MATCH (e:Episode {episode_id: "ep:old-rag-2025-09"})
MATCH (o:Outcome {outcome_id: "oc:old-rag-2025-09"})
MERGE (e)-[:HAS_OUTCOME]->(o);

// Capability belief derived from this episode.
// axis:"capability" — source is watch/FIT data (Rule #7; capability != preference).
// type:"inferred" — never posed as "stated" until user confirms.
// confidence 0.35 — provisional: N=1, below the N=3 promotion threshold (§2).
MERGE (bl:Belief {belief_id: "bl:josh-pace-moderate-001"})
  ON CREATE SET
    bl.owner_id             = "mem:josh",
    bl.subject_id           = "mem:josh",
    bl.subject_type         = "person",
    bl.axis                 = "capability",
    bl.type                 = "inferred",
    bl.key                  = "pace_on_grade_moderate",
    bl.value                = "15.8",
    bl.confidence           = 0.35,
    bl.corroboration_n      = 1,
    bl.source_episode_ids   = ["ep:old-rag-2025-09"],
    bl.created_at           = datetime("2025-09-14T18:30:00"),
    bl.last_updated_at      = datetime("2025-09-14T18:30:00"),
    bl.decays               = true,
    bl.decay_half_life_days = 180,
    bl.confirmed_by_user    = false;

MATCH (bl:Belief {belief_id: "bl:josh-pace-moderate-001"})
MATCH (e:Episode {episode_id: "ep:old-rag-2025-09"})
MERGE (bl)-[:DERIVED_FROM]->(e);

MATCH (bl:Belief {belief_id: "bl:josh-pace-moderate-001"})
MATCH (p:Person {member_id: "mem:josh"})
MERGE (bl)-[:ABOUT]->(p);

// PhysicalProfile: capability summary, one node per Person, updated as beliefs accrue
MERGE (phys:PhysicalProfile {profile_id: "phys:josh"})
  ON CREATE SET
    phys.owner_id        = "mem:josh",
    phys.pace_on_grade   = 15.8,
    phys.pace_confidence = 0.35,
    phys.max_distance_m  = 14650,
    phys.max_ascent_m    = 735,
    phys.heat_response   = "normal",
    phys.typical_season  = ["09"],
    phys.episode_count   = 1,
    phys.last_episode_at = date("2025-09-14"),
    phys.updated_at      = datetime("2025-09-14T18:30:00");

MATCH (p:Person {member_id: "mem:josh"})
MATCH (phys:PhysicalProfile {profile_id: "phys:josh"})
MERGE (p)-[:HAS_PROFILE]->(phys);

// PartyProfile: observed pace and composition when this party hikes together
MERGE (ppr:PartyProfile {profile_id: "party:josh+ruby"})
  ON CREATE SET
    ppr.owner_id       = "mem:josh",
    ppr.party_key      = "josh+ruby",
    ppr.episode_count  = 1,
    ppr.typical_pace_m = 15.8,
    ppr.ruby_keep_rate = 1.0,
    ppr.created_at     = datetime("2025-09-14T18:30:00"),
    ppr.updated_at     = datetime("2025-09-14T18:30:00");

MATCH (p:Person {member_id: "mem:josh"})
MATCH (ppr:PartyProfile {profile_id: "party:josh+ruby"})
MERGE (p)-[:HAS_PARTY_PROFILE]->(ppr);

RETURN "schema v0.2.0 applied + Old Rag seed + Stage-5 personal overlay loaded" AS status;
