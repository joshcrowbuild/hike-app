"""NWS adapter — api.weather.gov (keyless; requires a User-Agent contact string).

Two hops: /points/{lat},{lon} -> the forecast URL, then that forecast's first
period; plus /alerts/active?point=... (flash-flood / red-flag alerts are the
Verifier's hard-guardrail feed). TTL ~10 min. Source-or-silence: any failure -> None.

`fetch_region_raw`/`NwsRegionAdapter` (frame-conditions-wave, epic-054 S2/S3) are a
SEPARATE, region-level probe over the same api.weather.gov source: the FULL
multi-day forecast periods list (never just `periods[0]`) plus a recent-
observations window from the nearest reporting station. Run ONCE per plan at the
query origin (`engine._fetch_region_raw`), never per candidate — a deliberately
different caller/cadence from `fetch()`/`NwsAdapter` above, which stays the
per-candidate hazard-alert probe, unchanged in shape.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
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

SOURCE = "NWS api.weather.gov"
POINTS_URL = "https://api.weather.gov/points/{lat},{lon}"
ALERTS_URL = "https://api.weather.gov/alerts/active"
ROOT_URL = "https://api.weather.gov/"

# The /points response supplies the second hop's URL. Only ever follow it back into
# api.weather.gov over https (2026-07-12 review): a compromised/spoofed response must
# not be able to point this client at an arbitrary host (SSRF) — a non-conforming URL
# is a probe failure (couldn't-verify → None), never fetched.
_ALLOWED_FORECAST_PREFIX = "https://api.weather.gov/"

# How far back the region-level recent-observations fetch reaches (S3: "the last
# ~72h"). The rolling 48h sum the mud rule actually gates on is computed FROM this
# wider window at render time (`orchestration.region_conditions`), never re-fetched.
RECENT_OBSERVATIONS_WINDOW_H = 72


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
        alert_severities = None
    else:
        features = alerts_doc.get("features", []) if isinstance(alerts_doc, dict) else []
        active_alerts = []
        # event -> NWS severity ("Extreme"/"Severe"/"Moderate"/"Minor"/"Unknown") —
        # kept on the fact (frame-conditions-wave Q7/epic-054 S1) so the curator can
        # grade a warning's severity instead of the adapter dropping it. A missing
        # severity on a real feature degrades to "Unknown" (never louder than graded).
        alert_severities = {}
        for f in features:
            if not isinstance(f, dict):
                continue
            props = f.get("properties")
            if not isinstance(props, dict):
                continue
            event = props.get("event")
            if not event:
                continue
            active_alerts.append(event)
            severity = props.get("severity")
            alert_severities[event] = (
                severity if isinstance(severity, str) and severity.strip() else "Unknown"
            )

    return VerifiedFact(
        value={
            "period": p.get("name"),
            "short_forecast": p.get("shortForecast"),
            "temperature": p.get("temperature"),
            "temperature_unit": p.get("temperatureUnit"),
            "active_alerts": active_alerts,
            "alert_severities": alert_severities,
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


# ── region-level conditions (frame-conditions-wave §5, epic-054 S2/S3) ────────


def _fetch_periods(client: httpx.Client, forecast_url: object) -> list[Any] | None:
    """The full periods list from the SAME `/points` -> forecast hop `fetch()`
    uses, minus the `periods[0]`-only narrowing — day selection happens later,
    at render time (`orchestration.region_conditions`), never here."""
    if not isinstance(forecast_url, str) or not forecast_url.startswith(_ALLOWED_FORECAST_PREFIX):
        return None
    doc = _http.get_json(client, forecast_url)
    periods = doc.get("properties", {}).get("periods") if isinstance(doc, dict) else None
    return periods if isinstance(periods, list) else None


def _nearest_station_url(client: httpx.Client, stations_url: object) -> str | None:
    """The first station named in the `/points` doc's `observationStations`
    collection — same off-host guard as the forecast hop (2026-07-12 review):
    a spoofed doc must not steer this client at an arbitrary host."""
    if not isinstance(stations_url, str) or not stations_url.startswith(_ALLOWED_FORECAST_PREFIX):
        return None
    doc = _http.get_json(client, stations_url)
    features = doc.get("features", []) if isinstance(doc, dict) else []
    for f in features:
        station_id = f.get("id") if isinstance(f, dict) else None
        if isinstance(station_id, str) and station_id.startswith(_ALLOWED_FORECAST_PREFIX):
            return station_id
    return None


def _fetch_recent_observations(
    client: httpx.Client, stations_url: object, *, now: datetime | None
) -> list[Any] | None:
    """The nearest station's observations over the last
    `RECENT_OBSERVATIONS_WINDOW_H` hours (S3) — `None` on no station, an off-host
    station id, or a failed observations call (source-or-silence)."""
    station_url = _nearest_station_url(client, stations_url)
    if station_url is None:
        return None
    window_start = (now or datetime.now(timezone.utc)) - timedelta(
        hours=RECENT_OBSERVATIONS_WINDOW_H
    )
    doc = _http.get_json(
        client, f"{station_url}/observations", params={"start": window_start.isoformat()}
    )
    features = doc.get("features", []) if isinstance(doc, dict) else []
    return [
        f["properties"]
        for f in features
        if isinstance(f, dict) and isinstance(f.get("properties"), dict)
    ]


def fetch_region_raw(
    lat: float,
    lon: float,
    user_agent: str,
    *,
    client: httpx.Client | None = None,
    now: datetime | None = None,
) -> VerifiedFact | None:
    """The region-level companion to `fetch()`: the FULL multi-day forecast
    periods list plus the nearest station's recent observations, fetched ONCE at
    a single region-representative point (`engine._fetch_region_raw` — never per
    candidate, AC-2.4). `periods`/`observations` degrade INDEPENDENTLY (a station
    lookup failing must never cost the forecast, and vice versa); only the shared
    `/points` hop failing outright fails the whole probe, since neither sub-fetch
    has anywhere to start from without it.

    Deliberately returns the RAW fetched shape, not a day-selected/summed one:
    `orchestration.region_conditions` does that derivation at render time so a
    cache hit within the TTL is reused regardless of which day a later request's
    frame targets (a repeat here would defeat the point of caching this at all)."""
    c = client or _http.build_client(
        headers={"User-Agent": user_agent, "Accept": "application/geo+json"}
    )
    points = _http.get_json(c, POINTS_URL.format(lat=lat, lon=lon))
    if not isinstance(points, dict):
        return None  # the shared /points hop failed — nothing to derive from
    props = points.get("properties", {})

    periods = _fetch_periods(c, props.get("forecast"))
    observations = _fetch_recent_observations(c, props.get("observationStations"), now=now)

    return VerifiedFact(
        value={"periods": periods, "observations": observations},
        source=SOURCE,
        fetched_at=now or datetime.now(timezone.utc),
        confidence_inputs={
            "authority": "tier1_gov",
            "freshness": "live",
            "source_kind": "primary",
        },
    )


class NwsRegionAdapter(LiveAdapter):
    """The region-level probe behind `fetch_region_raw` (frame-conditions-wave
    S2/S3) — a deliberately SEPARATE adapter from `NwsAdapter`: the two serve
    different callers at different cadences (the engine's single per-plan region
    call vs. the Verifier's per-candidate hazard-alert fan-out), and folding a
    differently-shaped fact under the same adapter would blur that boundary. Not
    registered in `adapters.registry.ADAPTER_FACTORIES` — it is resolved directly
    by `engine.build_runtime` onto `Runtime.region_probe`, never through the
    per-kind `probes_for` fan-out (a region-level fact has no `ConditionKind` of
    its own to be grouped under)."""

    name = "nws_region"
    kind = ConditionKind.weather
    # Generous TTL (S3): forecast periods and station observations both change on
    # the order of an hour. A repeat within the window reuses the SAME raw fetch
    # regardless of which day/`when` a later request wants — day selection is a
    # render-time concern (`orchestration.region_conditions`), never cached.
    ttl_seconds = 3600

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
        return fetch_region_raw(point.lat, point.lon, self._user_agent, client=self._client)

    def health(self) -> AdapterHealth:
        return health_from_status(_http.probe_status(self._client_or_build(), ROOT_URL))

    @classmethod
    def from_config(cls, settings: Settings) -> LiveAdapter | None:
        return cls(settings.nws_user_agent) if settings.nws_user_agent else None
