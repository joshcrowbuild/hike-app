"""EPA AirNow adapter — current AQI at a point (API key required).

Returns the worst (max-AQI) current observation across reported parameters. AQI is
labeled preliminary (Stage 1) and disclosed as such. TTL ~60 min. Source-or-
silence: failure / empty -> None.
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

    # No distinct-origin id is captured on purpose (CDP-01 spike): AirNow is an
    # *aggregator* of EPA monitors and returns only a coarse `reporting_area`, so two
    # AQI feeds both pulling AirNow share an origin by definition. Corroboration is
    # honestly 1 ("single aggregated source"); a monitor id here would falsely imply
    # an independence the feed doesn't expose.

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


class AirNowAdapter(LiveAdapter):
    """Air quality (AQI) via EPA AirNow (API key required)."""

    name = "airnow"
    kind = ConditionKind.air
    ttl_seconds = 3600  # ~60 min (Stage 4 §4)

    def __init__(self, api_key: str, *, client: httpx.Client | None = None) -> None:
        self._api_key = api_key
        self._client = client

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
        client = self._client or _http.build_client()
        status = _http.probe_status(
            client,
            URL,
            params={
                "format": "application/json",
                "latitude": 38.5,
                "longitude": -78.4,
                "distance": 50,
                "API_KEY": self._api_key,
            },
        )
        return health_from_status(status)

    @classmethod
    def from_config(cls, settings: Settings) -> LiveAdapter | None:
        return cls(settings.airnow_api_key) if settings.airnow_api_key else None
