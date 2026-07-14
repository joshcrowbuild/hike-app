"""Scoped Cypher query builders — the single author of owned-node Cypher.

Pure functions returning ``(cypher, params)`` — no driver, no I/O, so they unit-
test without a database. World nodes (Area / CanonicalTrail / Trailhead /
Segment / SourceRecord) are unowned and public; Cypher that touches **owned**
nodes (the personal overlay) MUST carry the owner-scope clause (rule #4 / thread
T2), and this module is the *only* sanctioned place that Cypher is written — for
**reads and writes** alike (Epic 011). `owner_scope` is the single sanctioned way
to write the clause; `$viewer_id` / `$granted_ids` are injected by the
ScopedSession at run time.

`OWNED_LABELS` is the shared manifest of owner-keyed labels; `assert_scoped_write`
is the boundary guard `ScopedSession.run_write` calls so no writer can create or
overwrite an owned node by forgetting the scope clause (gap-audit C2). The same
manifest is importable by a future owned-label CI lint (gap-audit M9) and by the
write-path fuzz test.
"""

from __future__ import annotations

import re
from typing import Any

# Owner-keyed labels (carry `owner_id`; every read/write must owner-scope them).
# `CommonsObservation` is person-severed by design (gap-audit C1) and `Dependent`
# is a household sub-node with no `owner_id` (schema:171) — both excluded, or the
# guard would demand a scope clause on a label that has nothing to scope against.
OWNED_LABELS: frozenset[str] = frozenset(
    {"Episode", "Belief", "PhysicalProfile", "Outcome", "PartyProfile"}
)

# A write touching an owned label must scope it to $viewer_id. We accept either
# `owner_scope(var)`'s clause (mutate path) or a create that binds
# `owner_id = $viewer_id` — both contain `owner_id = $viewer_id` (assignment /
# WHERE form) or `owner_id: $viewer_id` (map-pattern form). A free `$owner` does
# NOT satisfy the guard (AC-1.6): the only owner a builder may write is the viewer.
_OWNED_LABEL_RE = re.compile(r":\s*(?:" + "|".join(sorted(OWNED_LABELS)) + r")\b")
_OWNER_SCOPE_RE = re.compile(r"(?:\.owner_id\s*=\s*\$viewer_id|\bowner_id\s*:\s*\$viewer_id)")


class UnscopedWriteError(ValueError):
    """An owned-label write reached the seam without an owner-scope clause.

    A subclass of ValueError: an unscoped owned write is a programming error
    (fail loudly at the boundary, rule #4), never a runtime degrade.
    """


def assert_scoped_write(cypher: str) -> None:
    """Guard for `ScopedSession.run_write`: refuse an owned-label `MERGE`/`SET`/
    `CREATE` that carries no owner-scope clause bound to `$viewer_id` (rule #4,
    extended to writes — gap-audit C2). World-only writes pass untouched."""
    if _OWNED_LABEL_RE.search(cypher) and not _OWNER_SCOPE_RE.search(cypher):
        raise UnscopedWriteError(
            "owned-label write reached run_write without an owner-scope clause "
            "(owner_scope(var) or owner_id = $viewer_id). Author it via "
            f"graph.queries so the scope cannot be forgotten. Cypher:\n{cypher}"
        )


def owner_scope(var: str) -> str:
    """Access-control clause for an owned node bound to `var` (rule #4)."""
    return f"({var}.owner_id = $viewer_id OR {var}.owner_id IN $granted_ids)"


