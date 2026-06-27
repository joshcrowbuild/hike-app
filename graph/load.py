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

from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import date
from typing import Any

Runner = Callable[[str, dict[str, Any]], Any]

# Distinguishes "caller omitted this optional property" from "caller explicitly passed
# None to CLEAR it". Used by load_canonical_trail so a re-ingest that loses geometry
# can null out a now-stale property rather than leave it standing (source-or-silence).
_UNSET: Any = object()


def make_runner(neo4j_session: Any) -> Runner:
    """Wrap a live neo4j.Session into the Runner interface."""

    def run(cypher: str, params: dict[str, Any]) -> Any:
        return neo4j_session.run(cypher, **params)

    return run


# Cypher reserved words that are also valid Python identifiers would produce invalid
# property access (`t.return`, `r.where`, …). A property name interpolated into Cypher
# (a SourceRecord `extra`, an EnrichmentFact `attribute`) must be a bare identifier and
# not one of these — both are author/config-controlled, but we fail loud rather than
# emit broken Cypher.
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


# Access-control keys a world-layer write must never set via a dynamic property name:
# `owner_id` (+ scoping params) exist only on OWNED labels (graph.queries.OWNED_LABELS),
# and the access model relies on that invariant. Blocking them here keeps a buggy/hostile
# enrichment source from stamping `owner_id` onto a world node (CanonicalTrail) — cheap
# defense-in-depth so "owner_id is owned-only" stays true by construction.
_FORBIDDEN_PROPERTY_NAMES = frozenset({"owner_id", "granted_ids", "viewer_id"})


def _validate_property_name(name: Any) -> None:
    """Guard a dynamically-interpolated Cypher property name (rule: fail loud at the
    boundary). Raises `ValueError` on a non-identifier, a reserved word, or an
    access-control key that must not appear on a world node."""
    if not isinstance(name, str) or not name.isidentifier():
        raise ValueError(f"property name {name!r} is not a valid Cypher property name")
    if name.lower() in _CYPHER_RESERVED:
        raise ValueError(f"property name {name!r} is a Cypher reserved word")
    if name.lower() in _FORBIDDEN_PROPERTY_NAMES:
        raise ValueError(f"property name {name!r} is an access-control key (owned-labels only)")


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
    route_geom_wkt: str | None = _UNSET,
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
    if route_geom_wkt is not _UNSET:
        # The precomputed assembled route (Epic 016 S1) — stored ready-to-serve so
        # the trip/detail API is a simple read, not a runtime segment-walk (D3/D4).
        # Passing None explicitly SETs null (Neo4j drops the property), so a re-ingest
        # that loses geometry clears the stale route rather than serving it (Rule #1).
        params["route_geom_wkt"] = route_geom_wkt
        set_clauses.append("t.route_geom_wkt = $route_geom_wkt")
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


def load_segment(
    runner: Runner,
    segment_id: str,
    geom_wkt: str,
    *,
    canonical_id: str,
    length_mi: float | None = None,
    lat: float | None = None,
    lon: float | None = None,
    ingest_version: str | None = None,
) -> None:
    """Upsert a trail `Segment` (the geometry-bearing unit — `Segment.geom_wkt`) and
    wire `(:CanonicalTrail)-[:HAS_SEGMENT]->(:Segment)` (Epic 016 S1). Idempotent:
    both the node and the edge are MERGEd, so a monthly re-run with a stable
    `segment_id` rewrites in place rather than duplicating."""
    params: dict[str, Any] = {
        "sid": segment_id,
        "geom_wkt": geom_wkt,
        "iv": ingest_version or _today(),
    }
    set_clauses = ["s.geom_wkt = $geom_wkt", "s.ingest_version = $iv"]
    if length_mi is not None:
        params["length_mi"] = length_mi
        set_clauses.append("s.length_mi = $length_mi")
    if lat is not None and lon is not None:
        params["lat"] = lat
        params["lon"] = lon
        set_clauses.append("s.point = point({latitude: $lat, longitude: $lon})")
    runner(
        f"MERGE (s:Segment {{segment_id: $sid}}) SET {', '.join(set_clauses)}",
        params,
    )
    runner(
        "MATCH (t:CanonicalTrail {canonical_id: $cid})\n"
        "MATCH (s:Segment {segment_id: $sid})\n"
        "MERGE (t)-[:HAS_SEGMENT]->(s)",
        {"cid": canonical_id, "sid": segment_id},
    )


def clear_trail_segments(runner: Runner, canonical_id: str) -> None:
    """Detach + delete a trail's existing `Segment`s before re-persisting (Epic 016
    S1 re-ingest hygiene). A monthly re-run whose route assembles into fewer parts —
    or loses geometry entirely — would otherwise orphan the higher-index `Segment`s
    and their `HAS_SEGMENT` edges; the trip/detail runtime-assembly fallback
    (`collect(s.geom_wkt)`) would then fold that stale geometry back into the served
    route (idempotency + Rule #1). Segments are trail-private (their id embeds the
    `canonical_id`), so deleting the trail's own is safe."""
    runner(
        "MATCH (t:CanonicalTrail {canonical_id: $cid})-[:HAS_SEGMENT]->(s:Segment)\n"
        "DETACH DELETE s",
        {"cid": canonical_id},
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
    for k, v in (extra or {}).items():
        _validate_property_name(k)
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


# ── Enrichment loader (Epic 017 S1) — the deferred graph write, now real ───────


def load_enrichment_facts(runner: Runner, facts: Iterable[Any]) -> int:
    """Persist `EnrichmentFact`s onto their target `CanonicalTrail` nodes — the
    "no graph write yet" gap the pipeline left for the first enrichment source
    (Epic 017 AC-1.1). Generic by design: each fact's `attribute` becomes a node
    property and its `value` the value, grouped per node into ONE idempotent
    MERGE+SET. The seam/protocol (`CorpusSource`/`EnrichmentFact`) is reused, not
    rebuilt — this is only its loader.

    `CanonicalTrail` is a world (unowned) node, so writes go through the world-layer
    `runner`, not the owner-scoped write seam (which guards owned labels only). A
    fact with no `canonical_id` is skipped (nothing to attach it to). Within a node,
    a later fact for the same attribute wins. Returns the number of nodes written.

    Facts are duck-typed (`.canonical_id`, `.attribute`, `.value`) so this lower
    `graph` layer never imports the `ingestion` seam (no layering cycle)."""
    by_node: dict[str, dict[str, Any]] = defaultdict(dict)
    for fact in facts:
        cid = getattr(fact, "canonical_id", None)
        if not cid:
            continue
        attr = fact.attribute
        _validate_property_name(attr)
        by_node[cid][attr] = fact.value

    for cid, attrs in by_node.items():
        params: dict[str, Any] = {"cid": cid}
        set_clauses: list[str] = []
        for i, (attr, value) in enumerate(attrs.items()):
            pkey = f"v{i}"
            params[pkey] = value
            set_clauses.append(f"t.{attr} = ${pkey}")
        runner(
            f"MERGE (t:CanonicalTrail {{canonical_id: $cid}}) SET {', '.join(set_clauses)}",
            params,
        )
    return len(by_node)


def _today() -> str:
    return date.today().isoformat()[:7]  # YYYY-MM
