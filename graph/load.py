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

import logging
import os
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any

log = logging.getLogger(__name__)

Runner = Callable[[str, dict[str, Any]], Any]

# Fraction of the region's PRIOR CORPUS TOTAL (the CanonicalTrail count snapshotted
# BEFORE the load) that the current run must at least reach before a prune is allowed
# to fire (findings M1 + the collapse-gate correction). A truncated ingest (Overpass
# timeout returning 1 of ~1500 trails) would otherwise sail past the empty-ingest guard
# (n_cur=1 >= min_current=1) and DETACH-DELETE the other ~1499.
#
# The denominator is the PRE-LOAD total, NOT the post-load `n_prev`: because
# `load_canonical_trail` MERGEs by a version-INDEPENDENT canonical_id, a re-ingest flips
# each recovered trail's ingest_version old→new, so after the load `n_prev` is only the
# trails the run MISSED and `n_cur`/`n_prev` are complementary halves of one total. A 50%
# partial (n_cur=750, n_prev=750) would compute `750 < 0.5*750` → False and wrongly PASS,
# then prune the 750 stragglers — a silent half-wipe. Comparing against the pre-load total
# (`750 < 0.5*1500` → 750 < 750) makes the gate scale-correct.
#
# This is the SINGLE shrink knob (finding: the old `ADVENTURE_PRUNE_SHRINK` gated the same
# decision from the other side, `1 - ratio`). Env-overridable via ADVENTURE_PRUNE_MIN_RATIO;
# a missing/unparseable value falls back to this default rather than disabling the guard —
# prefer blocking a legitimate prune over silently wiping the corpus.
_DEFAULT_PRUNE_MIN_RATIO = 0.5


def prune_min_ratio() -> float:
    """The minimum fraction of the prior corpus total the current-version count must
    reach for a prune to be allowed (the single shrink knob, finding M4). Read from
    `ADVENTURE_PRUNE_MIN_RATIO`, falling back SAFE (to the blocking-capable default) on
    unset/garbage — a bad knob must never silently disable this data-safety gate."""
    raw = os.environ.get("ADVENTURE_PRUNE_MIN_RATIO")
    if not raw:
        return _DEFAULT_PRUNE_MIN_RATIO
    try:
        return float(raw)
    except ValueError:
        log.warning(
            "ADVENTURE_PRUNE_MIN_RATIO=%r is not a float — falling back to default %.2f",
            raw,
            _DEFAULT_PRUNE_MIN_RATIO,
        )
        return _DEFAULT_PRUNE_MIN_RATIO


def _scalar_count(rows_or_result: Any, key: str = "n") -> int:
    """Extract a `RETURN count(...) AS n` scalar from whatever shape `runner` returns.

    Production (`ingestion/pipeline.py`) wires `runner = make_runner(session)`, a raw
    `neo4j.Session.run` whose return supports `.single()`. Tests (and the
    `ScopedSession.run` path some integration tests route through) instead pass an
    already-materialized `list[dict]`. Both are handled so this module stays agnostic
    about which Runner flavor it's given, matching every other function here."""
    single = getattr(rows_or_result, "single", None)
    if callable(single):
        record = single()
        return int(record[key]) if record is not None else 0
    if isinstance(rows_or_result, list):
        return int(rows_or_result[0][key]) if rows_or_result else 0
    raise TypeError(f"Unexpected count-query result shape: {type(rows_or_result)!r}")