def candidate_trails_near(
    lat: float, lon: float, radius_m: float, k: int = 10
) -> tuple[str, dict[str, Any]]:
    """Scout candidate generation: trails reachable from trailheads within
    `radius_m` of the origin, nearest first. World nodes only -> inherently public.
    Uses the `trailhead_point` POINT index."""
    # LIMIT is applied after Python dedup in scout.py, so we fetch k*5 to ensure
    # enough unique trails survive deduplication (multiple trailheads per trail).
    cypher = (
        "MATCH (h:Trailhead)\n"
        "WHERE point.distance(h.point, point($origin)) <= $radius_m\n"
        "MATCH (h)-[:ACCESSES]->(t:CanonicalTrail)\n"
        "OPTIONAL MATCH (a:Area)-[:CONTAINS]->(t)\n"
        "RETURN t.canonical_id AS canonical_id, t.name AS name, t.point AS point,\n"
        "       h.point AS trailhead_point,\n"
        "       t.is_loop AS is_loop, t.length_mi AS length_mi, t.way_type AS way_type,\n"
        "       t.outside_boundary AS outside_boundary,\n"
        "       h.trailhead_id AS trailhead_id,\n"
        "       point.distance(h.point, point($origin)) AS distance_m,\n"
        "       a.area_id AS area_id\n"
        "ORDER BY distance_m ASC\n"
        "LIMIT $prefetch"
    )
    params: dict[str, Any] = {
        "origin": {"latitude": lat, "longitude": lon},
        "radius_m": radius_m,
        "prefetch": k * 5,  # over-fetch so dedup in scout.py can yield k unique trails
    }
    return cypher, params


def candidate_trails_near_direct(
    lat: float, lon: float, radius_m: float, k: int = 10
) -> tuple[str, dict[str, Any]]:
    """Fallback Scout query when no Trailhead nodes exist: search CanonicalTrail.point
    directly. Uses the canonical_trail_point POINT index (added in schema v0.1.1)."""
    cypher = (
        "MATCH (t:CanonicalTrail)\n"
        "WHERE t.point IS NOT NULL\n"
        "  AND point.distance(t.point, point($origin)) <= $radius_m\n"
        "OPTIONAL MATCH (a:Area)-[:CONTAINS]->(t)\n"
        "RETURN t.canonical_id AS canonical_id, t.name AS name, t.point AS point,\n"
        "       t.point AS trailhead_point,\n"
        "       t.is_loop AS is_loop, t.length_mi AS length_mi, t.way_type AS way_type,\n"
        "       t.outside_boundary AS outside_boundary,\n"
        "       null AS trailhead_id,\n"
        "       point.distance(t.point, point($origin)) AS distance_m,\n"
        "       a.area_id AS area_id\n"
        "ORDER BY distance_m ASC\n"
        "LIMIT $prefetch"
    )
    params: dict[str, Any] = {
        "origin": {"latitude": lat, "longitude": lon},
        "radius_m": radius_m,
        "prefetch": k * 5,
    }
    return cypher, params


# The shared trip/detail projection (Epic 016 S1 + Epic 017 S4). World nodes only
# (CanonicalTrail / Segment / Trailhead) → inherently public, no owner scope. Returns
# the precomputed `route_geom_wkt` plus the raw `Segment.geom_wkt`s for the API's
# runtime-assembly fallback, the lexicographically-first accessing trailhead's point by
# `trailhead_id` (or the trail's own point as fallback), and the elevation
# parallel-arrays + scalars. `ORDER BY h.trailhead_id` makes the trailhead choice
# deterministic when a trail has more than one accessing Trailhead — `collect` has no
# defined order otherwise (null-safe: the OPTIONAL MATCH's null `h` is dropped by
# `collect`). Bound to whatever `t` the preceding MATCH selected, so it serves one trail
# or many unchanged.
_TRAIL_DETAIL_PROJECTION = (
    "OPTIONAL MATCH (t)-[:HAS_SEGMENT]->(s:Segment)\n"
    "WITH t, collect(s.geom_wkt) AS segment_wkts\n"
    "OPTIONAL MATCH (h:Trailhead)-[:ACCESSES]->(t)\n"
    "WITH t, segment_wkts, h ORDER BY h.trailhead_id\n"
    "WITH t, segment_wkts, collect(h.point) AS th_points\n"
    "RETURN t.canonical_id        AS canonical_id,\n"
    "       t.name                 AS name,\n"
    "       t.route_geom_wkt       AS route_geom_wkt,\n"
    "       segment_wkts           AS segment_wkts,\n"
    "       t.point                AS trail_point,\n"
    "       th_points[0]           AS trailhead_point,\n"
    "       t.profile_distances_m  AS profile_distances_m,\n"
    "       t.profile_elevations_m AS profile_elevations_m,\n"
    "       t.total_gain_m         AS total_gain_m,\n"
    "       t.total_loss_m         AS total_loss_m,\n"
    "       t.max_grade_pct        AS max_grade_pct,\n"
    "       t.elev_source          AS elev_source,\n"
    "       t.elev_resolution_m    AS elev_resolution_m"
)


