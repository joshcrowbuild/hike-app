"""Trailhead ingestion — fetch OSM trailhead nodes, load to Neo4j, wire ACCESSES edges.

Run after the main trail pipeline (requires CanonicalTrail nodes to be present).
Matches each trailhead to nearby CanonicalTrail nodes via Neo4j spatial query:
  - Within 500m → ACCESSES edge, capped at the 5 nearest trails per trailhead.

The primary Scout query (Trailhead→ACCESSES→CanonicalTrail) only activates once
Trailhead nodes exist; until then Scout uses the CanonicalTrail.point fallback.

Usage:
    python -m ingestion.ingest_trailheads [--region shenandoah-gwj] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from ingestion.fetch.trailheads import TrailheadFeature
from ingestion.fetch.trailheads import fetch as fetch_trailheads

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

_ACCESSES_RADIUS_M = 500.0  # link trailhead→trail if trail centroid is within this distance


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


def _cypher_load_trailhead(th: TrailheadFeature, ingest_version: str) -> tuple[str, dict]:
    return (
        """
        MERGE (h:Trailhead {trailhead_id: $th_id})
        SET h.name            = $name,
            h.point           = point({latitude: $lat, longitude: $lon}),
            h.osm_id          = $osm_id,
            h.ingest_version  = $iv
        """,
        {
            "th_id": f"th:osm:{th.osm_id}",
            "name": th.name or th.osm_id,
            "lat": th.lat,
            "lon": th.lon,
            "osm_id": th.osm_id,
            "iv": ingest_version,
        },
    )


def _cypher_nearby_trails(th: TrailheadFeature, radius_m: float) -> tuple[str, dict]:
    return (
        """
        MATCH (t:CanonicalTrail)
        WHERE t.point IS NOT NULL
          AND point.distance(t.point, point({latitude: $lat, longitude: $lon})) <= $radius_m
        RETURN t.canonical_id AS canonical_id, t.name AS name,
               point.distance(t.point, point({latitude: $lat, longitude: $lon})) AS distance_m
        ORDER BY distance_m ASC
        LIMIT 5
        """,
        {"lat": th.lat, "lon": th.lon, "radius_m": radius_m},
    )


def _cypher_accesses(th_id: str, canonical_id: str) -> tuple[str, dict]:
    return (
        """
        MATCH (h:Trailhead {trailhead_id: $th_id})
        MATCH (t:CanonicalTrail {canonical_id: $cid})
        MERGE (h)-[:ACCESSES]->(t)
        """,
        {"th_id": th_id, "cid": canonical_id},
    )


def ingest_trailheads(
    region_id: str,
    *,
    dry_run: bool = False,
    radius_m: float = _ACCESSES_RADIUS_M,
) -> dict[str, int]:
    bbox = _load_region_bbox(region_id)
    log.info("Fetching OSM trailheads for %s …", region_id)
    trailheads = fetch_trailheads(bbox)
    log.info("Found %d trailhead nodes", len(trailheads))

    counts = {"fetched": len(trailheads), "loaded": 0, "accesses_edges": 0, "no_nearby_trail": 0}

    if dry_run:
        log.info("DRY-RUN — would load %d trailheads", len(trailheads))
        for th in trailheads[:5]:
            log.info(
                "  %s (%s) lat=%.4f lon=%.4f", th.name or "(unnamed)", th.osm_id, th.lat, th.lon
            )
        return counts

    try:
        from graph.client import GraphClient
        from orchestration.config import Settings
    except ImportError as exc:
        log.error("Neo4j not available: %s", exc)
        return counts

    settings = Settings.from_env()
    gc = GraphClient(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
    iv = region_id

    try:
        driver = gc._ensure_driver()
        with driver.session() as session:
            for th in trailheads:
                th_id = f"th:osm:{th.osm_id}"

                # Load the Trailhead node
                cypher, params = _cypher_load_trailhead(th, iv)
                session.run(cypher, **params)
                counts["loaded"] += 1

                # Find nearby CanonicalTrail nodes
                cypher, params = _cypher_nearby_trails(th, radius_m)
                nearby = [dict(r) for r in session.run(cypher, **params)]

                if not nearby:
                    counts["no_nearby_trail"] += 1
                    log.debug("No trails within %.0fm of %s", radius_m, th.name or th.osm_id)
                    continue

                for trail in nearby:
                    cypher, params = _cypher_accesses(th_id, trail["canonical_id"])
                    session.run(cypher, **params)
                    counts["accesses_edges"] += 1
                    log.debug(
                        "  %s → %s (%.0fm)",
                        th.name or th.osm_id,
                        trail["name"],
                        trail["distance_m"],
                    )

    finally:
        gc.close()

    log.info(
        "Trailhead ingest complete: loaded=%d accesses=%d no_nearby=%d",
        counts["loaded"],
        counts["accesses_edges"],
        counts["no_nearby_trail"],
    )
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest OSM trailhead nodes into Neo4j")
    parser.add_argument("--region", default="shenandoah-gwj")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--radius-m",
        type=float,
        default=_ACCESSES_RADIUS_M,
        help=f"Max distance to link trailhead→trail (default {_ACCESSES_RADIUS_M}m)",
    )
    args = parser.parse_args()

    counts = ingest_trailheads(args.region, dry_run=args.dry_run, radius_m=args.radius_m)
    print("\nTrailhead ingest results:")
    for k, v in counts.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
