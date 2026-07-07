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
from dataclasses import dataclass

import httpx
from shapely.geometry import LineString

from ingestion.classify import classify_foot_access, classify_path_grade, classify_surface
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

# On-trail water POI tags — a sibling node query, same shape as trailheads.py.
_WATER_QUERY = """
[out:json][timeout:{timeout}];
(
  node["amenity"="drinking_water"]({s},{w},{n},{e});
  node["natural"="spring"]({s},{w},{n},{e});
  node["man_made"="water_well"]({s},{w},{n},{e});
  node["man_made"="water_tap"]({s},{w},{n},{e});
);
out body;
"""


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
            Feature(
                name=tags["name"],
                geom=LineString(coords),
                source="OSM",
                ref=osm_id,
                # Persist the way-type (Overpass filters to path|footway|track|
                # bridleway|steps) so the Curator can de-rank roadlike/access ways
                # later without a re-fetch. Kept even for a `track`, which the
                # Curator treats by name (fire roads stay; access roads sink).
                way_type=tags.get("highway") or None,
                # Classified difficulty/surface/access tags (Epic 026) — persisted
                # for a later phase; nothing reads them yet.
                path_grade=classify_path_grade(tags),
                psurface=classify_surface(tags),
                foot_access=classify_foot_access(tags),
            )
        )

    log.info(
        "OSM fetch: %d features in bbox %s (%d non-trail ways filtered)",
        len(features),
        bbox,
        skipped,
    )
    return features


@dataclass(frozen=True)
class WaterSource:
    """An on-trail water POI (Epic 035). Surfaces location + water type +
    seasonality only — never a potability claim (rule #1, source-or-silence).
    A spring/well/tap is a static POI, not fast/ephemeral like weather or
    streamflow, so persisting it as a world node is on the right side of rule
    #3 (graph holds slow/structural data only)."""

    osm_id: str
    water_type: str
    name: str | None
    lat: float
    lon: float
    seasonal: str | None


def _classify_water_type(tags: dict[str, str]) -> str | None:
    """Fixed priority when a node carries more than one matching tag:
    drinking_water > spring > water_well > water_tap. `None` if the node
    (defensively) carries none of the four — should not occur given the
    Overpass query, but the caller must not crash on it."""
    if tags.get("amenity") == "drinking_water":
        return "drinking_water"
    if tags.get("natural") == "spring":
        return "spring"
    if tags.get("man_made") == "water_well":
        return "water_well"
    if tags.get("man_made") == "water_tap":
        return "water_tap"
    return None


def fetch_water(
    bbox: tuple[float, float, float, float],
    *,
    client: httpx.Client | None = None,
    timeout: float = 60.0,
) -> list[WaterSource]:
    """Fetch OSM on-trail water POIs within bbox (south, west, north, east).
    Returns [] on error (rule #6: enrichment degrades-and-discloses, never
    fabricates)."""
    south, west, north, east = bbox
    query = _WATER_QUERY.format(timeout=int(timeout), s=south, w=west, n=north, e=east)
    c = client or httpx.Client(timeout=timeout)

    last_exc: Exception | None = None
    r = None
    for mirror in _OVERPASS_MIRRORS:
        try:
            r = c.post(mirror, data={"data": query})
            if r.status_code == 200:
                break
            log.debug("Water mirror %s returned %d, trying next", mirror, r.status_code)
        except Exception as exc:
            log.debug("Water mirror %s failed: %s", mirror, exc)
            last_exc = exc
    if r is None or r.status_code != 200:
        status = f"HTTP {r.status_code}" if r is not None else str(last_exc)
        log.warning("Water OSM fetch failed on all mirrors: %s", status)
        return []

    sources: list[WaterSource] = []
    for el in r.json().get("elements", []):
        tags = el.get("tags", {})
        water_type = _classify_water_type(tags)
        if water_type is None or "lat" not in el or "lon" not in el:
            continue
        sources.append(
            WaterSource(
                osm_id=f"node/{el['id']}",
                water_type=water_type,
                name=tags.get("name") or tags.get("official_name"),
                lat=float(el["lat"]),
                lon=float(el["lon"]),
                seasonal=tags.get("seasonal"),
            )
        )

    log.info("OSM water fetch: %d nodes in bbox %s", len(sources), bbox)
    return sources