def trail_detail(canonical_id: str) -> tuple[str, dict[str, Any]]:
    """Trip/detail read for one trail (the `GET /trail/{id}` endpoint)."""
    cypher = "MATCH (t:CanonicalTrail {canonical_id: $cid})\n" + _TRAIL_DETAIL_PROJECTION
    return cypher, {"cid": canonical_id}


def trails_detail(canonical_ids: list[str]) -> tuple[str, dict[str, Any]]:
    """Batched trip/detail read for many trails (the feed's per-card maps fields) —
    one round trip instead of N. Same projection as `trail_detail`; returns one row
    per matched canonical id (unknown ids simply don't appear)."""
    cypher = "MATCH (t:CanonicalTrail)\nWHERE t.canonical_id IN $cids\n" + _TRAIL_DETAIL_PROJECTION
    return cypher, {"cids": list(canonical_ids)}


def trail_source_corroboration(canonical_ids: list[str]) -> tuple[str, dict[str, Any]]:
    """Distinct-origin corroboration per trail — the CDP-01 moat (spike:
    `docs/research/cdp-01-corroboration-feasibility-spike.md`). Corroboration's locus is
    the corpus/`SAME_AS` layer, not the single-source live path: each trail is joined by
    `SAME_AS` to one `:SourceRecord` per independent upstream origin (OSM + NPS + USFS +
    USGS_NTD …), so the count of DISTINCT `SourceRecord.source` in a cluster is the real
    independence count — origins that agree the trail *exists*, never echoed feeds.

    World nodes only (CanonicalTrail / SourceRecord) → inherently public, no owner scope.
    Returns one row per matched id with the sorted distinct `sources` (so a caller can
    reason per-attribute: existence is corroborated by the whole cluster, a specific
    attribute only by its survivorship winner) and the `corroboration` count. A trail
    with no SourceRecords yields an empty list / count 0 — `collect` drops the OPTIONAL
    MATCH's null; the caller floors it at the honest baseline of 1 (the trail came from
    somewhere). Batched (one round trip for a whole feed)."""
    cypher = (
        "MATCH (t:CanonicalTrail)\n"
        "WHERE t.canonical_id IN $cids\n"
        "OPTIONAL MATCH (t)<-[:SAME_AS]-(sr:SourceRecord)\n"
        # ORDER BY before collect so `sources` is deterministically sorted (collect's
        # order is otherwise unspecified); the null source from an unmatched OPTIONAL
        # MATCH is dropped by collect, yielding [] for a SourceRecord-less trail.
        "WITH t, sr.source AS source ORDER BY source\n"
        "WITH t, collect(DISTINCT source) AS sources\n"
        "RETURN t.canonical_id AS canonical_id,\n"
        "       sources              AS sources,\n"
        "       size(sources)        AS corroboration"
    )
    return cypher, {"cids": list(canonical_ids)}


def water_sources_near(
    lat: float, lon: float, radius_m: float, *, limit: int = 50
) -> tuple[str, dict[str, Any]]:
    """On-trail water POIs (spring / well / tap / drinking-water fountain) near
    a point, nearest first (Epic 035). World nodes only -> inherently public,
    no owner scope. Surfaces location + water type + seasonality only — never
    a potability claim (rule #1)."""
    cypher = (
        "MATCH (w:WaterSource)\n"
        "WHERE point.distance(w.point, point($origin)) <= $radius_m\n"
        "RETURN w.water_id AS water_id, w.water_type AS water_type, w.name AS name,\n"
        "       w.point AS point, w.seasonal AS seasonal, w.source AS source,\n"
        "       point.distance(w.point, point($origin)) AS distance_m\n"
        "ORDER BY distance_m ASC\n"
        "LIMIT $limit"
    )
    params: dict[str, Any] = {
        "origin": {"latitude": lat, "longitude": lon},
        "radius_m": radius_m,
        "limit": limit,
    }
    return cypher, params


# ── Owned-node read builders (owner-scoped; run through ScopedSession.run) ──────


