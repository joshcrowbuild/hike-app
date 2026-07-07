"""Stage-3 ingestion pipeline — fetch → conflate → load.

CLI entry:
    python -m ingestion.pipeline --region shenandoah-gwj [--dry-run] [--source <name> …]

Reads the region polygon from regions/{region}.geojson, then iterates the
config-driven `CorpusSource` registry (ingestion/sources/registry.py) — it names
no source literally. The one source declaring `role=spine` is conflated against
each `role=conflate` geometry source; enrichment sources join post-conflation.
Which sources run is ADVENTURE_CORPUS_SOURCES; the spine is whichever source
declares it (Epic 012 / source-seams §6).

Idempotent: all Neo4j writes use MERGE. Safe to re-run monthly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from ingestion.boundary import classify_outside_boundary, load_region_boundary
from ingestion.conflate.match import Feature, Match, Thresholds, match, normalize_name
from ingestion.route import assemble_geometry, line_parts
from ingestion.sources import registry
from ingestion.sources.base import (
    CanonicalNode,
    ConflationRole,
    CorpusSource,
    EnrichmentFact,
    Region,
    SourceKind,
)
from orchestration.config import Settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


# ── Region config ─────────────────────────────────────────────────────────────


def load_region(region_id: str) -> Region:
    # AM4: region_id comes straight from --region (CLI arg); reject anything that could
    # escape regions/ before it's ever used to build a path (e.g. "../secrets").
    if "/" in region_id or "\\" in region_id or ".." in region_id:
        log.error("Invalid region id %r: must not contain '/', '\\\\', or '..'", region_id)
        sys.exit(1)
    path = Path(f"regions/{region_id}.geojson")
    if not path.exists():
        log.error("Region file not found: %s", path)
        sys.exit(1)
    with path.open() as f:
        feat = json.load(f)
    props = feat.get("properties", {})
    bbox_raw = props.get("bbox")
    if not bbox_raw or len(bbox_raw) != 4:
        log.error("Region %s is missing a valid bbox [west,south,east,north]", region_id)
        sys.exit(1)
    west, south, east, north = bbox_raw
    return Region(region_id=region_id, bbox=(south, west, north, east), props=props)


# ── Feature normalisation ──────────────────────────────────────────────────────


def _safe_geom_centroid(feature: Feature) -> tuple[float, float]:
    c = feature.geom.centroid
    return (c.y, c.x)  # (lat, lon)


def _build_canonical_id(source: str, ref: str | None, name: str) -> str:
    if ref:
        clean_ref = ref.replace("/", "_").replace(" ", "-").lower()
        return f"ct:{source.lower()}:{clean_ref}"
    # Two distinct names can slugify to the same string (e.g. "Blue/Ridge Trail"
    # and "Blue Ridge Trail" both -> "blue-ridge-trail"), so the hash suffix must
    # apply unconditionally, not just past some length threshold (mode (a) —
    # short-slug collision). It must hash the full original `name`, not the lossy
    # `slug`: hashing the slug would give identically-slugified names the same
    # suffix and fix nothing. The retained prefix is lengthened from 33 to 50
    # chars so two names sharing a long common prefix (mode (b) — long
    # shared-prefix truncation) stay human-distinguishable in the readable part.
    slug = name.lower().replace(" ", "-").replace("/", "-")
    suffix = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
    slug = f"{slug[:50]}-{suffix}"
    return f"ct:{source.lower()}:{slug}"


def _sr_uid(source: str, ref: str | None, name: str) -> str:
    if ref:
        return f"{source}:{ref}"
    key = name.replace(" ", "_").lower()
    if len(key) > 30:
        suffix = hashlib.sha1(key.encode()).hexdigest()[:6]
        key = f"{key[:23]}_{suffix}"
    return f"{source}:{key}"


# ── OSM consolidation ─────────────────────────────────────────────────────────


# Two OSM ways whose geometries come within this distance are treated as one
# connected trail. ~40 m bridges typical OSM way-endpoint snapping/rounding without
# merging genuinely-separate trails (the 300–800 m gaps the name-only merge produced).
_SEGMENT_GAP_M = 40.0
# Inverse of the match.py lat/lon average metres-per-degree at ~38°N (≈98 000 m/deg).
_DEG_PER_M = 1.0 / 98_000.0


def _dominant_way_type(features: list[Feature]) -> str | None:
    """The most common non-None `way_type` across a merged component (ties → first
    seen). Same-named connected OSM ways almost always share a highway value, so this
    is just a robust pick when a stray segment differs."""
    counts: dict[str, int] = defaultdict(int)
    order: list[str] = []
    for f in features:
        if f.way_type:
            if f.way_type not in counts:
                order.append(f.way_type)
            counts[f.way_type] += 1
    if not counts:
        return None
    return max(order, key=lambda wt: counts[wt])


def _connected_components(features: list[Feature], gap_deg: float) -> list[list[Feature]]:
    """Cluster features into spatially-connected components (union-find): two ways join
    when their geometries are within `gap_deg` of each other. O(n²) in the group size —
    fine, since same-name groups are small."""
    n = len(features)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            if find(i) != find(j) and features[i].geom.distance(features[j].geom) <= gap_deg:
                parent[find(i)] = find(j)

    comps: dict[int, list[Feature]] = defaultdict(list)
    for i in range(n):
        comps[find(i)].append(features[i])
    return list(comps.values())


def consolidate_osm_segments(
    features: list[Feature], *, gap_m: float = _SEGMENT_GAP_M
) -> list[Feature]:
    """Merge OSM way segments that share a name AND are spatially connected into one
    Feature; split same-named-but-disconnected ways into separate trails.

    OSM encodes a continuous trail as many disconnected `way` elements. Merging gives
    the conflation matcher the full trail geometry (a 200 m segment overlaps a
    full-length NPS record at ~0.02; merged it auto-accepts). But merging *solely* by
    name unioned genuinely-distinct ways that happen to share a name (two parks'
    "Ridge Trail"; the many "Rivanna Trail" / "Appalachian Trail" sections) into one
    gappy MultiLineString — the "map routes are nonsense" (Lead 2). Clustering each
    name-group by spatial connectivity keeps real contiguous trails merged (clean
    LineString) while disconnected ways become their own CanonicalTrails.
    """
    by_norm: dict[str, list[Feature]] = defaultdict(list)
    dropped = 0
    for feat in features:
        key = normalize_name(feat.name)
        if key:
            by_norm[key].append(feat)
        else:
            dropped += 1  # name was suffix-only (e.g. "Trail") — no useful key
    if dropped:
        log.warning("consolidate_osm_segments: dropped %d suffix-only named features", dropped)

    gap_deg = gap_m * _DEG_PER_M
    consolidated: list[Feature] = []
    split_groups = 0
    for _, group in by_norm.items():
        if len(group) == 1:
            consolidated.append(group[0])
            continue
        components = _connected_components(group, gap_deg)
        if len(components) > 1:
            split_groups += 1
        for comp in components:
            if len(comp) == 1:
                consolidated.append(comp[0])
                continue
            # Prefer the longest raw name as the display name; merge the component.
            name = max(comp, key=lambda f: len(f.name)).name
            combined = unary_union([f.geom for f in comp])
            # Stable, unique ref per component (the min member way id) so each connected
            # component is its OWN CanonicalTrail — no slug collision between disconnected
            # same-named ways, and the id is stable across re-ingests.
            ref = min((f.ref for f in comp if f.ref), default=None)
            # Carry the way-type: same-named connected ways almost always share it, so
            # take the most common (ties → first seen) as the component's type.
            way_type = _dominant_way_type(comp)
            consolidated.append(
                Feature(name=name, geom=combined, source=comp[0].source, ref=ref, way_type=way_type)
            )

    if split_groups:
        log.info(
            "consolidate_osm_segments: split %d same-name group(s) into disconnected components",
            split_groups,
        )
    return consolidated


# ── Canonical-node derivation + enrichment join point ─────────────────────────


def _assembled_route_wkt(geom: Any) -> str | None:
    """The trail's full route assembled from its (segment) geometry, as WKT — the
    one artifact both Epic 016 (the served `geometry`) and Epic 017 (the elevation
    sample-line) consume, so geometry is assembled once. `None` when no line."""
    assembled = assemble_geometry(geom)
    return assembled.wkt if assembled is not None else None


def _canonical_nodes(
    auto_accept: list[Match], spine_features: list[Feature]
) -> list[CanonicalNode]:
    """The canonical trails the load loop would create — derived read-only so the
    enrichment step can run over them in both dry-run and live paths. Mirrors the
    load loop's selection (auto-accept spine side + unmatched named spine features)
    so enrichment joins exactly the nodes that get persisted (SS-4). Each node
    carries its assembled route `geom_wkt` so a geometry-consuming enrichment source
    (3DEP) samples the same line the API serves (Epic 017)."""
    nodes: list[CanonicalNode] = []
    matched: set[str] = set()
    for m in auto_accept:
        cid = _build_canonical_id(m.a.source, m.a.ref, m.a.name)
        lat, lon = _safe_geom_centroid(m.a)
        nodes.append(
            CanonicalNode(
                canonical_id=cid,
                name=m.a.name,
                lat=lat,
                lon=lon,
                geom_wkt=_assembled_route_wkt(m.a.geom),
                way_type=m.a.way_type,
            )
        )
        matched.add(m.a.ref or m.a.name)
    for feat in spine_features:
        if (feat.ref or feat.name) in matched or not feat.name:
            continue
        cid = _build_canonical_id(feat.source, feat.ref, feat.name)
        lat, lon = _safe_geom_centroid(feat)
        nodes.append(
            CanonicalNode(
                canonical_id=cid,
                name=feat.name,
                lat=lat,
                lon=lon,
                geom_wkt=_assembled_route_wkt(feat.geom),
                way_type=feat.way_type,
            )
        )
    return nodes


def _run_enrichment(
    enrichment_sources: list[CorpusSource], canonical_nodes: list[CanonicalNode]
) -> list[EnrichmentFact]:
    """The post-conflation join point Stage 3 §7 promised (AC-5.2). Enrichment
    sources join onto already-canonical nodes and NEVER enter the matcher. With
    zero enrichment sources (the default config) this is a no-op. Collected facts
    are persisted by `load_enrichment_facts` in the live path (Epic 017 S1).

    Degrade-and-disclose (rule #6 / Epic 017 AC-1.2): a source that raises on a node
    contributes "no fact" for it (logged) and the run continues — one failing source
    or node never aborts enrichment for the rest."""
    facts: list[EnrichmentFact] = []
    for s in enrichment_sources:
        for node in canonical_nodes:
            try:
                facts.extend(s.enrich(node))
            except Exception as exc:
                log.warning(
                    "Enrichment source %s failed on %s, degrading to no fact: %s",
                    getattr(s, "name", s),
                    node.canonical_id,
                    exc,
                )
    if facts:
        log.info(
            "Enrichment: %d facts from %d source(s) over %d canonical nodes",
            len(facts),
            len(enrichment_sources),
            len(canonical_nodes),
        )
    _log_elevation_coverage(enrichment_sources, facts, len(canonical_nodes))
    return facts


# Elevation attributes carry this marker (the always-emitted scalar) so we can count
# how many nodes actually received a profile this run — distinct from the raw fact count.
_ELEV_MARKER_ATTR = "total_gain_m"


def _log_elevation_coverage(
    enrichment_sources: list[CorpusSource], facts: list[EnrichmentFact], n_nodes: int
) -> None:
    """Make elevation lag VISIBLE at ingest time (Epic 017 durability). Logs how many
    of the run's canonical nodes got a 3DEP profile; a WARNING when 3DEP is active but
    zero nodes were covered (a lost/missing DEM, the exact "elevation went null"
    failure) so it can't pass silently. A no-op when no 3DEP source is configured."""
    has_3dep = any(getattr(s, "name", "") == "usgs-3dep" for s in enrichment_sources)
    if not has_3dep or n_nodes == 0:
        return
    covered = len({f.canonical_id for f in facts if f.attribute == _ELEV_MARKER_ATTR})
    pct = covered / n_nodes * 100
    if covered == 0:
        log.warning(
            "Elevation: 0/%d trails got a 3DEP profile this run — DEM missing or "
            "empty? (existing elevation, if any, is left untouched; run "
            "scripts/fetch_dem.py to obtain the region DEM)",
            n_nodes,
        )
    else:
        log.info("Elevation: %d/%d trails (%.0f%%) carry a 3DEP profile", covered, n_nodes, pct)


# ── Fetch sanity + pre-prune verify gate (data-safety foundation) ─────────────


class FetchSanityError(RuntimeError):
    """A source returned suspiciously few features — a truncated/partial fetch (an
    Overpass timeout that returns 1 of ~1500 ways looks valid and is MORE dangerous
    than an empty one, because a downstream prune would read it as healthy and wipe
    the rest). Raised BEFORE any load/prune so a partial fetch aborts this region's
    ingest with nothing written, never a half-load that later self-wipes."""


class IngestVerificationError(RuntimeError):
    """A loaded region failed a pre-prune safety check (collapse or elevation). The
    caller MUST NOT prune — the last-good corpus stays intact and the new nodes coexist
    additively — and this propagates so the run exits nonzero (a bad run is visible,
    never a silent half-wipe)."""


_DEFAULT_MIN_ELEV_COVERAGE = 0.8


def _env_float(name: str, default: float) -> float:
    """Read a float env override, falling back SAFE (to `default`) on unset/garbage —
    a bad knob must never silently disable a data-safety gate."""
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        log.warning("%s=%r is not a float — using default %.2f", name, raw, default)
        return default


def _fetch_floor(source_name: str, region: Region) -> int | None:
    """The minimum feature count `source_name` must fetch for `region` before the run
    is allowed to proceed, or None if unconfigured (no check). An env override
    `ADVENTURE_FETCH_MIN_<SOURCE>` wins; otherwise the region file's
    `min_fetch_counts` map. Per-region-per-source so a floor sized for a dense region
    can't false-trip a sparse one."""
    key = f"ADVENTURE_FETCH_MIN_{source_name.upper().replace('-', '_')}"
    raw = os.environ.get(key)
    if raw:
        try:
            return int(raw)
        except ValueError:
            log.warning("%s=%r is not an int — ignoring env floor for %s", key, raw, source_name)
    floors = region.props.get("min_fetch_counts") or {}
    val = floors.get(source_name)
    return int(val) if val is not None else None


def _check_fetch_sanity(source_name: str, count: int, region: Region) -> None:
    """Abort (raise `FetchSanityError`) when a source fetched fewer than its configured
    floor — a truncated/partial fetch. A no-op when no floor is configured."""
    floor = _fetch_floor(source_name, region)
    if floor is not None and count < floor:
        raise FetchSanityError(
            f"{source_name} fetched {count} feature(s) for region {region.region_id!r}, "
            f"below the configured floor of {floor} — looks like a truncated/partial "
            "fetch. Aborting before any load/prune so a partial run can't self-wipe."
        )


def _elevation_expected(enrichment_sources: list[CorpusSource], settings: Settings) -> bool:
    """True only when elevation enrichment is BOTH configured AND resolvable this run:
    the 3DEP source is active and a DEM was resolved for the ingest region. Only then is
    0% coverage a failure (verify aborts) rather than an expected no-op — a DEM-less
    region degrades silently by design (rule #6), so it must NOT trip the gate."""
    from ingestion.sources.usgs_3dep import ELEV_SOURCE

    return bool(settings.dem_path) and any(
        getattr(s, "name", "") == ELEV_SOURCE for s in enrichment_sources
    )


def verify_before_prune(
    region: Region,
    counts: dict[str, int],
    runner: Any,
    *,
    iv: str,
    elevation_expected: bool,
    pre_load_count: int,
) -> tuple[int, int]:
    """The gate that MUST pass before `prune_stale_trails` runs — positioned between the
    load and the prune (post-run is too late: prune already committed). Raises
    `IngestVerificationError` on failure so the caller skips the prune (leaving the
    last-good corpus intact) and the run surfaces loudly. Returns `(n_cur, n_prev)`.

    (a) COLLAPSE — relative and scale-safe: the region's current-version trail count
        must be at least `min_ratio` of its PRIOR CORPUS TOTAL (`pre_load_count`, the
        snapshot taken BEFORE this run's load — default ratio 0.5, the single knob
        `ADVENTURE_PRUNE_MIN_RATIO`). The denominator is the pre-load total, NOT the
        post-load `n_prev`: the loaders MERGE by a version-independent id, so a re-ingest
        flips each recovered trail old→new and `n_prev` is only the run's MISSED trails —
        `n_cur`/`n_prev` are complementary halves of one total, and a 50% partial
        (n_cur == n_prev) would wrongly pass an `n_prev`-based check while pruning the
        stragglers (a silent half-wipe). Comparing against `pre_load_count` is
        scale-correct and turns a truncated re-ingest into a loud abort. `pre_load_count
        == 0` (first-ever ingest) has no denominator and passes.
    (b) ELEVATION — only when `elevation_expected`: coverage (nodes that got a 3DEP
        profile / the geometry-bearing canonical nodes that are ELIGIBLE for one) must be
        ≥ threshold (default 0.8, env `ADVENTURE_ELEV_MIN_COVERAGE`). This promotes today's
        silent "0% elevation" warning — the exact lost/empty-DEM failure — into an abort.
    """
    from graph.load import count_region_versions, prune_min_ratio

    n_cur, n_prev = count_region_versions(runner, iv, region_id=region.region_id)
    counts["verify_n_cur"] = n_cur
    counts["verify_n_prev"] = n_prev
    counts["verify_pre_load"] = pre_load_count

    ratio = prune_min_ratio()
    if pre_load_count > 0 and n_cur < pre_load_count * ratio:
        raise IngestVerificationError(
            f"ingest verify FAILED for region {region.region_id!r}: current-version trail "
            f"count {n_cur} collapsed below {ratio:.0%} of the prior corpus total "
            f"{pre_load_count}. Skipping prune to protect the last-good corpus — the new "
            "nodes coexist additively. Fix the ingest, or lower ADVENTURE_PRUNE_MIN_RATIO "
            "if the shrink is intentional."
        )

    if elevation_expected:
        nodes = counts.get("elev_nodes", 0)
        covered = counts.get("elev_covered", 0)
        min_cov = _env_float("ADVENTURE_ELEV_MIN_COVERAGE", _DEFAULT_MIN_ELEV_COVERAGE)
        coverage = (covered / nodes) if nodes else 0.0
        if nodes and coverage < min_cov:
            raise IngestVerificationError(
                f"ingest verify FAILED for region {region.region_id!r}: elevation coverage "
                f"{covered}/{nodes} ({coverage:.0%}) is below the required {min_cov:.0%} while "
                "3DEP was active with a resolved DEM — a lost or empty DEM. Skipping prune; fix "
                "the DEM (scripts/fetch_dem.py) or lower ADVENTURE_ELEV_MIN_COVERAGE."
            )

    return n_cur, n_prev


# ── Load ──────────────────────────────────────────────────────────────────────


def _replace_segments(runner: Any, canonical_id: str, assembled: Any, iv: str) -> None:
    """Re-persist the trail's `Segment`s idempotently (Epic 016 S1): clear any prior
    segments first (so a re-ingest with fewer/no route parts can't orphan stale ones
    — see `clear_trail_segments`), then persist one `Segment` per assembled-route
    part + its `HAS_SEGMENT` link. Call *after* the CanonicalTrail exists so the
    link's MATCH resolves. `assembled` is the already-assembled route geometry (or
    None when the trail has no line — then segments are only cleared, not added)."""
    from graph.load import clear_trail_segments, load_segment

    clear_trail_segments(runner, canonical_id)
    if assembled is None:
        return
    for i, part in enumerate(line_parts(assembled)):
        centroid = part.centroid
        load_segment(
            runner,
            f"seg:{canonical_id}:{i}",
            part.wkt,
            canonical_id=canonical_id,
            lat=centroid.y,
            lon=centroid.x,
            ingest_version=iv,
        )


def _load_matches(
    runner: Any,
    auto_accept: list[Match],
    spine_features: list[Feature],
    *,
    tier_by_name: dict[str, int],
    iv: str,
    boundary: BaseGeometry | None = None,
) -> dict[str, int]:
    """Persist auto-accept matches + unmatched spine features via the idempotent
    MERGE loaders. The spine side is read generically from the `Feature.source`
    (no literal "OSM" special-case); each SourceRecord carries the per-source
    `authority_tier` floor read from the source object (AC-4.3), recorded via the
    loader's `extra` slot — best-view per-attribute overrides stay in the
    best-view layer.

    `boundary` is the region's protected-area polygon (Phase 2). Each trail's point
    is classified inside/outside it and persisted as `outside_boundary` for the
    Curator's soft-demote. `None` (no real boundary) → the flag is `None` and nothing
    is demoted — the spatial signal degrades to today's name-only filter."""
    from graph.load import load_canonical_trail, load_source_record, merge_same_as

    # `load_segment` is imported lazily inside `_persist_segments` (same module).

    def _tier_extra(source: str) -> dict[str, Any] | None:
        tier = tier_by_name.get(source.lower())
        return {"authority_tier": tier} if tier is not None else None

    # CDP-14 flag-on-ambiguous merge (S5): after the S1/S2 fix, two *distinct*
    # names always get distinct canonical_ids, so a repeat (canonical_id, source)
    # within this run means two ref-less same-source features share a
    # byte-identical name — the only same-source fusion the fix can't
    # distinguish. Cross-source SAME_AS (osm+nps on one trail) keys to two
    # different tuples and never repeats, so it stays silent (degree-guarded).
    # Log-only: never raises, deletes, or overwrites (additive + reversible).
    #
    # A single spine Feature can legitimately appear as `m.a` in >1 auto-accept
    # Match (matched against two different agency sources, e.g. NPS and USFS,
    # by two independent match() calls) — that is corroboration, not ambiguity,
    # so re-seeing the SAME Feature object must not self-trigger. `id(feature)`
    # (not any persisted field) tracks "already considered this exact feature";
    # a genuinely distinct feature that happens to share a name is a different
    # object and still triggers the warning.
    seen_cid_source: set[tuple[str, str]] = set()
    seen_feature_ids: set[int] = set()

    def _flag_if_ambiguous(feature: Feature, canonical_id: str) -> None:
        if id(feature) in seen_feature_ids:
            return
        seen_feature_ids.add(id(feature))
        key = (canonical_id, feature.source)
        if key in seen_cid_source:
            log.warning(
                "Ambiguous same-source merge: canonical_id=%s source=%s name=%r "
                "already loaded this run — two ref-less features share this name.",
                canonical_id,
                feature.source,
                feature.name,
            )
            return
        seen_cid_source.add(key)

    counts = {"loaded": 0, "skipped_hygiene": 0}
    matched_spine_ids: set[str] = set()

    for m in auto_accept:
        canonical_id = _build_canonical_id(m.a.source, m.a.ref, m.a.name)
        lat, lon = _safe_geom_centroid(m.a)
        assembled = assemble_geometry(m.a.geom)
        route_wkt = assembled.wkt if assembled is not None else None
        load_canonical_trail(
            runner,
            canonical_id,
            m.a.name,
            lat=lat,
            lon=lon,
            route_geom_wkt=route_wkt,
            way_type=m.a.way_type,
            outside_boundary=classify_outside_boundary(lat, lon, boundary),
            ingest_version=iv,
        )
        _replace_segments(runner, canonical_id, assembled, iv)
        _flag_if_ambiguous(m.a, canonical_id)
        sr_a = _sr_uid(m.a.source, m.a.ref, m.a.name)
        load_source_record(
            runner,
            sr_a,
            m.a.source,
            source_id=m.a.ref,
            raw_name=m.a.name,
            ingest_version=iv,
            extra=_tier_extra(m.a.source),
        )
        merge_same_as(
            runner,
            canonical_id,
            sr_a,
            source=m.a.source,
            match_method="name+geom",
            match_score=1.0,
            ingest_version=iv,
        )
        _flag_if_ambiguous(m.b, canonical_id)
        sr_b = _sr_uid(m.b.source, m.b.ref, m.b.name)
        load_source_record(
            runner,
            sr_b,
            m.b.source,
            source_id=m.b.ref,
            raw_name=m.b.name,
            ingest_version=iv,
            extra=_tier_extra(m.b.source),
        )
        merge_same_as(
            runner,
            canonical_id,
            sr_b,
            source=m.b.source,
            match_method="name+geom",
            match_score=float(m.name_score) / 100,
            ingest_version=iv,
        )
        matched_spine_ids.add(m.a.ref or m.a.name)
        counts["loaded"] += 1

    # Unmatched spine features (skip only truly incomplete: no name AND no ref).
    for feat in spine_features:
        key = feat.ref or feat.name
        if key in matched_spine_ids:
            continue
        if not feat.name:  # geometry-only, can't conflate or display
            counts["skipped_hygiene"] += 1
            continue
        canonical_id = _build_canonical_id(feat.source, feat.ref, feat.name)
        lat, lon = _safe_geom_centroid(feat)
        assembled = assemble_geometry(feat.geom)
        route_wkt = assembled.wkt if assembled is not None else None
        load_canonical_trail(
            runner,
            canonical_id,
            feat.name,
            lat=lat,
            lon=lon,
            route_geom_wkt=route_wkt,
            way_type=feat.way_type,
            outside_boundary=classify_outside_boundary(lat, lon, boundary),
            ingest_version=iv,
        )
        _replace_segments(runner, canonical_id, assembled, iv)
        _flag_if_ambiguous(feat, canonical_id)
        sr_uid_val = _sr_uid(feat.source, feat.ref, feat.name)
        load_source_record(
            runner,
            sr_uid_val,
            feat.source,
            source_id=feat.ref,
            raw_name=feat.name,
            ingest_version=iv,
            extra=_tier_extra(feat.source),
        )
        merge_same_as(
            runner,
            canonical_id,
            sr_uid_val,
            source=feat.source,
            match_method="name",
            match_score=1.0,
            ingest_version=iv,
        )
        counts["loaded"] += 1

    return counts


# ── Core pipeline ─────────────────────────────────────────────────────────────


def run_pipeline(
    region: Region,
    *,
    sources: list[str] | None = None,
    dry_run: bool = False,
    thresholds: Thresholds | None = Thresholds(),
    settings: Settings | None = None,
) -> dict[str, int]:
    """Fetch, conflate, load. Returns counts dict.

    Iterates the config-driven source registry; `sources` (the CLI `--source`
    override) limits to those names, else ADVENTURE_CORPUS_SOURCES is used. The
    spine is resolved by declared role, so no source is named literally here.
    """
    # Bind settings to the region BEING INGESTED so the registry resolves THIS region's
    # DEM/sources (not the ambient ADVENTURE_REGION — the "Richmond got 0 elevation" bug).
    settings = (settings or Settings.from_env()).for_region(region.region_id)
    active = registry.enabled_sources(settings, names=sources)
    geometry_sources = [s for s in active if s.kind is SourceKind.geometry]
    enrichment_sources = [s for s in active if s.kind is SourceKind.enrichment]
    spine_source = registry.spine(geometry_sources)

    counts: dict[str, int] = {"auto_accept": 0, "review": 0, "loaded": 0, "skipped_hygiene": 0}

    # ── Fetch spine + conflate each non-spine geometry source onto it ───────────
    log.info("Fetching %s trails (spine) …", spine_source.name)
    raw_spine = spine_source.fetch(region)
    _check_fetch_sanity(spine_source.name, len(raw_spine), region)
    counts[spine_source.name] = len(raw_spine)
    spine_features = consolidate_osm_segments(raw_spine)
    counts[f"{spine_source.name}_consolidated"] = len(spine_features)
    log.info(
        "  %s: %d raw → %d after consolidation",
        spine_source.name,
        counts[spine_source.name],
        len(spine_features),
    )

    matches: list[Match] = []
    for s in geometry_sources:
        if s.role is ConflationRole.spine:
            continue
        log.info("Fetching %s trails …", s.name)
        feats = s.fetch(region)
        _check_fetch_sanity(s.name, len(feats), region)
        counts[s.name] = len(feats)
        log.info("  %s: %d features", s.name, len(feats))
        if spine_features and feats:
            pairs = match(spine_features, feats, thresholds=thresholds or Thresholds())
            log.info("Conflation %s×%s: %d matches", spine_source.name, s.name, len(pairs))
            matches.extend(pairs)

    auto_accept = [m for m in matches if m.verdict == "auto-accept"]
    review = [m for m in matches if m.verdict == "review"]
    counts["auto_accept"] = len(auto_accept)
    counts["review"] = len(review)
    log.info("Conflation: %d auto-accept, %d review", len(auto_accept), len(review))
    counts["review_persisted"] = _persist_review_band(
        review, region.region_id, settings.review_band_dir
    )

    canonical_nodes = _canonical_nodes(auto_accept, spine_features)

    # ── Load ────────────────────────────────────────────────────────────────────
    if dry_run:
        log.info("DRY-RUN — skipping Neo4j writes. Would load:")
        _print_dry_run_summary(spine_features, auto_accept, review)
        facts = _run_enrichment(enrichment_sources, canonical_nodes)
        counts["enrichment_facts"] = len(facts)
        return counts

    try:
        from graph.client import GraphClient
        from graph.load import (
            count_region_trails,
            load_enrichment_facts,
            make_runner,
            prune_stale_trails,
        )
    except ImportError as exc:
        log.error("Neo4j not available: %s — run 'pip install -e .[graph]'", exc)
        return counts

    gc = GraphClient(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
    try:
        with gc._ensure_driver().session() as session:
            runner = make_runner(session)
            version_suffix = region.props.get("ingest_version", "")
            iv = f"{region.region_id}-{version_suffix}" if version_suffix else region.region_id
            tier_by_name = {s.name: s.authority_tier for s in geometry_sources}
            # Snapshot the region's prior corpus total BEFORE the load — the collapse
            # gate's correct denominator (post-load counts can't recover it: a MERGE by
            # version-independent id makes n_prev the run's MISSED trails, not the prior
            # total). First-ever ingest → 0 → the gate's no-denominator (passes) path.
            pre_load_count = count_region_trails(runner, region_id=region.region_id)
            counts["pre_load_count"] = pre_load_count
            # Phase-2 spatial signal: the region's protected-area boundary (None when
            # the region ships only a placeholder bbox — the classifier then abstains,
            # so behaviour is never worse than today's name-only filter).
            boundary = load_region_boundary(region.region_id)
            load_counts = _load_matches(
                runner,
                auto_accept,
                spine_features,
                tier_by_name=tier_by_name,
                iv=iv,
                boundary=boundary,
            )
            counts["loaded"] = load_counts["loaded"]
            counts["skipped_hygiene"] = load_counts["skipped_hygiene"]
            # ── Enrichment join point (post-conflation): collect facts, then persist
            # them through the enrichment loader (Epic 017 S1). No-op without
            # enrichment sources; a failing source degrades inside _run_enrichment.
            facts = _run_enrichment(enrichment_sources, canonical_nodes)
            counts["enrichment_facts"] = load_enrichment_facts(runner, facts)
            # Elevation coverage for the verify gate: nodes that actually got a 3DEP
            # profile this run vs. the canonical nodes ELIGIBLE for one — i.e. those with
            # geometry (a point-only trail can never receive a 3DEP profile, so counting it
            # in the denominator would falsely drag coverage below the gate and skip a prune
            # for a perfectly healthy region). Distinct from the raw fact count.
            counts["elev_nodes"] = sum(1 for n in canonical_nodes if n.geom_wkt)
            counts["elev_covered"] = len(
                {f.canonical_id for f in facts if f.attribute == _ELEV_MARKER_ATTR}
            )
            # ── Gate BEFORE prune (positioned between the load and the prune — post-run
            # would be too late, the prune already committed). verify_before_prune checks
            # for a collapsed trail count (scale-safe, supersedes absolute bands) and, when
            # elevation is expected, adequate coverage. On FAIL it RAISES: prune never runs,
            # the last-good corpus stays intact (the new iv nodes coexist additively rather
            # than a half-wipe), and the bad run surfaces loudly (nonzero) instead of
            # silently self-wiping. A tighter filter (e.g. dropping a TIGER-misimported
            # state route) still self-heals: the stale node is pruned only once the gate
            # confirms the run is healthy.
            counts["pruned"] = 0
            verify_before_prune(
                region,
                counts,
                runner,
                iv=iv,
                elevation_expected=_elevation_expected(enrichment_sources, settings),
                pre_load_count=pre_load_count,
            )
            prune_outcome = prune_stale_trails(
                runner, iv, region_id=region.region_id, pre_load_count=pre_load_count
            )
            counts["pruned"] = int(prune_outcome.pruned)
            counts["prune_protected"] = int(prune_outcome.protected)
            if not prune_outcome.pruned:
                log.warning(prune_outcome.reason)
    finally:
        gc.close()

    log.info(
        "Pipeline complete: loaded=%d skipped_hygiene=%d auto_accept=%d review=%d",
        counts["loaded"],
        counts["skipped_hygiene"],
        counts["auto_accept"],
        counts["review"],
    )
    return counts


def _persist_review_band(review: list[Match], region_id: str, out_dir: str) -> int:
    """Write the conflation review band (auto-accept < name_score < no-match, per
    `classify`) to a reviewable `{out_dir}/{region_id}.jsonl` — one line per OSM×agency
    pair the matcher flagged for a human to adjudicate later, NOT a graph node (rule #3:
    fast/derived data never persists as structural graph state). Overwrites the region's
    file each run so it always reflects the latest ingest rather than growing unbounded
    across re-runs of an idempotent pipeline.

    Best-effort: a write failure (e.g. read-only filesystem) is logged and swallowed —
    this is a triage aid, never a pipeline dependency (rule #6's degrade-and-disclose
    spirit)."""
    if not review:
        return 0
    path = Path(out_dir) / f"{region_id}.jsonl"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as f:
            for m in review:
                f.write(
                    json.dumps(
                        {
                            "osm_name": m.a.name,
                            "agency_name": m.b.name,
                            "name_score": m.name_score,
                            "source": m.b.source,
                            "region": region_id,
                        }
                    )
                    + "\n"
                )
    except OSError as exc:
        log.warning("Review-band persistence failed for %s, skipping: %s", region_id, exc)
        return 0
    return len(review)


def _print_dry_run_summary(
    spine_features: list[Feature], auto_accept: list[Match], review: list[Match]
) -> None:
    print(f"\n  Spine features to load: {len(spine_features)}")
    print(f"  Auto-accept matches:  {len(auto_accept)}")
    print(f"  Review matches:       {len(review)}")
    if auto_accept:
        print("\n  Sample auto-accept:")
        for m in auto_accept[:5]:
            print(
                f"    {m.a.source} '{m.a.name}' ← {m.b.source} '{m.b.name}' (score={m.name_score})"
            )
    if review:
        print("\n  Sample review:")
        for m in review[:5]:
            print(
                f"    {m.a.source} '{m.a.name}' ← {m.b.source} '{m.b.name}' (score={m.name_score})"
            )


# ── CLI ───────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Adventure Planner Stage-3 ingestion pipeline")
    parser.add_argument(
        "--region", default="shenandoah-gwj", help="Region ID (matches regions/*.geojson)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Fetch and conflate but don't write to Neo4j"
    )
    parser.add_argument(
        "--source",
        choices=registry.known_source_names(),
        action="append",
        help="Limit to specific sources (default: all enabled in ADVENTURE_CORPUS_SOURCES)",
    )
    args = parser.parse_args()

    region = load_region(args.region)
    log.info("Region: %s, bbox: %s", region.region_id, region.bbox)

    counts = run_pipeline(
        region,
        sources=args.source,
        dry_run=args.dry_run,
    )
    print("\nPipeline results:")
    for k, v in counts.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
