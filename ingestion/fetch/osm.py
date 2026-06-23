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

log = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

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
    try:
        r = c.post(OVERPASS_URL, data={"data": query})
        r.raise_for_status()
    except Exception as exc:
        log.warning("OSM fetch failed: %s", exc)
        return []

    features: list[Feature] = []
    for el in r.json().get("elements", []):
        coords = [(n["lon"], n["lat"]) for n in el.get("geometry", [])]
        if len(coords) < 2:
            continue
        name = el.get("tags", {}).get("name")
        if not name:
            continue
        osm_id = f"{el.get('type', 'way')}/{el['id']}"
        features.append(Feature(name=name, geom=LineString(coords), source="OSM", ref=osm_id))

    log.info("OSM fetch: %d features in bbox %s", len(features), bbox)
    return features
