"""NPS Data API adapter — nearest-park closure/danger alerts (API key).

Surfaces the biggest live gap left after weather/air/fire/water/permits: "this place
is CLOSED / in danger." The NPS `/alerts` endpoint has no lat/lon/radius filter (the
design gap vs. RIDB), so "nearest park" is resolved in two calls: fetch the parks list
once and pick the nearest centroid by haversine (within a radius cap — a distant match
must not masquerade as "the local park"), then fetch that park's alerts and keep only
the safety-relevant categories. TTL: ~1 hour. Source-or-silence: no park in range, no
relevant alert, or any transport failure -> None, never a fabricated "open".
"""

from __future__ import annotations

import math
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

SOURCE = "NPS api.nps.gov"
BASE_URL = "https://developer.nps.gov/api/v1"
PARKS_URL = f"{BASE_URL}/parks"
ALERTS_URL = f"{BASE_URL}/alerts"

# Nearest-unit selection is a centroid approximation (a park boundary can be far
# larger than its centroid, and dense metro areas have co-located units) — a radius
# cap keeps a distant match from masquerading as "the local park" when nothing is
# actually close (Open Question 1: point-in-boundary is a follow-up, not this epic).
RADIUS_MILES = 50.0

_EARTH_RADIUS_MILES = 3958.8

# Only these categories are safety-relevant "this place is CLOSED / in danger" facts;
# Caution/Information are informational and would dilute source-or-silence into noise.
_RELEVANT_CATEGORIES = frozenset({"Closure", "Danger"})


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * _EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def _parse_lat_long(raw: object) -> tuple[float, float] | None:
    """Parse the `/parks` `latLong` format (`"lat:38.916554, long:-77.025977"`).
    Returns None for empty/unparseable strings so those units are skipped rather than
    crashing the nearest-park scan."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    lat_part, _, lon_part = raw.partition(",")
    try:
        lat = float(lat_part.split(":", 1)[1].strip())
        lon = float(lon_part.split(":", 1)[1].strip())
    except (IndexError, ValueError):
        return None
    return lat, lon


def _nearest_park(units: list[object], lat: float, lon: float) -> dict | None:
    """The nearest unit with a parseable `latLong` within `RADIUS_MILES`, or None —
    both "no unit close enough" and "everything unparseable" degrade to None
    (source-or-silence), never a best-effort guess past the cap."""
    best: dict | None = None
    best_dist = float("inf")
    for unit in units:
        if not isinstance(unit, dict):
            continue
        coords = _parse_lat_long(unit.get("latLong"))
        if coords is None:
            continue
        dist = _haversine_miles(lat, lon, coords[0], coords[1])
        if dist < best_dist:
            best_dist, best = dist, unit
    if best is None or best_dist > RADIUS_MILES:
        return None
    return best


def fetch(
    lat: float,
    lon: float,
    api_key: str,
    *,
    client: httpx.Client | None = None,
    now: datetime | None = None,
) -> VerifiedFact | None:
    c = client or _http.build_client(headers={"X-Api-Key": api_key})

    parks_doc = _http.get_json(c, PARKS_URL, params={"limit": 500})
    units = parks_doc.get("data") if isinstance(parks_doc, dict) else None
    if not units:
        return None
    nearest = _nearest_park(units, lat, lon)
    if nearest is None:
        return None
    park_code = nearest.get("parkCode")
    full_name = nearest.get("fullName")
    if not park_code:
        return None

    alerts_doc = _http.get_json(c, ALERTS_URL, params={"parkCode": park_code})
    records = alerts_doc.get("data") if isinstance(alerts_doc, dict) else None
    if not records:
        return None

    alerts = [
        {"title": a.get("title"), "category": a.get("category"), "url": a.get("url")}
        for a in records
        if isinstance(a, dict) and a.get("category") in _RELEVANT_CATEGORIES
    ]
    if not alerts:
        return None

    return VerifiedFact(
        value={
            "park": full_name,
            "park_code": park_code,
            "alerts": alerts,
            "count": len(alerts),
        },
        source=SOURCE,
        fetched_at=now or datetime.now(timezone.utc),
        confidence_inputs={"authority": "tier1_gov", "freshness": "live"},
        disclosures=("Park-level scope — the nearest NPS unit to this point, not trail-specific.",),
    )


class NpsAlertsAdapter(LiveAdapter):
    """Nearest-NPS-unit closure/danger alerts via the NPS Data API (API key header)."""

    name = "nps_alerts"
    kind = ConditionKind.closures
    # Closures/danger alerts change on hour/day scale: faster than permits' 1-day
    # window (facility data barely moves), slower than minute-scale weather/AQI.
    ttl_seconds = 3600  # ~1 hour

    def __init__(self, api_key: str, *, client: httpx.Client | None = None) -> None:
        self._api_key = api_key
        self._client = client

    def _client_or_build(self) -> httpx.Client:
        return self._client or _http.build_client(headers={"X-Api-Key": self._api_key})

    def capabilities(self) -> LiveCapabilities:
        return LiveCapabilities(
            needs_point=True,
            needs_site_id=False,
            is_keyless=False,
            supports_region=frozenset({"US"}),
        )

    def probe(self, point: Point, when: datetime | None = None) -> VerifiedFact | None:
        return fetch(point.lat, point.lon, self._api_key, client=self._client)

    def health(self) -> AdapterHealth:
        status = _http.probe_status(self._client_or_build(), PARKS_URL, params={"limit": 1})
        return health_from_status(status)

    @classmethod
    def from_config(cls, settings: Settings) -> LiveAdapter | None:
        return cls(settings.nps_api_key) if settings.nps_api_key else None
