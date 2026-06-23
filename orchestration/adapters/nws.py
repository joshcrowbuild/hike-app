"""NWS adapter — api.weather.gov (keyless; requires a User-Agent contact string).

Two hops: /points/{lat},{lon} -> the forecast URL, then that forecast's first
period; plus /alerts/active?point=... (flash-flood / red-flag alerts are the
Verifier's hard-guardrail feed). TTL ~10 min. Source-or-silence: any failure -> None.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from . import _http
from .base import VerifiedFact

SOURCE = "NWS api.weather.gov"
POINTS_URL = "https://api.weather.gov/points/{lat},{lon}"
ALERTS_URL = "https://api.weather.gov/alerts/active"


def fetch(
    lat: float,
    lon: float,
    user_agent: str,
    *,
    client: httpx.Client | None = None,
    now: datetime | None = None,
) -> VerifiedFact | None:
    c = client or _http.build_client(
        headers={"User-Agent": user_agent, "Accept": "application/geo+json"}
    )

    points = _http.get_json(c, POINTS_URL.format(lat=lat, lon=lon))
    props = points.get("properties", {}) if isinstance(points, dict) else {}
    forecast_url = props.get("forecast")
    if not forecast_url:
        return None

    forecast = _http.get_json(c, forecast_url)
    periods = forecast.get("properties", {}).get("periods") if isinstance(forecast, dict) else None
    if not periods:
        return None
    p = periods[0]

    alerts_doc = _http.get_json(c, ALERTS_URL, params={"point": f"{lat},{lon}"})
    features = alerts_doc.get("features", []) if isinstance(alerts_doc, dict) else []
    alerts = [
        f["properties"]["event"] for f in features if isinstance(f, dict) and f.get("properties")
    ]

    return VerifiedFact(
        value={
            "period": p.get("name"),
            "short_forecast": p.get("shortForecast"),
            "temperature": p.get("temperature"),
            "temperature_unit": p.get("temperatureUnit"),
            "active_alerts": [a for a in alerts if a],
        },
        source=SOURCE,
        fetched_at=now or datetime.now(timezone.utc),
        confidence_inputs={"authority": "tier1_gov", "freshness": "live"},
    )
