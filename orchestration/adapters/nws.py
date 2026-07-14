"""NWS adapter — api.weather.gov (keyless; requires a User-Agent contact string).

Two hops: /points/{lat},{lon} -> the forecast URL, then that forecast's first
period; plus /alerts/active?point=... (flash-flood / red-flag alerts are the
Verifier's hard-guardrail feed). TTL ~10 min. Source-or-silence: any failure -> None.
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

SOURCE = "NWS api.weather.gov"
POINTS_URL = "https://api.weather.gov/points/{lat},{lon}"
ALERTS_URL = "https://api.weather.gov/alerts/active"
ROOT_URL = "https://api.weather.gov/"

# The /points response supplies the second hop's URL. Only ever follow it back into
# api.weather.gov over https (2026-07-12 review): a compromised/spoofed response must
# not be able to point this client at an arbitrary host (SSRF) — a non-conforming URL
# is a probe failure (couldn't-verify → None), never fetched.
_ALLOWED_FORECAST_PREFIX = "https://api.weather.gov/"


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
    if not isinstance(forecast_url, str) or not forecast_url.startswith(_ALLOWED_FORECAST_PREFIX):
        return None

    # Origin-at-boundary (CDP-03 / spike item 3): the forecast office (CWA / gridId) and
    # gridpoint uniquely identify which NWS product this reading came from. Captured now
    # so the day weather gets a second provider, the independence check is already wired —
    # two readings from the same office+grid are NOT independent corroboration.
    forecast_office = props.get("gridId") or props.get("cwa")
    grid_x = props.get("gridX")
    grid_y = props.get("gridY")

    forecast = _http.get_json(c, forecast_url)
    periods = forecast.get("properties", {}).get("periods") if isinstance(forecast, dict) else None
    if not periods:
        return None
    p = periods[0]

    alerts_doc = _http.get_json(c, ALERTS_URL, params={"point": f"{lat},{lon}"})
    # source-or-silence on the alerts sub-call: None means the call failed, so we
    # cannot report "no alerts" — omit the key rather than fabricate an empty list.
    if alerts_doc is None:
        active_alerts = None  # unknown — alerts endpoint failed
    else:
        features = alerts_doc.get("features", []) if isinstance(alerts_doc, dict) else []
        active_alerts = [
            f["properties"]["event"]
            for f in features
            if isinstance(f, dict) and f.get("properties")
            if f["properties"].get("event")
        ]

    return VerifiedFact(
        value={
            "period": p.get("name"),
            "short_forecast": p.get("shortForecast"),
            "temperature": p.get("temperature"),
            "temperature_unit": p.get("temperatureUnit"),
            "active_alerts": active_alerts,
            "forecast_office": forecast_office,
            "grid_x": grid_x,
            "grid_y": grid_y,
        },
        source=SOURCE,
        fetched_at=now or datetime.now(timezone.utc),
        # source_kind "primary" (CDP-06 retune): forecast_office + grid_x/grid_y name
        # the one authoritative NWS gridpoint forecast for this point — a single but
        # uniquely-designated institutional origin, not an unverified aggregate. See
        # orchestration/confidence.py for the primary/aggregated corroboration split.
        confidence_inputs={
            "authority": "tier1_gov",
            "freshness": "live",
            "source_kind": "primary",
        },
    )


class NwsAdapter(LiveAdapter):
    """Weather via api.weather.gov (keyless; requires a User-Agent contact string)."""

    name = "nws"
    kind = ConditionKind.weather
    # Weather updates on the order of hours (NWS regenerates the gridpoint forecast
    # roughly hourly) — a 1 h window matches true volatility (CDP-08) and, with the
    # two-call points→forecast latency, is the biggest per-feed call-cut lever (Epic 018 S6).
    ttl_seconds = 3600  # ~1 h — weather-hours window (CDP-08)

    def __init__(self, user_agent: str, *, client: httpx.Client | None = None) -> None:
        self._user_agent = user_agent
        self._client = client

    def _client_or_build(self) -> httpx.Client:
        return self._client or _http.build_client(
            headers={"User-Agent": self._user_agent, "Accept": "application/geo+json"}
        )

    def capabilities(self) -> LiveCapabilities:
        return LiveCapabilities(
            needs_point=True,
            needs_site_id=False,
            is_keyless=True,
            supports_region=frozenset({"US"}),
        )

    def probe(self, point: Point, when: datetime | None = None) -> VerifiedFact | None:
        return fetch(point.lat, point.lon, self._user_agent, client=self._client)

    def health(self) -> AdapterHealth:
        return health_from_status(_http.probe_status(self._client_or_build(), ROOT_URL))

    @classmethod
    def from_config(cls, settings: Settings) -> LiveAdapter | None:
        return cls(settings.nws_user_agent) if settings.nws_user_agent else None
