"""OSM PBF fetch — deterministic local-file trail geometry via pyosmium.

A second, deterministic transport for the OSM geometry spine (Decision Log
§27), alongside `ingestion.fetch.osm`'s live Overpass HTTP path. Instead of
POSTing a query to a public Overpass mirror, this reads trail ways directly
from a local Geofabrik `.osm.pbf` extract (ODbL) with pyosmium (BSD-2-Clause)
and emits the identical `Feature` contract — same trail-highway filter, same
`is_trail_worthy` gate, same classified tags (`ingestion.classify`) — so the
two transports are drop-in interchangeable behind the `CorpusSource` seam
(`ingestion.sources.osm_pbf.OsmPbfSource`, registered as `"osm-pbf"`).

`data/osm/` is gitignored: the `.osm.pbf` extract is never committed. Obtain
it with `scripts/fetch_osm_pbf.py`, which downloads the Geofabrik state file
named in `regions/osm_pbf_manifest.json`.

The one genuinely-new mechanic vs. Overpass: an OSM way stores node IDs only,
not coordinates, so `osmium.FileProcessor(path).with_locations()` builds an
in-RAM node→(lat,lon) index before `osmium.geom.WKTFactory().create_linestring`
can resolve a way's geometry. The resulting WKT is parsed with `shapely.wkt`
into the same `LineString` type the Overpass path builds.

This module is additive: `ADVENTURE_CORPUS_SOURCES` still names `"osm"`
(Overpass) as the default spine (see `orchestration.config.Settings`);
nothing in the shipped default pipeline calls this transport yet.
"""

from __future__ import annotations

import logging
from pathlib import Path

import osmium
from osmium.geom import WKTFactory
from shapely import wkt as swkt
from shapely.geometry import LineString

from ingestion.classify import classify_foot_access, classify_path_grade, classify_surface
from ingestion.conflate.match import Feature
from ingestion.fetch.osm import _TRAIL_HIGHWAYS
from ingestion.trail_filter import is_trail_worthy

log = logging.getLogger(__name__)

_DEFAULT_FILE = Path("data/osm/region.osm.pbf")

# Overpass filters ways to this highway-value set server-side (osm.py's query);
# pyosmium reads ALL ways, so this transport applies the same filter in-loop.
# Reused, never re-derived, so the two transports can never drift apart (Guard 2).
_TRAIL_HIGHWAY_SET = frozenset(_TRAIL_HIGHWAYS.split("|"))


def _bounds_intersect(
    bounds: tuple[float, float, float, float], bbox: tuple[float, float, float, float]
) -> bool:
    """True if a geometry's shapely `.bounds` (minx, miny, maxx, maxy) rectangle
    overlaps `bbox` (south, west, north, east). Deliberately a superset of
    Overpass's server-side geometry-intersect: it keeps a way whose bounding box
    overlaps the region even if the line itself never enters it (e.g. an L-shaped
    detour), so it never drops a long trail that crosses the bbox without a
    vertex inside it. No `osmium-tool` — pure shapely."""
    minx, miny, maxx, maxy = bounds
    south, west, north, east = bbox
    return not (maxx < west or minx > east or maxy < south or miny > north)


def fetch(
    bbox: tuple[float, float, float, float],
    *,
    pbf_path: Path | str | None = None,
    factory: WKTFactory | None = None,
) -> list[Feature]:
    """Read OSM trails from a local `.osm.pbf`, clipped to bbox (south, west,
    north, east). Returns `[]` if the file is absent (mirrors `ingestion.fetch.
    usfs.fetch`'s missing-file degrade) — never fabricates geometry from a
    partial or corrupt read (rule #1)."""
    path = Path(pbf_path) if pbf_path else _DEFAULT_FILE
    if not path.exists():
        log.warning(
            "OSM PBF file not found at %s — skipping osm-pbf source.\n"
            "  Fetch it: python scripts/fetch_osm_pbf.py",
            path,
        )
        return []

    wktf = factory or WKTFactory()
    features: list[Feature] = []
    skipped = 0
    fp = osmium.FileProcessor(str(path)).with_locations()
    for o in fp:
        if not isinstance(o, osmium.osm.Way):
            continue
        tags = dict(o.tags)
        if tags.get("highway") not in _TRAIL_HIGHWAY_SET or "name" not in tags:
            continue
        try:
            geom = swkt.loads(wktf.create_linestring(o))
        except Exception as exc:
            log.debug("OSM PBF way/%d geometry resolution failed: %s", o.id, exc)
            continue
        coords = list(geom.coords)
        if len(coords) < 2:
            continue
        # Trail-worthiness gate (Lead 1) — identical to the Overpass path.
        if not is_trail_worthy(tags, coords):
            skipped += 1
            continue
        if not _bounds_intersect(geom.bounds, bbox):
            continue
        features.append(
            Feature(
                name=tags["name"],
                geom=LineString(coords),
                source="OSM",
                ref=f"way/{o.id}",
                way_type=tags.get("highway") or None,
                path_grade=classify_path_grade(tags),
                psurface=classify_surface(tags),
                foot_access=classify_foot_access(tags),
            )
        )

    log.info(
        "OSM PBF fetch: %d features in bbox %s from %s (%d non-trail ways filtered)",
        len(features),
        bbox,
        path,
        skipped,
    )
    return features
