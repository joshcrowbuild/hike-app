"""Epic 018 S3 — recorded-cassette regression gate for the live adapters (AC-3.3).

Every enabled live adapter is replayed against a recorded payload (`tests/cassettes/
<adapter>.json`) with no network, and its `VerifiedFact` is asserted field-by-field.
The cassettes carry the *real* API field names (confirmed against the live services),
so a schema/contract drift — a renamed key, a moved nesting level, a changed value
type — reds the build (ties Epic 009). Alongside the happy-path gate this file proves
the S3 honesty contract:

  * source-or-silence on any transport failure -> `None`, never a raised exception
    past the adapter boundary (AC-3.2 / AC-3.4);
  * partial-failure honesty — NWS alerts sub-call failure omits `active_alerts`
    (unknown, never a fabricated "no alerts"); USGS with no nearby gauge yields no
    water fact, and with a gauge discloses the point-to-gauge distance (AC-3.2);
  * a slow/999 source degrades to `None` rather than hanging, and the per-source TTL
    cache is active for every adapter (AC-3.4).

Cassettes carry no secrets (AC-3.3, rule #10): every key travels in a header, query
param, or URL path — never a response body — and `test_cassettes_carry_no_secrets`
enforces it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from orchestration.adapters.airnow import AirNowAdapter
from orchestration.adapters.base import LiveAdapter, Point, VerifiedFact
from orchestration.adapters.firms import FirmsAdapter
from orchestration.adapters.nws import NwsAdapter
from orchestration.adapters.ridb import RidbAdapter
from orchestration.adapters.usgs_water import UsgsWaterAdapter

_CASSETTES = Path(__file__).resolve().parent / "cassettes"
_POINT = Point(38.5219, -78.4356)  # a Shenandoah point (Big Meadows)


# ── cassette player: replay recorded payloads through httpx.MockTransport ──────


def _load(name: str) -> dict:
    return json.loads((_CASSETTES / f"{name}.json").read_text(encoding="utf-8"))


def _player(cassette: dict) -> httpx.Client:
    """Build a client whose transport answers each request from the first cassette
    interaction whose `match` substring appears in the URL. An unmatched request raises
    loudly — a new sub-call the cassette doesn't cover is a real contract change, not a
    silent pass."""
    interactions = cassette["interactions"]

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for it in interactions:
            if it["match"] in url:
                if "json" in it:
                    return httpx.Response(it["status"], json=it["json"])
                return httpx.Response(it["status"], text=it["text"])
        raise AssertionError(
            f"cassette {cassette['adapter']!r} has no interaction matching {url!r}"
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


# ── per-adapter builders + schema assertions (the drift gate) ─────────────────


def _make_nws(c: httpx.Client) -> LiveAdapter:
    return NwsAdapter("adventure-planner smoke-test", client=c)


def _assert_nws(fact: VerifiedFact) -> None:
    assert fact.source.startswith("NWS")
    assert fact.value["short_forecast"] == "Partly Sunny"
    assert fact.value["temperature"] == 68
    assert fact.value["active_alerts"] == []  # 200 with zero features == verified "clear"
    # CDP-03 origin-at-boundary fields the corroboration check keys on.
    assert fact.value["forecast_office"] == "LWX"
    assert fact.value["grid_x"] == 96 and fact.value["grid_y"] == 70


def _make_usgs(c: httpx.Client) -> LiveAdapter:
    return UsgsWaterAdapter(client=c)


def _assert_usgs(fact: VerifiedFact) -> None:
    assert fact.source.startswith("USGS")
    assert fact.value["site_id"] == "01628500"  # the nearer of the two gauges
    assert fact.value["monitoring_location"].startswith("HAWKSBILL CREEK")
    assert fact.value["latest_discharge_cfs"] == 123.0
    # AC-3.2: the point-to-gauge distance is disclosed, not just "may be miles away".
    assert re.search(r"~\d+(\.\d+)? mi", fact.disclosures[0])


def _make_airnow(c: httpx.Client) -> LiveAdapter:
    return AirNowAdapter("smoke-test-key", client=c)


def _assert_airnow(fact: VerifiedFact) -> None:
    assert fact.source == "EPA AirNow"
    assert fact.value["aqi"] == 45  # the worst (max) of O3 38 / PM2.5 45
    assert fact.value["parameter"] == "PM2.5"
    assert fact.value["reporting_area"] == "Shenandoah Valley"


def _make_firms(c: httpx.Client) -> LiveAdapter:
    return FirmsAdapter("smoke-test-key", client=c)


def _assert_firms(fact: VerifiedFact) -> None:
    assert fact.source == "NASA FIRMS"
    assert fact.value["hotspot_count"] == 1
    assert fact.value["satellites"] == ["N"]  # the distinct-origin column, parsed
    assert fact.value["dataset"] == "VIIRS_SNPP_NRT"


def _make_ridb(c: httpx.Client) -> LiveAdapter:
    return RidbAdapter("smoke-test-key", client=c)


def _assert_ridb(fact: VerifiedFact) -> None:
    assert fact.source == "Recreation.gov RIDB"
    assert fact.value["count"] == 2
    assert fact.value["facilities"][0]["name"] == "Big Meadows Campground"


# name -> (builder, schema assertion). The enabled fan-out set (Epic 018 S1+S2).
CASSETTE_CASES: list[tuple[str, Callable[[httpx.Client], LiveAdapter], Callable]] = [
    ("nws", _make_nws, _assert_nws),
    ("usgs_water", _make_usgs, _assert_usgs),
    ("airnow", _make_airnow, _assert_airnow),
    ("firms", _make_firms, _assert_firms),
    ("ridb", _make_ridb, _assert_ridb),
]
_IDS = [c[0] for c in CASSETTE_CASES]


# ── AC-3.3 — replay the cassette; assert the stamped fact + its schema ─────────


@pytest.mark.parametrize("name,make,check", CASSETTE_CASES, ids=_IDS)
def test_cassette_replays_to_a_stamped_fact(name, make, check) -> None:  # type: ignore[no-untyped-def]
    fact = make(_player(_load(name))).probe(_POINT)
    assert isinstance(fact, VerifiedFact)
    assert fact.source and fact.fetched_at is not None
    check(fact)  # field-by-field: any schema drift from the recorded payload reds this


def test_every_enabled_adapter_has_a_cassette() -> None:
    # The gate must cover the whole enabled fan-out; a new adapter without a cassette
    # is a coverage hole, not a silent pass.
    enabled = {"nws", "usgs_water", "airnow", "firms", "ridb"}
    have = {p.stem for p in _CASSETTES.glob("*.json")}
    assert enabled <= have, f"missing cassettes for {enabled - have}"


def test_cassettes_carry_no_secrets() -> None:
    # rule #10 / AC-3.3: no API-key-shaped token may live in a recorded payload. Every
    # adapter's credential travels in a header/param/path, never a response body.
    for path in _CASSETTES.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        suspicious = [t for t in re.findall(r"[A-Za-z0-9]+", text) if len(t) >= 20]
        assert not suspicious, f"{path.name} contains key-shaped token(s): {suspicious}"


# ── AC-3.2 — partial-failure honesty (unknown != a fabricated clear) ──────────


def test_nws_alerts_subcall_failure_omits_active_alerts() -> None:
    # Forecast succeeds but the alerts endpoint 500s: active_alerts must be unknown
    # (None), never [] — we cannot claim "no alerts" from a failed call.
    def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if "/points/" in u:
            return httpx.Response(
                200, json={"properties": {"forecast": "https://api.weather.gov/g/forecast"}}
            )
        if u.endswith("/forecast"):
            return httpx.Response(200, json={"properties": {"periods": [{"shortForecast": "Sun"}]}})
        return httpx.Response(500)  # alerts sub-call fails

    fact = NwsAdapter("ua", client=httpx.Client(transport=httpx.MockTransport(handler))).probe(
        _POINT
    )
    assert fact is not None
    assert fact.value["active_alerts"] is None  # unknown, NOT [] ("no alerts")


def test_usgs_no_nearby_gauge_yields_no_water_fact() -> None:
    # An empty feature set is not a zero-flow reading — it is silence (no water fact).
    empty = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    assert UsgsWaterAdapter(client=empty).probe(_POINT) is None


@pytest.mark.parametrize("name,make,_check", CASSETTE_CASES, ids=_IDS)
def test_transport_error_never_raises_past_the_adapter(name, make, _check) -> None:  # type: ignore[no-untyped-def]
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    fact = make(httpx.Client(transport=httpx.MockTransport(boom))).probe(_POINT)
    assert fact is None  # source-or-silence, never an exception past the boundary


# ── AC-3.4 — a slow/999 source degrades to None; the TTL cache is active ──────


@pytest.mark.parametrize("name,make,_check", CASSETTE_CASES, ids=_IDS)
def test_slow_or_999_source_degrades_to_none(name, make, _check) -> None:  # type: ignore[no-untyped-def]
    # A read timeout and a bogus 999 status are the two "won't answer" shapes; both must
    # degrade to silence, not hang or surface an unsourced fact.
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    assert make(httpx.Client(transport=httpx.MockTransport(timeout))).probe(_POINT) is None
    nine99 = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(999)))
    assert make(nine99).probe(_POINT) is None


def test_http_client_has_a_bounded_timeout() -> None:
    # The default adapter client must carry a finite timeout so a stalled source can't
    # pin a request open (AC-3.4). 8s is the Stage-4 budget.
    from orchestration.adapters import _http

    client = _http.build_client()
    assert client.timeout.read == _http.DEFAULT_TIMEOUT
    assert _http.DEFAULT_TIMEOUT and _http.DEFAULT_TIMEOUT <= 30


@pytest.mark.parametrize("name,make,check", CASSETTE_CASES, ids=_IDS)
def test_ttl_cache_active_for_every_adapter(name, make, check) -> None:  # type: ignore[no-untyped-def]
    # Replay through the registry TTL cache with a frozen clock: the second probe within
    # TTL must be served from cache with no further underlying call (the §29 cost lever).
    from orchestration.adapters import registry

    class _Counting(httpx.MockTransport):
        def __init__(self, handler: Callable) -> None:
            self.count = 0

            def wrapped(request: httpx.Request) -> httpx.Response:
                self.count += 1
                return handler(request)

            super().__init__(wrapped)

    cassette = _load(name)

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for it in cassette["interactions"]:
            if it["match"] in url:
                if "json" in it:
                    return httpx.Response(it["status"], json=it["json"])
                return httpx.Response(it["status"], text=it["text"])
        raise AssertionError(f"unmatched {url}")

    transport = _Counting(handler)
    adapter = make(httpx.Client(transport=transport))
    assert adapter.ttl_seconds > 0
    cache = registry.TTLCache(clock=lambda: 1000.0)  # frozen -> always within TTL
    first = cache.probe(adapter, _POINT)
    assert first is not None
    after_first = transport.count
    cache.probe(adapter, _POINT)  # within TTL -> cached, no new transport call
    assert transport.count == after_first