@dataclass(frozen=True)
class PruneOutcome:
    """What `prune_stale_trails` decided. `pruned=False` means every node was left
    intact — either guard can fire this; `reason` says which and names the counts.
    `protected` counts stale trails that WERE eligible but were kept because a live
    personal Episode still references them (owned-ref safety)."""

    pruned: bool
    n_cur: int
    n_prev: int
    reason: str | None = None
    protected: int = 0


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
    way_type: str | None = _UNSET,
    outside_boundary: bool | None = _UNSET,
    path_grade: str | None = _UNSET,
    psurface: str | None = _UNSET,
    foot_access: str | None = _UNSET,
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
    if way_type is not _UNSET:
        # The OSM way-type (Curator de-rank input). As with route geometry, passing
        # None explicitly SETs null so a re-ingest that drops the type clears a stale
        # value rather than leaving it standing (source-or-silence).
        params["way_type"] = way_type
        set_clauses.append("t.way_type = $way_type")
    if outside_boundary is not _UNSET:
        # Phase-2 spatial signal: True when the trail's point falls OUTSIDE the
        # region's protected-area boundary (Curator soft-demote input — see
        # `is_outside_boundary_demoted`). None means "no boundary / unknown"; as with
        # way_type, passing it explicitly SETs null so a re-ingest without a boundary
        # clears a stale flag rather than leaving it standing (source-or-silence).
        params["outside_boundary"] = outside_boundary
        set_clauses.append("t.outside_boundary = $outside_boundary")
    if path_grade is not _UNSET:
        # Classified difficulty (Epic 026). As with way_type, an explicit None SETs
        # null so a re-ingest that loses the source tag clears a stale grade rather
        # than leaving it standing (source-or-silence).
        params["path_grade"] = path_grade
        set_clauses.append("t.path_grade = $path_grade")
    if psurface is not _UNSET:
        params["psurface"] = psurface
        set_clauses.append("t.psurface = $psurface")
    if foot_access is not _UNSET:
        params["foot_access"] = foot_access
        set_clauses.append("t.foot_access = $foot_access")
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


# Same-region membership predicate (separator-anchored prefix). A node belongs to
# region `$region_id` when its `ingest_version` IS the bare region id or starts with
# `"{region_id}-"`. The anchor matters — a bare `STARTS WITH region_id` would let region
# "shen" match region "shenandoah-gwj" (a silent cross-region wipe) — so the prefix must
# end on the `-` boundary. Used version-independently by `count_region_trails` (the
# pre-load corpus snapshot) …
_REGION_PRED = "(node.ingest_version = $region_id OR node.ingest_version STARTS WITH $prefix)"

# … and, with the current-version exclusion, as the stale-candidate predicate shared by
# `count_region_versions` and `prune_stale_trails` so the candidate set the guards count
# is EXACTLY the set the delete passes act on.
_REGION_VERSION_PRED = f"{_REGION_PRED}\n  AND node.ingest_version <> $iv"

# A stale world CanonicalTrail with a LIVE incoming owned edge — a personal
# `(:Episode)-[:ON]->(t)` reference — must NEVER be DETACH-DELETEd: severing it is
# the personal→world dangling-ref that produced the viewer-path 500. Prune skips such
# nodes (and logs the count). Episode-[:ON] is the only owned→world edge into a
# CanonicalTrail in the schema; if another is ever added, widen this predicate.
#
# `_OWNED_TRAIL_REF_RELS` is the authoritative manifest of (owned-label, rel-type) pairs
# that `_OWNED_REF_PRED` protects. A schema-drift guard test (test_load.py) fails if a
# query builder ever creates an owned→CanonicalTrail edge NOT in this set — so a future
# saved/bookmarked-trail feature (e.g. Belief-[:ABOUT]->CanonicalTrail) can't silently
# reopen the viewer-500 class without also widening the predicate here.
_OWNED_TRAIL_REF_RELS: frozenset[tuple[str, str]] = frozenset({("Episode", "ON")})
_OWNED_REF_PRED = "(node)<-[:ON]-(:Episode)"


def _region_version_params(
    ingest_version: str, region_id: str, min_current: int = 1
) -> dict[str, Any]:
    return {
        "iv": ingest_version,
        "region_id": region_id,
        "prefix": f"{region_id}-",
        "min_current": min_current,
    }


def count_region_versions(
    runner: Runner, ingest_version: str, *, region_id: str
) -> tuple[int, int]:
    """`(n_cur, n_prev)`: this region's current-`ingest_version` CanonicalTrail count,
    and its prior-version (stale-candidate) count. The two numbers the prune guards —
    and the pre-prune verify gate (`ingestion.pipeline.verify_before_prune`) — decide
    on, factored out so both compute them identically from the SAME candidate
    predicate. Read-only; issues no writes."""
    n_cur = _scalar_count(
        runner(
            "MATCH (cur:CanonicalTrail {ingest_version: $iv})\nRETURN count(cur) AS n",
            {"iv": ingest_version},
        )
    )
    n_prev = _scalar_count(
        runner(
            f"MATCH (node:CanonicalTrail)\nWHERE {_REGION_VERSION_PRED}\nRETURN count(node) AS n",
            _region_version_params(ingest_version, region_id),
        )
    )
    return n_cur, n_prev


