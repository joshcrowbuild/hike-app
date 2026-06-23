"""Scoped Cypher query builders.

Pure functions returning ``(cypher, params)`` — no driver, no I/O, so they unit-
test without a database. World nodes (Area / CanonicalTrail / Trailhead /
Segment) are unowned and public; queries that touch **owned** nodes (the personal
overlay) MUST carry the owner-scope clause (rule #4 / thread T2). `owner_scope`
is the single sanctioned way to write that clause; `$viewer_id` / `$granted_ids`
are injected by the ScopedSession at run time.
"""

from __future__ import annotations

from typing import Any


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
        "       t.is_loop AS is_loop, t.length_mi AS length_mi,\n"
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
        "       t.is_loop AS is_loop, t.length_mi AS length_mi,\n"
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


def episodes_on_trail(canonical_id: str) -> tuple[str, dict[str, Any]]:
    """Personal-overlay read (reserved for Stage 5) — demonstrates the seam: any
    query touching owned :Episode nodes is owner-scoped."""
    cypher = (
        "MATCH (p:Person)-[:DID]->(e:Episode)-[:ON]->"
        "(t:CanonicalTrail {canonical_id: $canonical_id})\n"
        f"WHERE {owner_scope('e')}\n"
        "RETURN e"
    )
    return cypher, {"canonical_id": canonical_id}
