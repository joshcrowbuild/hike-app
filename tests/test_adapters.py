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
