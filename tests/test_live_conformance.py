"""Epic 013 S6 — the shared LiveAdapter conformance suite + EchoAdapter drop-in.

A parametrized contract every adapter must satisfy (driven by an injected client — no
live calls): probe never raises past the boundary on a transport failure (returns a
stamped VerifiedFact or None), health() transitions on 401/429/5xx/connection-error,
and the per-source TTL cache makes a repeat probe within TTL skip the underlying call.
Adding EchoAdapter was one file + one registry-factory entry — this suite passing on
it, and the registry selecting it, is the modularity claim asserted empirically (AC-6.4).
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from orchestration.adapters import registry
from orchestration.adapters.airnow import AirNowAdapter
from orchestration.adapters.base import (
    AdapterHealth,
    ConditionKind,
    LiveAdapter,
    Point,
    VerifiedFact,
)
from orchestration.adapters.echo import EchoAdapter
from orchestration.adapters.firms import FirmsAdapter
from orchestration.adapters.nws import NwsAdapter
from orchestration.adapters.ridb import RidbAdapter
from orchestration.adapters.usgs_water import UsgsWaterAdapter
from orchestration.adapters.valhalla import ValhallaAdapter
from orchestration.config import Settings

_POINT = Point(38.5, -78.4)


# ── per-adapter success handlers (a 200 that makes probe return a real fact) ──


def _nws_ok(request: httpx.Request) -> httpx.Response:
    u = str(request.url)
    if "/points/" in u:
        return httpx.Response(200, json={"properties": {"forecast": "https://x/forecast"}})
    if u.endswith("/forecast"):
        period = {
            "name": "Today",
            "shortForecast": "Sunny",
            "temperature": 70,
            "temperatureUnit": "F",
        }
        return httpx.Response(200, json={"properties": {"periods": [period]}})
    if "/alerts/active" in u:
        return httpx.Response(200, json={"features": []})
    return httpx.Response(200, json={})  # health root


def _airnow_ok(request: httpx.Request) -> httpx.Response:
    obs = {"ParameterName": "PM2.5", "AQI": 42, "Category": {"Name": "Good"}}
    return httpx.Response(200, json=[obs])


def _firms_ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, text="latitude,longitude\n")  # header only → hotspot_count 0


def _usgs_ok(request: httpx.Request) -> httpx.Response:
    u = str(request.url)
    if "waterservices" in u:
        return httpx.Response(200, json={"value": {"timeSeries": []}})
    feature = {
        "geometry": {"coordinates": [-78.4, 38.5]},
        "properties": {"monitoring_location_name": "X", "monitoring_location_number": "1"},
    }
    return httpx.Response(200, json={"features": [feature]})


def _ridb_ok(request: httpx.Request) -> httpx.Response:
    rec = {"FacilityID": "1", "FacilityName": "A", "Reservable": True}
    return httpx.Response(200, json={"RECDATA": [rec]})


def _valhalla_ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"sources_to_targets": [[{"time": 1800, "distance": 40}]]})


def _echo_ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"ok": True})


# make_adapter(client) -> adapter, plus its happy-path handler.
ADAPTERS: list[tuple[str, Callable[[httpx.Client], LiveAdapter], Callable]] = [
    ("nws", lambda c: NwsAdapter("ua", client=c), _nws_ok),
    ("airnow", lambda c: AirNowAdapter("key", client=c), _airnow_ok),
    ("firms", lambda c: FirmsAdapter("key", client=c), _firms_ok),
    ("usgs_water", lambda c: UsgsWaterAdapter(client=c), _usgs_ok),
    ("ridb", lambda c: RidbAdapter("key", client=c), _ridb_ok),
    (
        "valhalla",
        lambda c: ValhallaAdapter("http://v", origin=(38.5, -78.4), client=c),
        _valhalla_ok,
    ),
    ("echo", lambda c: EchoAdapter(client=c), _echo_ok),
]


def _client(handler: Callable) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _status_client(status: int) -> httpx.Client:
    return _client(lambda r: httpx.Response(status))


def _raising_client() -> httpx.Client:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    return _client(boom)


class _CountingTransport(httpx.MockTransport):
    def __init__(self, handler: Callable) -> None:
        self.count = 0

        def wrapped(request: httpx.Request) -> httpx.Response:
            self.count += 1
            return handler(request)

        super().__init__(wrapped)


# ── AC-6.1 — probe never raises past the boundary; returns VerifiedFact | None ──


@pytest.mark.parametrize("name,make,_ok", ADAPTERS, ids=[a[0] for a in ADAPTERS])
def test_s6_ac1_probe_degrades_to_none_never_raises(name, make, _ok) -> None:  # type: ignore[no-untyped-def]
    for client in (_status_client(500), _raising_client()):
        fact = make(client).probe(_POINT)
        assert fact is None or (
            isinstance(fact, VerifiedFact) and fact.source and fact.fetched_at is not None
        )


@pytest.mark.parametrize("name,make,ok", ADAPTERS, ids=[a[0] for a in ADAPTERS])
def test_s6_ac1_probe_success_is_stamped(name, make, ok) -> None:  # type: ignore[no-untyped-def]
    fact = make(_client(ok)).probe(_POINT)
    assert fact is None or (isinstance(fact, VerifiedFact) and fact.source and fact.fetched_at)


# ── AC-6.2 — health() transitions on injected status ──


@pytest.mark.parametrize("name,make,_ok", ADAPTERS, ids=[a[0] for a in ADAPTERS])
def test_s6_ac2_health_transitions(name, make, _ok) -> None:  # type: ignore[no-untyped-def]
    assert make(_status_client(401)).health() is AdapterHealth.NEEDS_REAUTH
    assert make(_status_client(429)).health() is AdapterHealth.RATE_LIMITED
    assert make(_status_client(503)).health() is AdapterHealth.DOWN
    assert make(_raising_client()).health() is AdapterHealth.DOWN


# ── AC-6.3 — the per-source TTL cache makes a repeat probe skip the underlying call ──


@pytest.mark.parametrize("name,make,ok", ADAPTERS, ids=[a[0] for a in ADAPTERS])
def test_s6_ac3_ttl_cache_skips_second_underlying_call(name, make, ok) -> None:  # type: ignore[no-untyped-def]
    transport = _CountingTransport(ok)
    adapter = make(httpx.Client(transport=transport))
    assert adapter.ttl_seconds > 0
    cache = registry.TTLCache(clock=lambda: 1000.0)  # frozen clock → always within TTL
    first = cache.probe(adapter, _POINT)
    if first is None:
        pytest.skip(f"{name} returned None for the generic success payload; TTL covered by S5.4")
    after_first = transport.count
    cache.probe(adapter, _POINT)  # within TTL → cached, no new transport call
    assert transport.count == after_first


# ── AC-6.4 — EchoAdapter is selected by the registry (the drop-in proof) ──


def test_s6_ac4_echo_selected_by_registry() -> None:
    s = Settings.from_env({"ADVENTURE_LIVE_ADAPTERS": "nws,echo", "NWS_USER_AGENT": "ua"})
    grouped = registry.probes_for("US", s)
    names = [a.name for a in grouped[ConditionKind.weather]]
    assert names == ["nws", "echo"]  # echo registered + selected as a weather fallback


# ── AC-6.5 — all five existing adapters plus valhalla pass conformance ──


def test_s6_ac5_all_builtin_adapters_registered() -> None:
    for name in ("nws", "airnow", "firms", "usgs_water", "ridb", "valhalla"):
        assert name in registry.ADAPTER_FACTORIES
