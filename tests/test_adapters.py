"""Mocked-response tests for the live adapters (Track B).

No network: each adapter is driven with an httpx.Client backed by a MockTransport
returning a representative payload, asserting the VerifiedFact shape and source-
or-silence (failure -> None). Live validation against the real APIs is the
network-gated next step (run where egress is open).
"""

from __future__ import annotations

import httpx

from orchestration.adapters import airnow, firms, nws, ridb, usgs_water, valhalla
from orchestration.adapters.base import VerifiedFact


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_nws_returns_forecast_and_alerts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if "/points/" in u:
            return httpx.Response(
                200, json={"properties": {"forecast": "https://api.weather.gov/x/forecast"}}
            )
        if u.endswith("/forecast"):
            return httpx.Response(
                200,
                json={
                    "properties": {
                        "periods": [
                            {
                                "name": "Today",
                                "shortForecast": "Sunny",
                                "temperature": 70,
                                "temperatureUnit": "F",
                            }
                        ]
                    }
                },
            )
        if "/alerts/active" in u:
            return httpx.Response(
                200, json={"features": [{"properties": {"event": "Flood Watch"}}]}
            )
        return httpx.Response(404)

    fact = nws.fetch(38.5, -78.4, "ua", client=_client(handler))
    assert isinstance(fact, VerifiedFact)
    assert fact.value["short_forecast"] == "Sunny"
    assert fact.value["active_alerts"] == ["Flood Watch"]
    assert fact.source.startswith("NWS")


def test_nws_silence_on_failure() -> None:
    assert nws.fetch(0, 0, "ua", client=_client(lambda r: httpx.Response(500))) is None


def test_nws_off_host_forecast_url_is_never_fetched() -> None:
    # 2026-07-12 review: the /points response supplies the second hop's URL; a
    # spoofed/compromised payload must not steer this client to an arbitrary host.
    # Non-conforming → probe failure (None), and the URL is never requested.
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        requested.append(u)
        if "/points/" in u:
            return httpx.Response(
                200, json={"properties": {"forecast": "https://evil.example.com/forecast"}}
            )
        return httpx.Response(200, json={"properties": {"periods": [{"name": "Today"}]}})

    assert nws.fetch(38.5, -78.4, "ua", client=_client(handler)) is None
    assert not any("evil.example.com" in u for u in requested)


def test_nws_http_scheme_forecast_url_is_never_fetched() -> None:
    # Same guard, downgrade variant: plain-http back to the right host is still
    # non-conforming (the prefix pins the scheme too).
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(
            200, json={"properties": {"forecast": "http://api.weather.gov/x/forecast"}}
        )

    assert nws.fetch(38.5, -78.4, "ua", client=_client(handler)) is None
    assert all(u.startswith("https://api.weather.gov/") for u in requested)


def test_nws_conforming_forecast_url_still_fetched() -> None:
    # The guard changes nothing for the real shape: an api.weather.gov https URL
    # is followed exactly as before (the happy-path contract test also covers this).
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        requested.append(u)
        if "/points/" in u:
            return httpx.Response(
                200, json={"properties": {"forecast": "https://api.weather.gov/x/forecast"}}
            )
        if u.endswith("/forecast"):
            return httpx.Response(
                200, json={"properties": {"periods": [{"name": "Today", "temperature": 60}]}}
            )
        return httpx.Response(200, json={"features": []})

    fact = nws.fetch(38.5, -78.4, "ua", client=_client(handler))
    assert isinstance(fact, VerifiedFact)
    assert any(u == "https://api.weather.gov/x/forecast" for u in requested)


def test_nws_captures_office_and_grid_origin() -> None:
    # CDP-03 origin-at-boundary: office (gridId) + gridpoint are captured from /points.
    def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if "/points/" in u:
            return httpx.Response(
                200,
                json={
                    "properties": {
                        "forecast": "https://api.weather.gov/x/forecast",
                        "gridId": "LWX",
                        "gridX": 96,
                        "gridY": 70,
                    }
                },
            )
        if u.endswith("/forecast"):
            return httpx.Response(200, json={"properties": {"periods": [{"shortForecast": "Sun"}]}})
        return httpx.Response(200, json={"features": []})

    fact = nws.fetch(38.5, -78.4, "ua", client=_client(handler))
    assert fact is not None
    assert fact.value["forecast_office"] == "LWX"
    assert fact.value["grid_x"] == 96 and fact.value["grid_y"] == 70