def count_region_trails(runner: Runner, *, region_id: str) -> int:
    """This region's TOTAL CanonicalTrail count across ALL ingest versions — the
    version-independent corpus size. Called BEFORE a re-ingest's load to snapshot the
    prior corpus total (`pre_load_count`), the correct denominator for the collapse gate
    (the post-load `n_prev` is only the run's MISSED trails — see `prune_min_ratio`).
    Read-only; issues no writes."""
    return _scalar_count(
        runner(
            f"MATCH (node:CanonicalTrail)\nWHERE {_REGION_PRED}\nRETURN count(node) AS n",
            {"region_id": region_id, "prefix": f"{region_id}-"},
        )
    )


def prune_stale_trails(
    runner: Runner,
    ingest_version: str,
    *,
    region_id: str,
    min_current: int = 1,
    min_ratio: float | None = None,
    pre_load_count: int | None = None,
) -> PruneOutcome:
    """Delete CanonicalTrails (+ their Segments and SourceRecords) left behind by a
    PRIOR ingest of this region — the nodes a now-tighter filter stopped refreshing.

    The loaders are MERGE-only (idempotent upsert), so a re-ingest that newly *drops*
    a way — e.g. a TIGER-misimported state route the trail filter now rejects (finding
    #1) — never deletes the node last month's run created. It just stops touching it,
    leaving a stale CanonicalTrail serving forever in /plan. This prunes every
    same-region trail whose `ingest_version` is not the current run's, closing that gap
    so a tighter filter actually self-heals on re-ingest.

    Guard 1 (empty-ingest) — a failed or empty ingest must NEVER wipe the graph (the
    whole point of the prune is to delete *non-current* nodes, which is everything if
    the current run wrote nothing). The delete fires only when at least `min_current`
    trails carry the current `ingest_version`: an ingest that loaded nothing (Overpass
    down, region misconfigured) leaves `n_cur = 0 < min_current`, the in-query WHERE
    drops the only row, and the downstream MATCH/DELETE never runs.

    Guard 2 (ratio, finding M1 + collapse-gate correction) — a *truncated* ingest is a
    different failure mode: it loads a nonzero-but-tiny count (e.g. Overpass times out
    mid-fetch and returns 750 of ~1500 trails), which sails past guard 1 (n_cur=750 >=
    min_current=1) and would then prune the ~750 stragglers as "stale" — a silent corpus
    wipe, not a loud failure. Before either DELETE pass runs, this aborts the WHOLE prune
    in Python — no query even fires — if `n_cur` (current-version trails) has collapsed
    below `min_ratio * pre_load_count` (default ratio 0.5, env `ADVENTURE_PRUNE_MIN_RATIO`).

    The denominator is `pre_load_count` — the caller's PRE-load snapshot of the region's
    total CanonicalTrail count (`count_region_trails`) — NOT the post-load `n_prev`. Because
    the loaders MERGE by a version-INDEPENDENT canonical_id, a re-ingest flips each recovered
    trail old→new, so `n_prev` is only the run's MISSED trails and `n_cur`/`n_prev` are
    complementary halves of one total; comparing against `n_prev` lets a 50% partial pass
    (see `prune_min_ratio`). This guard is a belt to the pipeline's primary `verify_before_prune`
    gate; when `pre_load_count` is None (not supplied) it is skipped and only guard 1 + the
    verify gate protect. A healthy re-ingest (comparable counts) is unaffected; `pre_load_count
    == 0` (first-ever ingest of a region) has no denominator and always passes. This is purely
    additive — it can only ABORT a prune guard 1 would have allowed, never permit one guard 1
    would have blocked, and every existing protection still runs unchanged.

    Region-scoped: only nodes whose `ingest_version` IS this region's id or starts with
    `"{region_id}-"` are candidates (`ingest_version` is `"{region_id}"` or
    `"{region_id}-{suffix}"`). The separator anchor matters — a bare `STARTS WITH
    region_id` would let region "shen" prune region "shenandoah", a silent cross-region
    wipe — so the prefix must end on the `-` boundary.

    Two passes, because a SourceRecord is NOT guaranteed 1:1 with its trail (the matcher
    can `SAME_AS` one source feature to several canonicals, and a re-keyed canonical_id
    leaves the old `SAME_AS` standing). Pass 1 deletes the stale trails and their
    trail-private Segments (the id embeds the canonical_id) — DETACH drops their
    `SAME_AS` edges. Pass 2 then deletes only the SourceRecords that are now *orphaned*
    (no surviving `SAME_AS` to any CanonicalTrail) AND stale-versioned in this region —
    so a SourceRecord still corroborating a surviving current-version trail is kept
    (rule #1 source-or-silence / rule #7 provenance).

    Owned-ref safety — pass 1 additionally SKIPS any stale trail a live personal
    `(:Episode)-[:ON]->(t)` still references. DETACH-deleting such a node would sever a
    personal→world reference (the viewer-path 500). Skipped nodes are counted into
    `PruneOutcome.protected` and logged; they simply wait for a future re-ingest to
    refresh (and thus retire) them, rather than being wiped out from under an Episode."""
    guard = (
        "MATCH (cur:CanonicalTrail {ingest_version: $iv})\n"
        "WITH count(cur) AS n_cur\n"
        "WHERE n_cur >= $min_current\n"
    )
    region_pred = _REGION_VERSION_PRED
    params = _region_version_params(ingest_version, region_id, min_current)

    n_cur, n_prev = count_region_versions(runner, ingest_version, region_id=region_id)

    if n_cur < min_current:
        reason = (
            f"prune skipped: region {region_id!r} current-version count {n_cur} "
            f"below min_current {min_current} (leaving all {n_prev} stale-candidate "
            "trail(s) intact)"
        )
        log.warning(reason)
        return PruneOutcome(pruned=False, n_cur=n_cur, n_prev=n_prev, reason=reason)

    ratio = prune_min_ratio() if min_ratio is None else min_ratio
    if pre_load_count is not None and pre_load_count > 0 and n_cur < ratio * pre_load_count:
        reason = (
            f"prune skipped: region {region_id!r} current-version count {n_cur} is below "
            f"{ratio:.0%} of the prior corpus total {pre_load_count} "
            f"(ratio {n_cur / pre_load_count:.3f} below min_ratio {ratio:.3f}) — looks like "
            "a truncated ingest; leaving all nodes intact"
        )
        log.warning(reason)
        return PruneOutcome(pruned=False, n_cur=n_cur, n_prev=n_prev, reason=reason)

    # Owned-ref safety (2c): count the stale trails a live Episode still references so
    # the skip is visible, then EXCLUDE them from the delete (never sever a personal ref).
    protected = _scalar_count(
        runner(
            f"MATCH (node:CanonicalTrail)\nWHERE {region_pred}\n"
            f"  AND {_OWNED_REF_PRED}\nRETURN count(node) AS n",
            dict(params),
        )
    )
    if protected:
        log.info(
            "prune: keeping %d stale trail(s) in region %r that a live Episode still "
            "references (owned-ref safety — they retire on a future re-ingest)",
            protected,
            region_id,
        )

    # Pass 1 — stale trails + their private segments, EXCEPT owned-referenced ones.
    runner(
        guard
        + "MATCH (node:CanonicalTrail)\n"
        + f"WHERE {region_pred}\n"
        + f"  AND NOT {_OWNED_REF_PRED}\n"
        + "OPTIONAL MATCH (node)-[:HAS_SEGMENT]->(s:Segment)\n"
        + "DETACH DELETE node, s",
        params,
    )
    # Pass 2 — SourceRecords now orphaned by pass 1 (still-referenced ones survive).
    runner(
        guard
        + "MATCH (node:SourceRecord)\n"
        + f"WHERE {region_pred}\n"
        + "  AND NOT (node)-[:SAME_AS]->(:CanonicalTrail)\n"
        + "DETACH DELETE node",
        params,
    )
    return PruneOutcome(pruned=True, n_cur=n_cur, n_prev=n_prev, protected=protected)


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
