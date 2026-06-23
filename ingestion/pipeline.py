"""Stage-3 ingestion pipeline — fetch → transform → hygiene → conflate → load.

CLI entry:
    python -m ingestion.pipeline --region shenandoah-gwj [--dry-run] [--source osm|nps|usfs]

Reads the region polygon from regions/{region}.geojson, fetches from each active
source, conflates OSM vs agency, then bulk-loads to Neo4j via graph.load.

Sources:
  OSM  — Overpass API (free, keyless, always attempted)
  NPS  — public ArcGIS FeatureServer (free, keyless)
  USFS — local bulk GeoJSON (see ingestion/fetch/usfs.py for download instructions)

Idempotent: all Neo4j writes use MERGE. Safe to re-run monthly.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from ingestion.conflate.match import Feature, Match, Thresholds, match
from ingestion.fetch import nps as nps_fetch
from ingestion.fetch import osm as osm_fetch
from ingestion.fetch import usfs as usfs_fetch

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


# ── Region config ─────────────────────────────────────────────────────────────


def load_region(region_id: str) -> dict[str, Any]:
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
    return {"region_id": region_id, "bbox": (south, west, north, east), "props": props}


# ── Feature normalisation (thin shim over ingestion.transform) ─────────────────


def _safe_geom_centroid(feature: Feature) -> tuple[float, float]:
    c = feature.geom.centroid
    return (c.y, c.x)  # (lat, lon)


def _build_canonical_id(source: str, ref: str | None, name: str) -> str:
    if ref:
        clean_ref = ref.replace("/", "_").replace(" ", "-").lower()
        return f"ct:{source.lower()}:{clean_ref}"
    slug = name.lower().replace(" ", "-").replace("/", "-")[:40]
    return f"ct:{source.lower()}:{slug}"


def _sr_uid(source: str, ref: str | None, name: str) -> str:
    key = ref or name.replace(" ", "_")[:30].lower()
    return f"{source}:{key}"


# ── Core pipeline ─────────────────────────────────────────────────────────────


def run_pipeline(
    region: dict[str, Any],
    *,
    sources: list[str] | None = None,
    dry_run: bool = False,
    thresholds: Thresholds | None = Thresholds(),
) -> dict[str, int]:
    """Fetch, conflate, load. Returns counts dict."""
    bbox: tuple[float, float, float, float] = region["bbox"]
    active_sources = set(sources or ["osm", "nps", "usfs"])
    counts: dict[str, int] = {
        "osm": 0,
        "nps": 0,
        "usfs": 0,
        "auto_accept": 0,
        "review": 0,
        "loaded": 0,
        "skipped_hygiene": 0,
    }

    # ── Fetch ──────────────────────────────────────────────────────────────────
    osm_features: list[Feature] = []
    nps_features: list[Feature] = []
    usfs_features: list[Feature] = []

    if "osm" in active_sources:
        log.info("Fetching OSM trails …")
        osm_features = osm_fetch.fetch(bbox)
        counts["osm"] = len(osm_features)
        log.info("  OSM: %d features", counts["osm"])

    if "nps" in active_sources:
        log.info("Fetching NPS trails …")
        nps_features = nps_fetch.fetch(bbox)
        counts["nps"] = len(nps_features)
        log.info("  NPS: %d features", counts["nps"])

    if "usfs" in active_sources:
        log.info("Fetching USFS trails …")
        usfs_features = usfs_fetch.fetch(bbox)
        counts["usfs"] = len(usfs_features)
        log.info("  USFS: %d features", counts["usfs"])

    # ── Conflate ───────────────────────────────────────────────────────────────
    osm_nps_matches: list[Match] = []
    osm_usfs_matches: list[Match] = []
    if osm_features and nps_features:
        osm_nps_matches = match(osm_features, nps_features, thresholds=thresholds or Thresholds())
        log.info("Conflation OSM×NPS: %d matches", len(osm_nps_matches))
    if osm_features and usfs_features:
        osm_usfs_matches = match(osm_features, usfs_features, thresholds=thresholds or Thresholds())
        log.info("Conflation OSM×USFS: %d matches", len(osm_usfs_matches))

    auto_accept = [m for m in osm_nps_matches + osm_usfs_matches if m.verdict == "auto-accept"]
    review = [m for m in osm_nps_matches + osm_usfs_matches if m.verdict == "review"]
    counts["auto_accept"] = len(auto_accept)
    counts["review"] = len(review)

    log.info("Conflation: %d auto-accept, %d review", len(auto_accept), len(review))

    # ── Load ───────────────────────────────────────────────────────────────────
    if dry_run:
        log.info("DRY-RUN — skipping Neo4j writes. Would load:")
        _print_dry_run_summary(osm_features, auto_accept, review)
        return counts

    try:
        from graph.client import GraphClient
        from graph.load import (
            load_canonical_trail,
            load_source_record,
            make_runner,
            merge_same_as,
        )
        from orchestration.config import Settings
    except ImportError as exc:
        log.error("Neo4j not available: %s — run 'pip install -e .[graph]'", exc)
        return counts

    settings = Settings.from_env()
    gc = GraphClient(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)

    try:
        with gc._ensure_driver().session() as session:
            runner = make_runner(session)
            iv = region["region_id"] + "-" + region.get("props", {}).get("ingest_version", "")

            # Load auto-accept pairs
            matched_osm_ids: set[str] = set()
            for m in auto_accept:
                canonical_id = _build_canonical_id("osm", m.a.ref, m.a.name)
                lat, lon = _safe_geom_centroid(m.a)
                load_canonical_trail(
                    runner, canonical_id, m.a.name, lat=lat, lon=lon, ingest_version=iv
                )
                sr_osm = _sr_uid("OSM", m.a.ref, m.a.name)
                load_source_record(
                    runner, sr_osm, "OSM", source_id=m.a.ref, raw_name=m.a.name, ingest_version=iv
                )
                merge_same_as(
                    runner,
                    canonical_id,
                    sr_osm,
                    source="OSM",
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
                matched_osm_ids.add(m.a.ref or m.a.name)
                counts["loaded"] += 1

            # Load unmatched OSM features (skip only truly incomplete: no name AND no ref)
            for feat in osm_features:
                key = feat.ref or feat.name
                if key in matched_osm_ids:
                    continue
                if not feat.name:  # geometry-only, can't conflate or display
                    counts["skipped_hygiene"] += 1
                    continue
                canonical_id = _build_canonical_id("osm", feat.ref, feat.name)
                lat, lon = _safe_geom_centroid(feat)
                load_canonical_trail(
                    runner, canonical_id, feat.name, lat=lat, lon=lon, ingest_version=iv
                )
                sr_uid_val = _sr_uid("OSM", feat.ref, feat.name)
                load_source_record(
                    runner,
                    sr_uid_val,
                    "OSM",
                    source_id=feat.ref,
                    raw_name=feat.name,
                    ingest_version=iv,
                )
                merge_same_as(
                    runner,
                    canonical_id,
                    sr_uid_val,
                    source="OSM",
                    match_method="name",
                    match_score=1.0,
                    ingest_version=iv,
                )
                counts["loaded"] += 1

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
    osm_features: list[Feature], auto_accept: list[Match], review: list[Match]
) -> None:
    print(f"\n  OSM features to load: {len(osm_features)}")
    print(f"  Auto-accept matches:  {len(auto_accept)}")
    print(f"  Review matches:       {len(review)}")
    if auto_accept:
        print("\n  Sample auto-accept:")
        for m in auto_accept[:5]:
            print(f"    OSM '{m.a.name}' ← {m.b.source} '{m.b.name}' (score={m.name_score})")
    if review:
        print("\n  Sample review:")
        for m in review[:5]:
            print(f"    OSM '{m.a.name}' ← {m.b.source} '{m.b.name}' (score={m.name_score})")


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
        choices=["osm", "nps", "usfs"],
        action="append",
        help="Limit to specific sources (default: all)",
    )
    args = parser.parse_args()

    region = load_region(args.region)
    log.info("Region: %s, bbox: %s", region["region_id"], region["bbox"])

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