# ── S1: alert severity is kept on the fact (frame-conditions-wave Q7) ─────────


def _points_and_forecast_handler(alerts_json: dict) -> object:
    def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if "/points/" in u:
            return httpx.Response(
                200, json={"properties": {"forecast": "https://api.weather.gov/x/forecast"}}
            )
        if u.endswith("/forecast"):
            return httpx.Response(200, json={"properties": {"periods": [{"name": "Today"}]}})
        if "/alerts/active" in u:
            return httpx.Response(200, json=alerts_json)
        return httpx.Response(404)

    return handler


def test_nws_captures_alert_severity() -> None:
    handler = _points_and_forecast_handler(
        {
            "features": [
                {"properties": {"event": "Extreme Heat Warning", "severity": "Extreme"}},
                {"properties": {"event": "Frost Advisory", "severity": "Minor"}},
            ]
        }
    )
    fact = nws.fetch(38.5, -78.4, "ua", client=_client(handler))
    assert fact is not None
    assert fact.value["active_alerts"] == ["Extreme Heat Warning", "Frost Advisory"]
    assert fact.value["alert_severities"] == {
        "Extreme Heat Warning": "Extreme",
        "Frost Advisory": "Minor",
    }


def test_nws_missing_alert_severity_degrades_to_unknown() -> None:
    # A real feature with no severity key must never crash or vanish (rule #1) —
    # it degrades to "Unknown", which curator.py grades as heads_up (never
    # louder than graded).
    handler = _points_and_forecast_handler(
        {"features": [{"properties": {"event": "Small Craft Advisory"}}]}
    )
    fact = nws.fetch(38.5, -78.4, "ua", client=_client(handler))
    assert fact is not None
    assert fact.value["alert_severities"] == {"Small Craft Advisory": "Unknown"}


def test_nws_failed_alerts_subcall_nulls_both_alerts_and_severities() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if "/points/" in u:
            return httpx.Response(
                200, json={"properties": {"forecast": "https://api.weather.gov/x/forecast"}}
            )
        if u.endswith("/forecast"):
            return httpx.Response(200, json={"properties": {"periods": [{"name": "Today"}]}})
        return httpx.Response(500)  # the alerts sub-call fails

    fact = nws.fetch(38.5, -78.4, "ua", client=_client(handler))
    assert fact is not None
    assert fact.value["active_alerts"] is None
    assert fact.value["alert_severities"] is None


# ── S2/S3: region-level probe (frame-conditions-wave §5) ──────────────────────

_STATIONS_DOC = {
    "features": [
        {"id": "https://api.weather.gov/stations/KABC", "properties": {"stationIdentifier": "KABC"}}
    ]
}

_OBSERVATIONS_DOC = {
    "features": [
        {
            "properties": {
                "timestamp": "2026-07-15T12:00:00+00:00",
                "precipitationLastHour": {"value": 2.0, "unitCode": "wmoUnit:mm"},
            }
        },
        {
            "properties": {
                "timestamp": "2026-07-15T13:00:00+00:00",
                "precipitationLastHour": {"value": 0.0, "unitCode": "wmoUnit:mm"},
            }
        },
    ]
}


def _region_handler(
    *,
    forecast_url: str | None = "https://api.weather.gov/x/forecast",
    stations_url: str | None = "https://api.weather.gov/gridpoints/LWX/96,70/stations",
    forecast_status: int = 200,
    stations_status: int = 200,
    observations_status: int = 200,
    requested: list[str] | None = None,
):
    def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if requested is not None:
            requested.append(u)
        if "/points/" in u:
            props: dict[str, object] = {}
            if forecast_url is not None:
                props["forecast"] = forecast_url
            if stations_url is not None:
                props["observationStations"] = stations_url
            return httpx.Response(200, json={"properties": props})
        if forecast_url is not None and u.startswith(forecast_url):
            if forecast_status != 200:
                return httpx.Response(forecast_status)
            return httpx.Response(
                200,
                json={
                    "properties": {
                        "periods": [
                            {"name": "Today", "isDaytime": True},
                            {"name": "Tonight", "isDaytime": False},
                        ]
                    }
                },
            )
        if stations_url is not None and u.startswith(stations_url):
            if stations_status != 200:
                return httpx.Response(stations_status)
            return httpx.Response(200, json=_STATIONS_DOC)
        if "/stations/KABC/observations" in u:
            if observations_status != 200:
                return httpx.Response(observations_status)
            return httpx.Response(200, json=_OBSERVATIONS_DOC)
        return httpx.Response(404)

    return handler