def physical_profile_pace_read() -> tuple[str, dict[str, Any]]:
    """The viewer's PhysicalProfile pace + episode count, for the EWMA update.

    Keyed strictly on `owner_id = $viewer_id` (not `owner_scope`): this read feeds
    a self-update, so it must never read a *granted* member's profile — that would
    let their pace contaminate the viewer's own EWMA (rule #5). `owner_scope` is
    for genuine cross-owner reads only."""
    cypher = (
        "MATCH (pp:PhysicalProfile {owner_id: $viewer_id})\n"
        "RETURN pp.pace_on_grade AS pace, pp.episode_count AS count"
    )
    return cypher, {}


def episode_fields_read(episode_id: str) -> tuple[str, dict[str, Any]]:
    """The viewer's Episode distance/ascent/pace, for `process_episode`."""
    cypher = (
        "MATCH (e:Episode {episode_id: $eid})\n"  # noqa
        f"WHERE {owner_scope('e')}\n"
        "RETURN e.distance_m AS distance_m, e.ascent_m AS ascent_m,\n"
        "       e.pace_on_grade AS pace_on_grade"
    )
    return cypher, {"eid": episode_id}


# ── Owned-node write builders (every owned write binds to $viewer_id — rule #4) ─
#
# These are the only place owned-node MERGE/SET/CREATE Cypher is authored. Each
# either carries `owner_scope(var)` (mutate) or binds `owner_id = $viewer_id`
# (create), so each passes `assert_scoped_write`. No builder accepts an owner
# param distinct from the viewer (AC-1.6 / AC-3.4) — the viewer is the only owner
# a write may name; `$viewer_id` is injected by the ScopedSession.


