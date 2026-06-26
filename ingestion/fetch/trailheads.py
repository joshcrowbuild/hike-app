"""OSM trailhead fetch — nodes tagged amenity/tourism/highway=trailhead.

Returns minimal TrailheadFeature records (name, lat, lon, osm_id, tags).
Restores the primary Scout query path: Scout prefers Trailhead→ACCESSES→CanonicalTrail
over the direct CanonicalTrail.point fallback that runs when no Trailhead nodes exist.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx

from ingestion.fetch.osm import _OVERPASS_MIRRORS

log = logging.getLogger(__name__)

_TRAILHEAD_QUERY = """
[out:json][timeout:45];
(
  node["amenity"="trailhead"]({s},{w},{n},{e});
  node["tourism"="trailhead"]({s},{w},{n},{e});
  node["highway"="trailhead"]({s},{w},{n},{e});
);
out body;
"""


@dataclass(frozen=True)
class TrailheadFeature:
    osm_id: str
    name: str | None
    lat: float
    lon: float
    tags: dict[str, str] = field(default_factory=dict)


def fetch(
    bbox: tuple[float, float, float, float],
    *,
    client: httpx.Client | None = None,
    timeout: float = 60.0,
) -> list[TrailheadFeature]:
    """Fetch OSM trailhead nodes within bbox (south, west, north, east)."""
    south, west, north, east = bbox
    query = _TRAILHEAD_QUERY.format(s=south, w=west, n=north, e=east)
    c = client or httpx.Client(timeout=timeout)

    last_exc: Exception | None = None
    r = None
    for mirror in _OVERPASS_MIRRORS:
        try:
            r = c.post(mirror, data={"data": query})
            if r.status_code == 200:
                break
            log.debug("Trailhead mirror %s returned %d", mirror, r.status_code)
        except Exception as exc:
            last_exc = exc

    if r is None or r.status_code != 200:
        status = f"HTTP {r.status_code}" if r is not None else str(last_exc)
        log.warning("Trailhead OSM fetch failed: %s", status)
        return []

    features: list[TrailheadFeature] = []
    for el in r.json().get("elements", []):
        tags = el.get("tags", {})
        features.append(
            TrailheadFeature(
                osm_id=f"node/{el['id']}",
                name=tags.get("name") or tags.get("official_name"),
                lat=float(el["lat"]),
                lon=float(el["lon"]),
                tags=tags,
            )
        )

    log.info("OSM trailhead fetch: %d nodes in bbox %s", len(features), bbox)
    return features