def test_fetch_region_raw_returns_full_periods_not_narrowed() -> None:
    # Unlike fetch()'s periods[0] narrowing, the region-level fetch keeps the
    # WHOLE list — day selection is a render-time concern (region_conditions.py).
    fact = nws.fetch_region_raw(38.5, -78.4, "ua", client=_client(_region_handler()))
    assert fact is not None
    assert len(fact.value["periods"]) == 2
    assert fact.value["observations"] == [f["properties"] for f in _OBSERVATIONS_DOC["features"]]
    assert fact.source.startswith("NWS")


def test_fetch_region_raw_points_failure_is_total() -> None:
    fact = nws.fetch_region_raw(0, 0, "ua", client=_client(lambda r: httpx.Response(500)))
    assert fact is None


def test_fetch_region_raw_forecast_failure_never_costs_observations() -> None:
    handler = _region_handler(forecast_status=500)
    fact = nws.fetch_region_raw(38.5, -78.4, "ua", client=_client(handler))
    assert fact is not None
    assert fact.value["periods"] is None
    assert fact.value["observations"] is not None


def test_fetch_region_raw_stations_failure_never_costs_forecast() -> None:
    handler = _region_handler(stations_status=500)
    fact = nws.fetch_region_raw(38.5, -78.4, "ua", client=_client(handler))
    assert fact is not None
    assert fact.value["periods"] is not None
    assert fact.value["observations"] is None


def test_fetch_region_raw_no_station_in_range_yields_none_observations() -> None:
    handler = _region_handler(stations_url=None)
    fact = nws.fetch_region_raw(38.5, -78.4, "ua", client=_client(handler))
    assert fact is not None
    assert fact.value["observations"] is None


def test_fetch_region_raw_off_host_stations_url_never_fetched() -> None:
    requested: list[str] = []
    handler = _region_handler(stations_url="https://evil.example.com/stations", requested=requested)
    fact = nws.fetch_region_raw(38.5, -78.4, "ua", client=_client(handler))
    assert fact is not None
    assert fact.value["observations"] is None
    assert not any("evil.example.com" in u for u in requested)


def test_fetch_region_raw_off_host_station_id_never_fetched() -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        requested.append(u)
        if "/points/" in u:
            return httpx.Response(
                200,
                json={
                    "properties": {
                        "forecast": "https://api.weather.gov/x/forecast",
                        "observationStations": "https://api.weather.gov/gp/stations",
                    }
                },
            )
        if u.endswith("/forecast"):
            return httpx.Response(200, json={"properties": {"periods": [{"name": "Today"}]}})
        if u.endswith("/stations"):
            return httpx.Response(
                200,
                json={"features": [{"id": "https://evil.example.com/stations/KXYZ"}]},
            )
        return httpx.Response(404)

    fact = nws.fetch_region_raw(38.5, -78.4, "ua", client=_client(handler))
    assert fact is not None
    assert fact.value["observations"] is None
    assert not any("evil.example.com" in u for u in requested)


def test_fetch_region_raw_observations_window_start_param() -> None:
    import datetime as dt

    captured: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if "/observations" in u:
            captured.append(u)
        if "/points/" in u:
            return httpx.Response(
                200,
                json={
                    "properties": {
                        "forecast": "https://api.weather.gov/x/forecast",
                        "observationStations": "https://api.weather.gov/gp/stations",
                    }
                },
            )
        if u.endswith("/forecast"):
            return httpx.Response(200, json={"properties": {"periods": [{"name": "Today"}]}})
        if u.endswith("/stations"):
            return httpx.Response(200, json=_STATIONS_DOC)
        if "/observations" in u:
            return httpx.Response(200, json=_OBSERVATIONS_DOC)
        return httpx.Response(404)

    fixed_now = dt.datetime(2026, 7, 15, 18, 0, tzinfo=dt.timezone.utc)
    fact = nws.fetch_region_raw(38.5, -78.4, "ua", client=_client(handler), now=fixed_now)
    assert fact is not None
    assert fact.fetched_at == fixed_now
    assert len(captured) == 1
    # start = now - 72h
    assert "start=2026-07-12T18%3A00%3A00" in captured[0] or "2026-07-12T18:00:00" in captured[0]


