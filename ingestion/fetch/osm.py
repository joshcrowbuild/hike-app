"""OSM fetch — Overpass API, bbox-clipped hiking trails with names.

Returns Feature objects (ingestion.conflate.match.Feature) backed by Shapely
LineString geometries. OSM is the geometry spine (Decision Log §27); all agency
sources conflate onto OSM records.

Overpass is free and keyless; a 60-second timeout is conservative for the pilot
bbox. On any error the fetch returns [] (fetch-layer failure ≠ silence on facts;
the pipeline reports it separately).
"""

from __future__ import annotations

import logging

import httpx
from shapely.geometry import LineString

from ingestion.conflate.match import Feature
from ingestion.trail_filter import is_trail_worthy

log = logging.getLogger(__name__)

# Primary + fallback mirrors tried in order; first 200 wins.
_OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]

# OSM highway values that represent walkable trails (not roads or cycle lanes).
_TRAIL_HIGHWAYS = "path|footway|track|bridleway|steps"


def fetch(
    bbox: tuple[float, float, float, float],
    *,
    client: httpx.Client | None = None,
    timeout: float = 90.0,
) -> list[Feature]:
    """Fetch OSM trails within bbox (south, west, north, east). Returns [] on error."""
    south, west, north, east = bbox
    query = (
        f"[out:json][timeout:{int(timeout)}];"
        f'way["highway"~"{_TRAIL_HIGHWAYS}"]["name"]'
        f"({south},{west},{north},{east});"
        "out geom;"
    )
    c = client or httpx.Client(timeout=timeout)
    last_exc: Exception | None = None
    r = None
    for mirror in _OVERPASS_MIRRORS:
        try:
            r = c.post(mirror, data={"data": query})
            if r.status_code == 200:
                break
            log.debug("OSM mirror %s returned %d, trying next", mirror, r.status_code)
        except Exception as exc:
            log.debug("OSM mirror %s failed: %s", mirror, exc)
            last_exc = exc
    if r is None or r.status_code != 200:
        status = f"HTTP {r.status_code}" if r is not None else str(last_exc)
        log.warning("OSM fetch failed on all mirrors: %s", status)
        return []

    features: list[Feature] = []
    skipped = 0
    for el in r.json().get("elements", []):
        coords = [(n["lon"], n["lat"]) for n in el.get("geometry", [])]
        if len(coords) < 2:
            continue
        tags = el.get("tags", {})
        # Trail-worthiness gate (Lead 1): drop urban/private non-trails (sidewalks,
        # school/utility footways, private drives) by tag + name, keeping fire roads.
        if not is_trail_worthy(tags, coords):
            skipped += 1
            continue
        osm_id = f"{el.get('type', 'way')}/{el['id']}"
        features.append(
            Feature(name=tags["name"], geom=LineString(coords), source="OSM", ref=osm_id)
        )

    log.info(
        "OSM fetch: %d features in bbox %s (%d non-trail ways filtered)",
        len(features),
        bbox,
        skipped,
    )
    return features
