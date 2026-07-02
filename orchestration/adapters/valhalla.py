"""Valhalla adapter — drive time/distance from an origin to a trailhead.

Self-hosted Valhalla (base_url from config). One-to-one `sources_to_targets`
matrix with auto costing. Source-or-silence: failure -> None.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

import httpx

from . import _http
from .base import (
    AdapterHealth,
    ConditionKind,
    LiveAdapter,
    LiveCapabilities,
    Point,
    VerifiedFact,
    health_from_status,
)

if TYPE_CHECKING:
    from orchestration.config import Settings

SOURCE = "Valhalla (self-hosted)"

LatLon = tuple[float, float]


def fetch(
    origin: tuple[float, float],
    trailhead: tuple[float, float],
    base_url: str,
    *,
    costing: str = "auto",
    client: httpx.Client | None = None,
    now: datetime | None = None,
) -> VerifiedFact | None:
    c = client or _http.build_client(
        headers={"Content-Type": "application/json"}, follow_redirects=False
    )
    body = {
        "sources": [{"lat": origin[0], "lon": origin[1]}],
        "targets": [{"lat": trailhead[0], "lon": trailhead[1]}],
        "costing": costing,
    }
    doc = _http.post_json(c, base_url.rstrip("/") + "/sources_to_targets", body)
    matrix = doc.get("sources_to_targets") if isinstance(doc, dict) else None
    if not matrix or not matrix[0]:
        return None
    cell = matrix[0][0]
    if not isinstance(cell, dict) or cell.get("time") is None:
        return None

    return VerifiedFact(
        value={"drive_seconds": cell.get("time"), "distance_km": cell.get("distance")},
        source=SOURCE,
        fetched_at=now or datetime.now(timezone.utc),
        confidence_inputs={"authority": "derived", "freshness": "live"},
    )


def _cell_to_fact(cell: object, stamped: datetime) -> VerifiedFact | None:
    if not isinstance(cell, dict) or cell.get("time") is None:
        return None
    return VerifiedFact(
        value={"drive_seconds": cell.get("time"), "distance_km": cell.get("distance")},
        source=SOURCE,
        fetched_at=stamped,
        confidence_inputs={"authority": "derived", "freshness": "live"},
    )


def fetch_matrix(
    origin: LatLon,
    targets: list[LatLon],
    base_url: str,
    *,
    costing: str = "auto",
    client: httpx.Client | None = None,
    now: datetime | None = None,
) -> list[VerifiedFact | None]:
    """One source × K targets in a single `/sources_to_targets` call. Returns one fact
    (or None) per target, aligned by index (source-or-silence per cell). K candidates
    cost one HTTP round-trip, not K (Epic 005 AC-4.1)."""
    if not targets:
        return []
    c = client or _http.build_client(
        headers={"Content-Type": "application/json"}, follow_redirects=False
    )
    body = {
        "sources": [{"lat": origin[0], "lon": origin[1]}],
        "targets": [{"lat": t[0], "lon": t[1]} for t in targets],
        "costing": costing,
    }
    doc = _http.post_json(c, base_url.rstrip("/") + "/sources_to_targets", body)
    matrix = doc.get("sources_to_targets") if isinstance(doc, dict) else None
    # Honor the never-raise boundary on a malformed-but-200 shape (e.g. a dict-shaped
    # matrix): degrade to all-None rather than crash up into the engine (rule #1/#6).
    if not isinstance(matrix, list) or not matrix or not isinstance(matrix[0], list):
        return [None] * len(targets)
    row = matrix[0]
    stamped = now or datetime.now(timezone.utc)
    return [_cell_to_fact(row[i] if i < len(row) else None, stamped) for i in range(len(targets))]


def fetch_isochrone(
    origin: LatLon,
    time_budget_s: float,
    base_url: str,
    *,
    costing: str = "auto",
    client: httpx.Client | None = None,
) -> list[LatLon] | None:
    """One `/isochrone` call → the polygon (list of (lat, lon)) reachable within the
    time budget. Candidates are tested point-in-polygon in Python (no per-candidate
    round-trip). Source-or-silence: failure → None (Epic 005 AC-4.2)."""
    c = client or _http.build_client(
        headers={"Content-Type": "application/json"}, follow_redirects=False
    )
    minutes = max(1.0, time_budget_s / 60.0)
    body = {
        "locations": [{"lat": origin[0], "lon": origin[1]}],
        "costing": costing,
        "contours": [{"time": minutes}],
        "polygons": True,
    }
    doc = _http.post_json(c, base_url.rstrip("/") + "/isochrone", body)
    features = doc.get("features") if isinstance(doc, dict) else None
    if not features or not isinstance(features[0], dict):
        return None
    geom = features[0].get("geometry")
    coords = geom.get("coordinates") if isinstance(geom, dict) else None
    if not coords:
        return None
    # GeoJSON Polygon: coordinates[0] is the outer ring of [lon, lat] pairs. A
    # MultiPolygon (ring-of-rings) or null/non-numeric coordinate must degrade to None,
    # not raise past the boundary (rule #1/#6) — each pair is parsed defensively.
    ring = coords[0] if coords and isinstance(coords[0], list) else coords
    polygon: list[LatLon] = []
    for pt in ring:
        if not isinstance(pt, (list, tuple)) or len(pt) < 2:
            continue
        try:
            polygon.append((float(pt[1]), float(pt[0])))
        except (TypeError, ValueError):
            continue  # nested ring (MultiPolygon) or non-numeric coordinate
    return polygon or None


class ValhallaAdapter(LiveAdapter):
    """Drive-time via self-hosted Valhalla (kind=drive_time). Origin-relative: the
    engine consumes it through the `DriveTimeComputer` batch protocol — `matrix(origin,
    targets)` / `isochrone(origin, budget)` take the per-request origin as an argument
    (Settings has no origin). The per-point `probe(point)` path routes from an origin
    set on the instance and returns None when none is bound. Region-agnostic. Behind
    this contract, an OSRM/GraphHopper swap is one adapter file (Epic 013 S5, absorbing
    Epic 005's M5 Router)."""

    name = "valhalla"
    kind = ConditionKind.drive_time
    ttl_seconds = 600

    def __init__(
        self,
        base_url: str,
        *,
        origin: LatLon | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url
        self._origin = origin
        self._client = client

    def capabilities(self) -> LiveCapabilities:
        return LiveCapabilities(
            needs_point=True, needs_site_id=False, is_keyless=True, supports_region=frozenset()
        )

    def probe(self, point: Point, when: datetime | None = None) -> VerifiedFact | None:
        if self._origin is None:
            return None  # no origin bound → cannot route (never a fabricated time)
        return fetch(self._origin, (point.lat, point.lon), self._base_url, client=self._client)

    def matrix(self, origin: LatLon, targets: list[LatLon]) -> list[VerifiedFact | None]:
        return fetch_matrix(origin, targets, self._base_url, client=self._client)

    def isochrone(self, origin: LatLon, time_budget_s: float) -> list[LatLon] | None:
        return fetch_isochrone(origin, time_budget_s, self._base_url, client=self._client)

    def health(self) -> AdapterHealth:
        client = self._client or _http.build_client(follow_redirects=False)
        return health_from_status(
            _http.probe_status(client, self._base_url.rstrip("/") + "/status")
        )

    @classmethod
    def from_config(cls, settings: Settings) -> LiveAdapter | None:
        return cls(settings.valhalla_base_url) if settings.valhalla_base_url else None
