"""USGS Water adapter — nearest streamflow monitoring location near a point.

Uses the NEW OGC API (api.waterdata.usgs.gov/ogcapi), not the legacy waterservices
endpoint (Stage 1 §27). Discloses that the nearest gauge may be miles away. TTL
~15 min. Source-or-silence: failure -> None.

LIVE-VERIFY: the exact OGC collection name, query params, and the latest-value
shape must be confirmed against the live API — outbound access to USGS is blocked
in the build sandbox, so the URL/params below are documented best-effort and only
the *parsing* (nearest-feature selection) is exercised by the tests. Confirm
before relying on it; fetching the latest discharge value needs a second OGC call.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from . import _http
from .base import VerifiedFact

SOURCE = "USGS Water Data (OGC API)"
ITEMS_URL = "https://api.waterdata.usgs.gov/ogcapi/v0/collections/monitoring-locations/items"


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

    return VerifiedFact(
        value={
            "monitoring_location": props.get("monitoring_location_name") or props.get("name"),
            "site_id": props.get("monitoring_location_number") or props.get("id"),
            "latest_discharge_cfs": None,  # second OGC call — LIVE-VERIFY
        },
        source=SOURCE,
        fetched_at=now or datetime.now(timezone.utc),
        confidence_inputs={"authority": "tier1_gov", "freshness": "live"},
        disclosures=("Nearest gauge may be miles from the trail; treat as indicative.",),
    )
