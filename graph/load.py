"""Neo4j ingestion loader — idempotent MERGE upserts for world (public) nodes.

All writes use MERGE so the pipeline is safe to re-run (monthly refresh pattern
from Stage 3). These functions write **world/public** nodes (Area / CanonicalTrail
/ Trailhead / Segment / SourceRecord) — which are unowned, so they correctly need
no ScopedSession scope clause. Owned-node writes (Episode / Belief / etc.) go
through `ScopedSession.run_write` instead (rule #4 / thread T2, Epic 011); this
loader is the world-layer path only. The caller passes a `runner` callable
`(cypher: str, params: dict) -> Any`; inject a real `neo4j.Session.run` for
production or a list-appender for tests/dry-runs.

Ownership of world nodes: `owner_id` is intentionally absent. Personal overlay
nodes (Episode, Belief, etc.) are a Phase-1 concern (Stage 5).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

Runner = Callable[[str, dict[str, Any]], Any]


def make_runner(neo4j_session: Any) -> Runner:
    """Wrap a live neo4j.Session into the Runner interface."""

    def run(cypher: str, params: dict[str, Any]) -> Any:
        return neo4j_session.run(cypher, **params)

    return run


# ── World nodes ──────────────────────────────────────────────────────────────


def load_area(
    runner: Runner,
    area_id: str,
    name: str,
    *,
    manager: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    ingest_version: str | None = None,
) -> None:
    params: dict[str, Any] = {"area_id": area_id, "name": name, "iv": ingest_version or _today()}
    set_clauses = ["a.name = $name", "a.ingest_version = $iv"]
    if manager:
        params["manager"] = manager
        set_clauses.append("a.manager = $manager")
    if lat is not None and lon is not None:
        params["lat"] = lat
        params["lon"] = lon
        set_clauses.append("a.point = point({latitude: $lat, longitude: $lon})")
    runner(
        f"MERGE (a:Area {{area_id: $area_id}}) SET {', '.join(set_clauses)}",
        params,
    )


def load_canonical_trail(
    runner: Runner,
    canonical_id: str,
    name: str,
    *,
    region: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    is_loop: bool | None = None,
    length_mi: float | None = None,
    length_source: str | None = None,
    gain_ft: float | None = None,
    gain_source: str | None = None,
    ingest_version: str | None = None,
) -> None:
    params: dict[str, Any] = {"cid": canonical_id, "name": name, "iv": ingest_version or _today()}
    set_clauses = ["t.name = $name", "t.ingest_version = $iv"]
    if region:
        params["region"] = region
        set_clauses.append("t.region = $region")
    if lat is not None and lon is not None:
        params["lat"] = lat
        params["lon"] = lon
        set_clauses.append("t.point = point({latitude: $lat, longitude: $lon})")
    if is_loop is not None:
        params["is_loop"] = is_loop
        set_clauses.append("t.is_loop = $is_loop")
    if length_mi is not None:
        params["length_mi"] = length_mi
        params["length_source"] = length_source or ""
        set_clauses += ["t.length_mi = $length_mi", "t.length_source = $length_source"]
    if gain_ft is not None:
        params["gain_ft"] = gain_ft
        params["gain_source"] = gain_source or ""
        set_clauses += ["t.gain_ft = $gain_ft", "t.gain_source = $gain_source"]
    runner(
        f"MERGE (t:CanonicalTrail {{canonical_id: $cid}}) SET {', '.join(set_clauses)}",
        params,
    )


def load_source_record(
    runner: Runner,
    sr_uid: str,
    source: str,
    *,
    source_id: str | None = None,
    raw_name: str | None = None,
    raw_geom_wkt: str | None = None,
    allowed_use: str | None = None,
    surface: str | None = None,
    length_mi: float | None = None,
    ingest_version: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    params: dict[str, Any] = {
        "sr_uid": sr_uid,
        "source": source,
        "sid": source_id or "",
        "iv": ingest_version or _today(),
    }
    set_clauses = ["r.source = $source", "r.source_id = $sid", "r.ingest_version = $iv"]
    if raw_name:
        params["raw_name"] = raw_name
        set_clauses.append("r.raw_name = $raw_name")
    if raw_geom_wkt:
        params["raw_geom_wkt"] = raw_geom_wkt
        set_clauses.append("r.raw_geom_wkt = $raw_geom_wkt")
    if allowed_use:
        params["allowed_use"] = allowed_use
        set_clauses.append("r.allowed_use = $allowed_use")
    if surface:
        params["surface"] = surface
        set_clauses.append("r.surface = $surface")
    if length_mi is not None:
        params["length_mi"] = length_mi
        set_clauses.append("r.length_mi = $length_mi")
    # Cypher reserved words that are also valid Python identifiers would produce
    # invalid property access (r.return, r.where, etc.). Block the most dangerous.
    _CYPHER_RESERVED = frozenset(
        {
            "return",
            "where",
            "match",
            "create",
            "merge",
            "delete",
            "set",
            "with",
            "order",
            "limit",
            "skip",
            "call",
            "yield",
            "union",
        }
    )
    for k, v in (extra or {}).items():
        if not k.isidentifier():
            raise ValueError(f"extras key {k!r} is not a valid property name")
        if k.lower() in _CYPHER_RESERVED:
            raise ValueError(f"extras key {k!r} is a Cypher reserved word")
        params[f"ex_{k}"] = v
        set_clauses.append(f"r.{k} = $ex_{k}")
    runner(
        f"MERGE (r:SourceRecord {{sr_uid: $sr_uid}}) SET {', '.join(set_clauses)}",
        params,
    )


def merge_same_as(
    runner: Runner,
    canonical_id: str,
    sr_uid: str,
    *,
    source: str,
    match_method: str = "name+geom",
    match_score: float = 0.0,
    matched_on: list[str] | None = None,
    ingest_version: str | None = None,
) -> None:
    params: dict[str, Any] = {
        "cid": canonical_id,
        "sr_uid": sr_uid,
        "source": source,
        "method": match_method,
        "score": match_score,
        "matched_on": matched_on or [],
        "iv": ingest_version or _today(),
    }
    runner(
        """
        MATCH (t:CanonicalTrail {canonical_id: $cid})
        MATCH (r:SourceRecord {sr_uid: $sr_uid})
        MERGE (t)<-[sa:SAME_AS {source: $source}]-(r)
        SET sa.match_method = $method,
            sa.match_score  = $score,
            sa.matched_on   = $matched_on,
            sa.ingest_version = $iv
        """,
        params,
    )


def link_area_contains(runner: Runner, area_id: str, canonical_id: str) -> None:
    runner(
        """
        MATCH (a:Area {area_id: $area_id})
        MATCH (t:CanonicalTrail {canonical_id: $cid})
        MERGE (a)-[:CONTAINS]->(t)
        """,
        {"area_id": area_id, "cid": canonical_id},
    )


def load_trailhead(
    runner: Runner,
    trailhead_id: str,
    name: str,
    lat: float,
    lon: float,
    *,
    canonical_ids: list[str] | None = None,
    area_id: str | None = None,
    ridb_facility_id: str | None = None,
    ingest_version: str | None = None,
) -> None:
    params: dict[str, Any] = {
        "th_id": trailhead_id,
        "name": name,
        "lat": lat,
        "lon": lon,
        "iv": ingest_version or _today(),
    }
    set_clauses = [
        "h.name = $name",
        "h.point = point({latitude: $lat, longitude: $lon})",
        "h.ingest_version = $iv",
    ]
    if ridb_facility_id:
        params["ridb_fid"] = ridb_facility_id
        set_clauses.append("h.ridb_facility_id = $ridb_fid")
    runner(
        f"MERGE (h:Trailhead {{trailhead_id: $th_id}}) SET {', '.join(set_clauses)}",
        params,
    )
    for cid in canonical_ids or []:
        runner(
            """
            MATCH (h:Trailhead {trailhead_id: $th_id})
            MATCH (t:CanonicalTrail {canonical_id: $cid})
            MERGE (h)-[:ACCESSES]->(t)
            """,
            {"th_id": trailhead_id, "cid": cid},
        )
    if area_id:
        runner(
            """
            MATCH (h:Trailhead {trailhead_id: $th_id})
            MATCH (a:Area {area_id: $area_id})
            MERGE (h)-[:LOCATED_IN]->(a)
            """,
            {"th_id": trailhead_id, "area_id": area_id},
        )


def _today() -> str:
    return date.today().isoformat()[:7]  # YYYY-MM
