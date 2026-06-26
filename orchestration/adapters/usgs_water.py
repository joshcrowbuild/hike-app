"""USGS Water adapter — nearest streamflow monitoring location near a point.

Uses the OGC API (api.waterdata.usgs.gov/ogcapi) for site discovery and the
legacy waterservices endpoint for the latest discharge reading. The legacy
endpoint is authoritative until the OGC API's time-series collections stabilise
(target: Q1 2027 per Stage 1 §27). Discloses that the nearest gauge may be
miles away. TTL ~15 min. Source-or-silence: failure -> None.

Field names confirmed against live API 2026-06-23:
  monitoring_location_name, monitoring_location_number (from monitoring-locations collection)
  Discharge: waterservices.usgs.gov/nwis/iv/ parameterCd=00060 (cubic feet/second)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

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

SOURCE = "USGS Water Data (OGC API + WaterServices)"
ITEMS_URL = "https://api.waterdata.usgs.gov/ogcapi/v0/collections/monitoring-locations/items"
DISCHARGE_URL = "https://waterservices.usgs.gov/nwis/iv/"


_USGS_NO_DATA = frozenset({"-999999", "-999999.0", "Ice", "Bkw", "Ssn", "Rat", "Eqp"})


def _latest_discharge_cfs(site_id: str, client: httpx.Client) -> float | None:
    """Fetch latest instantaneous discharge reading (cfs) via legacy WaterServices."""
    doc = _http.get_json(
        client,
        DISCHARGE_URL,
        params={"format": "json", "sites": site_id, "parameterCd": "00060", "siteStatus": "active"},
    )
    if not isinstance(doc, dict):
        return None
    try:
        ts = doc["value"]["timeSeries"]
        if not ts:
            return None
        values = ts[0]["values"][0]["value"]
        if not values:
            return None
        raw = str(values[-1]["value"]).strip()
        if raw in _USGS_NO_DATA:
            return None  # USGS sentinel / qualifier — not a real reading
        val = float(raw)
        return val if val >= 0 else None  # negative values are also sentinels
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def fetch(
    lat: float,
    lon: float,
    *,
    radius_deg: float = 0.25,
    client: httpx.Client | None = None,
    now: datetime | None = None,
) -> VerifiedFact | None:
    c = client or _http.build_client(headers={"Accept": "application/json"})
    bbox = f"{lon - radius_deg},{lat - radius_deg},{lon + radius_deg},{lat + radius_deg}"
    doc = _http.get_json(c, ITEMS_URL, params={"bbox": bbox, "limit": 50, "f": "json"})
    features = doc.get("features") if isinstance(doc, dict) else None
    if not features:
        return None

    def planar_dist(feature: Any) -> float:
        coords = (feature.get("geometry") or {}).get("coordinates") or [lon, lat]
        return (coords[0] - lon) ** 2 + (coords[1] - lat) ** 2

    nearest = min(features, key=planar_dist)
    props = nearest.get("properties", {}) if isinstance(nearest, dict) else {}

    site_name = props.get("monitoring_location_name")
    site_id = props.get("monitoring_location_number")
    discharge = _latest_discharge_cfs(site_id, c) if site_id else None

    return VerifiedFact(
        value={
            "monitoring_location": site_name,
            "site_id": site_id,
            "latest_discharge_cfs": discharge,
        },
        source=SOURCE,
        fetched_at=now or datetime.now(timezone.utc),
        confidence_inputs={"authority": "tier1_gov", "freshness": "live"},
        disclosures=("Nearest gauge may be miles from the trail; treat as indicative.",),
    )


class UsgsWaterAdapter(LiveAdapter):
    """Streamflow at the nearest gauge via USGS Water Data (keyless)."""

    name = "usgs_water"
    kind = ConditionKind.water
    ttl_seconds = 900  # ~15 min (Stage 4 §4)

    def __init__(self, *, client: httpx.Client | None = None) -> None:
        self._client = client

    def capabilities(self) -> LiveCapabilities:
        return LiveCapabilities(
            needs_point=True,
            needs_site_id=False,
            is_keyless=True,
            supports_region=frozenset({"US"}),
        )

    def probe(self, point: Point, when: datetime | None = None) -> VerifiedFact | None:
        return fetch(point.lat, point.lon, client=self._client)

    def health(self) -> AdapterHealth:
        client = self._client or _http.build_client(headers={"Accept": "application/json"})
        status = _http.probe_status(
            client, ITEMS_URL, params={"bbox": "-78.6,38.3,-78.2,38.7", "limit": 1, "f": "json"}
        )
        return health_from_status(status)

    @classmethod
    def from_config(cls, settings: Settings) -> LiveAdapter | None:
        return cls()  # keyless — always available
