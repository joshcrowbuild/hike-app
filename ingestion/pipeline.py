"""Stage-3 ingestion pipeline — fetch → transform → hygiene → conflate → load.

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
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from shapely.ops import unary_union

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


# ── Feature normalisation (thin shim over ingestion.transform) ─────────────────


def _safe_geom_centroid(feature: Feature) -> tuple[float, float]:
    c = feature.geom.centroid
    return (c.y, c.x)  # (lat, lon)


def _build_canonical_id(source: str, ref: str | None, name: str) -> str:
    if ref:
        clean_ref = ref.replace("/", "_").replace(" ", "-").lower()
        return f"ct:{source.lower()}:{clean_ref}"
    slug = name.lower().replace(" ", "-").replace("/", "-")
    if len(slug) > 40:
        # Hash suffix prevents collision when two names share a long common prefix.
        import hashlib

        suffix = hashlib.sha1(slug.encode()).hexdigest()[:6]
        slug = f"{slug[:33]}-{suffix}"
    return f"ct:{source.lower()}:{slug}"


def _sr_uid(source: str, ref: str | None, name: str) -> str:
    if ref:
        return f"{source}:{ref}"
    key = name.replace(" ", "_").lower()
    if len(key) > 30:
        import hashlib

        suffix = hashlib.sha1(key.encode()).hexdigest()[:6]
        key = f"{key[:23]}_{suffix}"
    return f"{source}:{key}"


# ── OSM consolidation ─────────────────────────────────────────────────────────


def consolidate_osm_segments(features: list[Feature]) -> list[Feature]:
    """Merge OSM way segments that share a normalized name into one Feature.

    OSM encodes a continuous trail as many disconnected `way` elements. Running
    conflation against individual 200m segments produces artificially low geometry
    overlap against full-length NPS/USFS records (score=100, overlap=0.02). Merging
    first gives the matcher the full trail geometry and turns most of those "review"
    cases into auto-accepts.

    Groups solely by normalized name within the fetched bbox — geographic separation
    (two parks with "Ridge Trail") is acceptable at pilot scale; add spatial clustering
    later if cross-park false-merges become a problem.
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

    consolidated: list[Feature] = []
    for _, group in by_norm.items():
        if len(group) == 1:
            consolidated.append(group[0])
            continue
        # Prefer the longest raw name as the display name; merge all geometries.
        name = max(group, key=lambda f: len(f.name)).name
        combined = unary_union([f.geom for f in group])
        # ref=None: a merge spans multiple source way IDs. `source` carries the group's
        # real provenance (not a hardcoded "OSM") so a non-OSM spine keeps its authority
        # tier and SourceRecord/SAME_AS provenance (C5 / AC-4.3).
        consolidated.append(Feature(name=name, geom=combined, source=group[0].source, ref=None))

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
    return facts


# ── Load ──────────────────────────────────────────────────────────────────────


def _persist_segments(runner: Any, canonical_id: str, assembled: Any, iv: str) -> None:
    """Persist one `Segment` per assembled-route part + its `HAS_SEGMENT` link (Epic
    016 S1). Call *after* the CanonicalTrail exists so the link's MATCH resolves;
    `assembled` is the already-assembled route geometry (assembled once at the call
    site and reused for the stored `route_geom_wkt`)."""
    from graph.load import load_segment

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
) -> dict[str, int]:
    """Persist auto-accept matches + unmatched spine features via the idempotent
    MERGE loaders. The spine side is read generically from the `Feature.source`
    (no literal "OSM" special-case); each SourceRecord carries the per-source
    `authority_tier` floor read from the source object (AC-4.3), recorded via the
    loader's `extra` slot — best-view per-attribute overrides stay in the
    best-view layer."""
    from graph.load import load_canonical_trail, load_source_record, merge_same_as

    # `load_segment` is imported lazily inside `_persist_segments` (same module).

    def _tier_extra(source: str) -> dict[str, Any] | None:
        tier = tier_by_name.get(source.lower())
        return {"authority_tier": tier} if tier is not None else None

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
            ingest_version=iv,
        )
        if assembled is not None:
            _persist_segments(runner, canonical_id, assembled, iv)
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
            ingest_version=iv,
        )
        if assembled is not None:
            _persist_segments(runner, canonical_id, assembled, iv)
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
    settings = settings or Settings.from_env()
    active = registry.enabled_sources(settings, names=sources)
    geometry_sources = [s for s in active if s.kind is SourceKind.geometry]
    enrichment_sources = [s for s in active if s.kind is SourceKind.enrichment]
    spine_source = registry.spine(geometry_sources)

    counts: dict[str, int] = {"auto_accept": 0, "review": 0, "loaded": 0, "skipped_hygiene": 0}

    # ── Fetch spine + conflate each non-spine geometry source onto it ───────────
    log.info("Fetching %s trails (spine) …", spine_source.name)
    raw_spine = spine_source.fetch(region)
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
        from graph.load import load_enrichment_facts, make_runner
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
            load_counts = _load_matches(
                runner, auto_accept, spine_features, tier_by_name=tier_by_name, iv=iv
            )
            counts["loaded"] = load_counts["loaded"]
            counts["skipped_hygiene"] = load_counts["skipped_hygiene"]
            # ── Enrichment join point (post-conflation): collect facts, then persist
            # them through the enrichment loader (Epic 017 S1). No-op without
            # enrichment sources; a failing source degrades inside _run_enrichment.
            facts = _run_enrichment(enrichment_sources, canonical_nodes)
            counts["enrichment_facts"] = load_enrichment_facts(runner, facts)
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
