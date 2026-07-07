"""Water-source ingestion — fetch OSM water POIs, load as :WaterSource nodes.

The Epic 035 wiring: its three tested primitives (`fetch_water` →
`load_water_source` → `water_sources_near`) shipped without a runner (the
epic's Does-NOT-include kept the pipeline seam untouched), so nothing created
:WaterSource nodes. This is the standalone per-region runner, mirroring
`ingest_trailheads.py`. Run after the main trail pipeline; safe to re-run
(idempotent MERGE by water_id).

Static POIs only (spring / well / tap / drinking-water fountain): location +
type + seasonality — never a potability claim (rule #1). Slow/structural, so
persisting as world nodes is on the right side of rule #3.

Usage:
    python -m ingestion.ingest_water [--region shenandoah-gwj] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from ingestion.fetch.osm import fetch_water

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


def _load_region_bbox(region_id: str) -> tuple[float, float, float, float]:
    path = Path(f"regions/{region_id}.geojson")
    if not path.exists():
        log.error("Region file not found: %s", path)
        sys.exit(1)
    props = json.loads(path.read_text()).get("properties", {})
    bbox = props.get("bbox")
    if not bbox or len(bbox) != 4:
        log.error("Region %s missing valid bbox [west,south,east,north]", region_id)
        sys.exit(1)
    west, south, east, north = bbox
    return (south, west, north, east)


def ingest_water(region_id: str, *, dry_run: bool = False) -> dict[str, int]:
    bbox = _load_region_bbox(region_id)
    log.info("Fetching OSM water sources for %s …", region_id)
    sources = fetch_water(bbox)
    log.info("Found %d water nodes", len(sources))

    counts = {"fetched": len(sources), "loaded": 0}

    if dry_run:
        log.info("DRY-RUN — would load %d water sources", len(sources))
        for w in sources[:5]:
            log.info("  %s (%s) lat=%.4f lon=%.4f", w.name or "(unnamed)", w.water_type, w.lat, w.lon)
        return counts

    try:
        from graph.client import GraphClient
        from graph.load import load_water_source
        from orchestration.config import Settings
    except ImportError as exc:
        log.error("Neo4j not available: %s", exc)
        return counts

    settings = Settings.from_env()
    gc = GraphClient(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)

    try:
        driver = gc._ensure_driver()
        with driver.session() as session:
            runner = lambda c, p: session.run(c, **p)  # noqa: E731
            for w in sources:
                load_water_source(
                    runner,
                    f"water:osm:{w.osm_id}",
                    water_type=w.water_type,
                    lat=w.lat,
                    lon=w.lon,
                    name=w.name,
                    seasonal=w.seasonal,
                    ingest_version=region_id,
                )
                counts["loaded"] += 1
    finally:
        gc.close()

    log.info("Water ingest complete for %s: %s", region_id, counts)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest OSM water sources for a region")
    parser.add_argument("--region", default="shenandoah-gwj")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    counts = ingest_water(args.region, dry_run=args.dry_run)
    print("\nWater ingest results:")
    for k, v in counts.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