def upsert_episode(
    episode_id: str,
    *,
    watch_activity_id: str,
    source: str,
    distance_m: float | None,
    ascent_m: float | None,
    descent_m: float | None,
    moving_min: float | None,
    duration_min: float | None,
    avg_heart_rate: int | None,
    pace_on_grade: float | None,
    now: str,
    start_date: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Upsert the viewer's Episode. `owner_id` is part of the MERGE key, so a
    foreign `episode_id` can never MATCH (and re-own) another member's node — the
    seam enforces ownership structurally, not by id-naming convention. With the
    global `episode_id` uniqueness constraint, a cross-owner id fails closed.

    `start_date` is the FIT activity's calendar date (``YYYY-MM-DD``); it lands as the
    `e.date` Date that the 18-month retrieval window filters on (Epic 003 AC-3.2).
    `date($start_date)` is null-safe — a `None` start_date leaves `e.date` null, so an
    undated episode is simply absent from the recency window rather than crashing."""
    cypher = (
        "MERGE (e:Episode {episode_id: $eid, owner_id: $viewer_id})\n"  # noqa
        "ON CREATE SET e.created_at = $now\n"
        "SET e.watch_activity_id = $wid,\n"
        "    e.source            = $source,\n"
        "    e.date              = date($start_date),\n"
        "    e.distance_m        = $distance,\n"
        "    e.ascent_m          = $ascent,\n"
        "    e.descent_m         = $descent,\n"
        "    e.moving_min        = $moving_min,\n"
        "    e.duration_min      = $duration_min,\n"
        "    e.avg_heart_rate    = $hr,\n"
        "    e.pace_on_grade     = $pace,\n"
        "    e.fit_parsed        = true,\n"
        "    e.updated_at        = $now"
    )
    params: dict[str, Any] = {
        "eid": episode_id,
        "wid": watch_activity_id,
        "source": source,
        "start_date": start_date,
        "distance": distance_m,
        "ascent": ascent_m,
        "descent": descent_m,
        "moving_min": moving_min,
        "duration_min": duration_min,
        "hr": avg_heart_rate,
        "pace": pace_on_grade,
        "now": now,
    }
    return cypher, params


def wire_person_did_episode(episode_id: str) -> tuple[str, dict[str, Any]]:
    """Wire the viewer's Person to their Episode. The Episode is matched under
    owner scope (the Person anchor is an identity match, $viewer_id-keyed)."""
    cypher = (  # noqa
        "MATCH (p:Person {member_id: $viewer_id})\n"
        "MATCH (e:Episode {episode_id: $eid})\n"
        f"WHERE {owner_scope('e')}\n"
        "MERGE (p)-[:DID]->(e)"
    )
    return cypher, {"eid": episode_id}


def wire_episode_on_trail(episode_id: str, canonical_id: str) -> tuple[str, dict[str, Any]]:
    """Wire the viewer's Episode to the (world, unowned) CanonicalTrail it was on."""
    cypher = (
        "MATCH (e:Episode {episode_id: $eid})\n"  # noqa
        f"WHERE {owner_scope('e')}\n"
        "MATCH (t:CanonicalTrail {canonical_id: $cid})\n"
        "MERGE (e)-[:ON]->(t)"
    )
    return cypher, {"eid": episode_id, "cid": canonical_id}


def upsert_physical_profile_pace(pace: float) -> tuple[str, dict[str, Any]]:
    """MERGE the viewer's PhysicalProfile (keyed `owner_id = $viewer_id`, so it is
    born owner-scoped) and set the EWMA pace + bump `episode_count`."""
    cypher = (
        "MERGE (pp:PhysicalProfile {owner_id: $viewer_id})\n"
        "SET pp.pace_on_grade = $pace,\n"
        "    pp.episode_count = coalesce(pp.episode_count, 0) + 1,\n"
        "    pp.updated_at    = datetime()"
    )
    return cypher, {"pace": pace}


def upsert_physical_profile_maxima(
    distance_m: float | None, ascent_m: float | None
) -> tuple[str, dict[str, Any]]:
    """MERGE the viewer's PhysicalProfile and lift max distance/ascent. ON CREATE
    seeds the first-episode maxima; ON MATCH keeps the running maximum."""
    cypher = (
        "MERGE (pp:PhysicalProfile {owner_id: $viewer_id})\n"
        "ON CREATE SET\n"
        "    pp.max_distance_m = $distance_m,\n"
        "    pp.max_ascent_m   = $ascent_m,\n"
        "    pp.updated_at     = datetime()\n"
        "ON MATCH SET\n"
        "    pp.max_distance_m = CASE WHEN $distance_m IS NOT NULL AND\n"
        "                             $distance_m > coalesce(pp.max_distance_m, 0)\n"
        "                        THEN $distance_m ELSE pp.max_distance_m END,\n"
        "    pp.max_ascent_m   = CASE WHEN $ascent_m IS NOT NULL AND\n"
        "                             $ascent_m > coalesce(pp.max_ascent_m, 0)\n"
        "                        THEN $ascent_m ELSE pp.max_ascent_m END,\n"
        "    pp.updated_at     = datetime()"
    )
    return cypher, {"distance_m": distance_m, "ascent_m": ascent_m}


def upsert_physical_profile_last_episode(episode_date: str) -> tuple[str, dict[str, Any]]:
    """Advance the viewer's `PhysicalProfile.last_episode_at` to this episode's date,
    kept as a running maximum so an out-of-order backfill never regresses it. Born
    owner-scoped (MERGE keyed `owner_id = $viewer_id`), so it passes the owned-write
    guard. `date($episode_date)` parses the ``YYYY-MM-DD`` string server-side."""
    cypher = (
        "MERGE (pp:PhysicalProfile {owner_id: $viewer_id})\n"
        "SET pp.last_episode_at = CASE\n"
        "        WHEN $episode_date IS NULL THEN pp.last_episode_at\n"
        "        WHEN pp.last_episode_at IS NULL OR date($episode_date) > pp.last_episode_at\n"
        "            THEN date($episode_date)\n"
        "        ELSE pp.last_episode_at END,\n"
        "    pp.updated_at = datetime()"
    )
    return cypher, {"episode_date": episode_date}


def upsert_pace_belief(belief_id: str, value: str) -> tuple[str, dict[str, Any]]:
    """MERGE the viewer's `pace_on_grade_moderate` capability Belief. `owner_id`
    is part of the MERGE key, so the ON MATCH value update can only ever touch the
    viewer's own belief — a foreign `belief_id` can never MATCH (and clobber) it."""
    cypher = (
        "MERGE (b:Belief {belief_id: $bid, owner_id: $viewer_id})\n"  # noqa
        "ON CREATE SET\n"
        "    b.subject_id           = $viewer_id,\n"
        "    b.subject_type         = 'person',\n"
        "    b.axis                 = 'capability',\n"
        "    b.type                 = 'inferred',\n"
        "    b.key                  = 'pace_on_grade_moderate',\n"
        "    b.value                = $value,\n"
        "    b.confidence           = 0.3,\n"
        "    b.corroboration_n      = 0,\n"
        "    b.decays               = true,\n"
        "    b.decay_half_life_days = 180,\n"
        "    b.confirmed_by_user    = false,\n"
        "    b.created_at           = datetime(),\n"
        "    b.last_updated_at      = datetime()\n"
        "ON MATCH SET\n"
        "    b.value                = $value,\n"
        "    b.last_updated_at      = datetime()"
    )
    return cypher, {"bid": belief_id, "value": value}


def wire_belief_derived_from_episode(belief_id: str, episode_id: str) -> tuple[str, dict[str, Any]]:
    """Provenance edge Belief-[:DERIVED_FROM]->Episode (rule #7). Both owned ends
    are matched under owner scope so the edge can never cross owners."""
    cypher = (
        "MATCH (b:Belief {belief_id: $bid})\n"  # noqa
        "MATCH (e:Episode {episode_id: $eid})\n"
        f"WHERE {owner_scope('b')} AND {owner_scope('e')}\n"
        "MERGE (b)-[:DERIVED_FROM]->(e)"
    )
    return cypher, {"bid": belief_id, "eid": episode_id}


def recount_belief_corroboration(belief_id: str, threshold: int) -> tuple[str, dict[str, Any]]:
    """Recount `corroboration_n` from **owner-scoped** DERIVED_FROM episodes and
    re-promote confidence (gap-audit M8 — the count was owner-unscoped). The
    confidence `CASE` (n≥threshold → 0.7) survives the rewrite."""
    cypher = (
        "MATCH (b:Belief {belief_id: $bid})\n"  # noqa
        "MATCH (b)-[:DERIVED_FROM]->(e:Episode)\n"
        f"WHERE {owner_scope('e')}\n"
        "WITH b, count(e) AS n\n"
        "SET b.corroboration_n = n,\n"
        "    b.confidence      = CASE WHEN n >= $threshold THEN 0.7 ELSE 0.3 END"
    )
    return cypher, {"bid": belief_id, "threshold": threshold}


def wire_belief_about_person(belief_id: str) -> tuple[str, dict[str, Any]]:
    """Ownership edge Belief-[:ABOUT]->Person. The Belief is matched under owner
    scope; the Person anchor is the viewer's identity match."""
    cypher = (
        "MATCH (b:Belief {belief_id: $bid})\n"  # noqa
        f"WHERE {owner_scope('b')}\n"
        "MATCH (p:Person {member_id: $viewer_id})\n"
        "MERGE (b)-[:ABOUT]->(p)"
    )
    return cypher, {"bid": belief_id}


# ── Outcome card (Epic 002) — owned writes, routed through the scoped-write seam ─


def upsert_outcome(
    episode_id: str,
    *,
    outcome_id: str,
    overall: int | None,
    delta_question: str | None,
    delta_answer: str | None,
    skipped: bool,
) -> tuple[str, dict[str, Any]]:
    """MERGE the viewer's post-hike Outcome, idempotent on its natural key (AC-1.5).
    `owner_id` is part of the MERGE key, so a foreign `episode_id` can never MATCH and
    re-own another member's Outcome — ownership is structural, not an id-naming
    convention. ON MATCH refreshes the mutable fields so a re-post updates in place."""
    cypher = (
        "MERGE (o:Outcome {episode_id: $eid, owner_id: $viewer_id})\n"  # noqa
        "ON CREATE SET\n"
        "    o.outcome_id     = $oid,\n"
        "    o.overall        = $overall,\n"
        "    o.delta_question = $delta_q,\n"
        "    o.delta_answer   = $delta_a,\n"
        "    o.skipped        = $skipped,\n"
        "    o.surfaces_at    = datetime(),\n"
        "    o.completed_at   = CASE WHEN NOT $skipped THEN datetime() ELSE null END,\n"
        "    o.created_at     = datetime()\n"
        "ON MATCH SET\n"
        "    o.overall        = $overall,\n"
        "    o.delta_answer   = $delta_a,\n"
        "    o.skipped        = $skipped,\n"
        "    o.updated_at     = datetime()"
    )
    params: dict[str, Any] = {
        "eid": episode_id,
        "oid": outcome_id,
        "overall": overall,
        "delta_q": delta_question,
        "delta_a": delta_answer,
        "skipped": skipped,
    }
    return cypher, params


def wire_episode_has_outcome(episode_id: str) -> tuple[str, dict[str, Any]]:
    """Wire the viewer's Episode to its Outcome (AC-2.1). Both owned ends are matched
    on the viewer's owner-key, so the edge can never cross owners."""
    cypher = (
        "MATCH (e:Episode {episode_id: $eid, owner_id: $viewer_id})\n"  # noqa
        "MATCH (o:Outcome {episode_id: $eid, owner_id: $viewer_id})\n"
        "MERGE (e)-[:HAS_OUTCOME]->(o)"
    )
    return cypher, {"eid": episode_id}


def upsert_stated_belief(belief_id: str, value: str) -> tuple[str, dict[str, Any]]:
    """MERGE the viewer's `stated_preference` Belief from an explicit user statement
    (AC-5: confidence=1.0, decays=false, confirmed_by_user — no LLM). `owner_id` is part
    of the MERGE key (review finding #2), so a foreign `belief_id` can never MATCH and
    clobber another member's belief — ownership is enforced by the seam, not by the
    id-naming convention the seam forbids."""
    cypher = (
        "MERGE (b:Belief {belief_id: $bid, owner_id: $viewer_id})\n"  # noqa
        "ON CREATE SET\n"
        "    b.subject_id         = $viewer_id,\n"
        "    b.subject_type       = 'person',\n"
        "    b.axis               = 'preference',\n"
        "    b.type               = 'stated',\n"
        "    b.key                = 'stated_preference',\n"
        "    b.value              = $value,\n"
        "    b.confidence         = 1.0,\n"
        "    b.corroboration_n    = 1,\n"
        "    b.decays             = false,\n"
        "    b.confirmed_by_user  = true,\n"
        "    b.created_at         = datetime(),\n"
        "    b.last_updated_at    = datetime()\n"
        "ON MATCH SET\n"
        "    b.value              = $value,\n"
        "    b.last_updated_at    = datetime()"
    )
    return cypher, {"bid": belief_id, "value": value}


# ── Commons fork (Epic 010) — UNOWNED, born-severed by construction ───────────


def create_commons_observation(props: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Born-severed `:CommonsObservation` write (Stage 9 §2.1): a node with no
    inbound/outbound edge to any `:Person`/`:Episode`/`:Outcome` and **no
    owner_id**. It is unowned by construction, so it is *correctly* outside the
    owner-scope seam — `assert_scoped_write` does not fire on it (CommonsObservation
    ∉ OWNED_LABELS).

    `MERGE` (not `CREATE`) on the contributor-minted random `observation_id` makes
    the write idempotent under a managed-transaction retry, without weakening
    severance: the id is a fresh uuid4 (born severed, never reused across hikes),
    so the MERGE always creates on the first run and dedups on a re-run. `props`
    are the de-identified values from `commons_fork.build_observation` (band/
    buckets/trimmed track/writer_hash — never the raw pace/date/totals)."""
    cypher = (
        "MERGE (co:CommonsObservation {observation_id: $observation_id})\n"
        "ON CREATE SET\n"
        "    co.trail_id        = $trail_id,\n"
        "    co.segment_ids     = $segment_ids,\n"
        "    co.capability_band = $capability_band,\n"
        "    co.month           = $month,\n"
        "    co.ascent_bucket   = $ascent_bucket,\n"
        "    co.distance_bucket = $distance_bucket,\n"
        "    co.trimmed_track   = $trimmed_track,\n"
        "    co.writer_hash     = $writer_hash,\n"
        "    co.ingest_version  = $ingest_version,\n"
        "    co.written_at      = datetime()"
    )
    return cypher, dict(props)
