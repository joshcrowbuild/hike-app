"""EPA AirNow adapter — current AQI at a point (API key required).

Returns the worst (max-AQI) current observation across reported parameters. AQI is
labeled preliminary (Stage 1) and disclosed as such. TTL ~60 min. Source-or-
silence: failure / empty -> None.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from . import _http
from .base import VerifiedFact

SOURCE = "EPA AirNow"
URL = "https://www.airnowapi.org/aq/observation/latLong/current/"


def fetch(
    lat: float,
    lon: float,
    api_key: str,
    *,
    distance_miles: int = 50,
    client: httpx.Client | None = None,
    now: datetime | None = None,
) -> VerifiedFact | None:
    c = client or _http.build_client()
    data = _http.get_json(
        c,
        URL,
        params={
            "format": "application/json",
            "latitude": lat,
            "longitude": lon,
            "distance": distance_miles,
            "API_KEY": api_key,
        },
    )
    if not isinstance(data, list) or not data:
        return None

    worst = max(data, key=lambda o: o.get("AQI", -1) if isinstance(o, dict) else -1)
    if not isinstance(worst, dict) or worst.get("AQI") is None:
        return None
    category = worst.get("Category") or {}

    return VerifiedFact(
        value={
            "aqi": worst.get("AQI"),
            "parameter": worst.get("ParameterName"),
            "category": category.get("Name") if isinstance(category, dict) else None,
            "reporting_area": worst.get("ReportingArea"),
        },
        source=SOURCE,
        fetched_at=now or datetime.now(timezone.utc),
        confidence_inputs={"authority": "tier1_gov", "freshness": "live"},
        disclosures=("AirNow AQI is preliminary and subject to revision.",),
    )