def test_nws_region_adapter_from_config_absent_credential() -> None:
    from orchestration.config import Settings

    settings = Settings.from_env({})
    assert nws.NwsRegionAdapter.from_config(settings) is None


def test_airnow_picks_worst_aqi() -> None:
    payload = [
        {"ParameterName": "O3", "AQI": 42, "Category": {"Name": "Good"}, "ReportingArea": "X"},
        {
            "ParameterName": "PM2.5",
            "AQI": 88,
            "Category": {"Name": "Moderate"},
            "ReportingArea": "X",
        },
    ]
    fact = airnow.fetch(
        38.5, -78.4, "key", client=_client(lambda r: httpx.Response(200, json=payload))
    )
    assert fact is not None
    assert fact.value["aqi"] == 88
    assert fact.value["parameter"] == "PM2.5"


def test_airnow_silence_on_empty() -> None:
    assert airnow.fetch(0, 0, "key", client=_client(lambda r: httpx.Response(200, json=[]))) is None


def test_firms_zero_detections_is_a_fact() -> None:
    csv_text = "latitude,longitude,bright_ti4,acq_date\n"  # header only -> zero rows
    fact = firms.fetch(
        38.5, -78.4, "key", client=_client(lambda r: httpx.Response(200, text=csv_text))
    )
    assert fact is not None
    assert fact.value["hotspot_count"] == 0  # absence of fire is verified info, not silence


def test_firms_silence_on_failure() -> None:
    assert firms.fetch(0, 0, "key", client=_client(lambda r: httpx.Response(503))) is None


def test_firms_captures_distinct_satellites() -> None:
    # CDP-03 origin-at-boundary: distinct satellites are the genuine independence signal.
    csv_text = (
        "latitude,longitude,satellite,acq_date\n"
        "38.5,-78.4,N,2026-06-29\n"  # Suomi-NPP
        "38.6,-78.3,Aqua,2026-06-29\n"
        "38.7,-78.2,N,2026-06-29\n"  # duplicate satellite — collapsed by the set
    )
    fact = firms.fetch(
        38.5, -78.4, "key", client=_client(lambda r: httpx.Response(200, text=csv_text))
    )
    assert fact is not None
    assert fact.value["hotspot_count"] == 3
    assert fact.value["satellites"] == ["Aqua", "N"]  # sorted, distinct


def test_firms_satellites_empty_when_column_absent() -> None:
    csv_text = "latitude,longitude,bright_ti4,acq_date\n38.5,-78.4,300,2026-06-29\n"
    fact = firms.fetch(
        38.5, -78.4, "key", client=_client(lambda r: httpx.Response(200, text=csv_text))
    )
    assert fact is not None
    assert fact.value["satellites"] == []  # no column → empty, never a fabricated origin


def test_usgs_picks_nearest_site() -> None:
    fc = {
        "features": [
            {
                "geometry": {"coordinates": [-78.40, 38.50]},
                "properties": {
                    "monitoring_location_name": "Near",
                    "monitoring_location_number": "111",
                },
            },
            {
                "geometry": {"coordinates": [-79.00, 39.00]},
                "properties": {
                    "monitoring_location_name": "Far",
                    "monitoring_location_number": "222",
                },
            },
        ]
    }
    fact = usgs_water.fetch(38.5, -78.4, client=_client(lambda r: httpx.Response(200, json=fc)))
    assert fact is not None
    assert fact.value["site_id"] == "111"


def test_ridb_lists_facilities() -> None:
    payload = {"RECDATA": [{"FacilityID": "1", "FacilityName": "Camp A", "Reservable": True}]}
    fact = ridb.fetch(
        38.5, -78.4, "key", client=_client(lambda r: httpx.Response(200, json=payload))
    )
    assert fact is not None
    assert fact.value["count"] == 1


def test_valhalla_drive_time() -> None:
    payload = {"sources_to_targets": [[{"time": 3600, "distance": 80.5}]]}
    fact = valhalla.fetch(
        (38.5, -78.4),
        (38.7, -78.6),
        "http://localhost:8002",
        client=_client(lambda r: httpx.Response(200, json=payload)),
    )
    assert fact is not None
    assert fact.value["drive_seconds"] == 3600
