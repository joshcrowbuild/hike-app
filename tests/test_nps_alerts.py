"""Epic 034 S6 — NpsAlertsAdapter: nearest-park closure/danger alerts.

All HTTP via httpx.MockTransport routing /parks and /alerts (no live calls).
Source-or-silence: no park in range, no relevant alert, or any transport failure
must degrade to None, never a fabricated "open".
"""

from __future__ import annotations

from collections.abc import Callable

import httpx

from orchestration.adapters.base import AdapterHealth, ConditionKind, Point, VerifiedFact
from orchestration.adapters.nps_alerts import SOURCE, NpsAlertsAdapter
from orchestration.config import Settings

_POINT = Point(38.5, -78.4)


def _unit(
    lat: float, lon: float, *, code: str = "SHEN", name: str = "Shenandoah National Park"
) -> dict:
    return {"fullName": name, "parkCode": code, "latLong": f"lat:{lat}, long:{lon}"}


def _alert(category: str, *, title: str = "Road closed", url: str = "https://nps.gov/x") -> dict:
    return {"title": title, "category": category, "url": url}


def _handler(parks: list[dict], alerts: list[dict]) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if "/parks" in u:
            return httpx.Response(200, json={"data": parks})
        if "/alerts" in u:
            return httpx.Response(200, json={"data": alerts})
        return httpx.Response(404)

    return handler


def _client(handler: Callable) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _status_client(status: int) -> httpx.Client:
    return _client(lambda r: httpx.Response(status))


def _raising_client() -> httpx.Client:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    return _client(boom)


# ── (a) happy path ──


def test_happy_path_returns_stamped_fact() -> None:
    parks = [_unit(38.5, -78.4)]
    alerts = [_alert("Closure")]
    adapter = NpsAlertsAdapter("key", client=_client(_handler(parks, alerts)))
    fact = adapter.probe(_POINT)
    assert isinstance(fact, VerifiedFact)
    assert fact.source == SOURCE
    assert fact.value["count"] >= 1
    assert fact.value["park"] == "Shenandoah National Park"
    assert fact.value["park_code"] == "SHEN"
    assert any("Park-level scope" in d for d in fact.disclosures)


# ── (b) no park within RADIUS_MILES ──


def test_no_park_within_radius_returns_none() -> None:
    parks = [_unit(0.0, 0.0)]  # far from _POINT
    alerts = [_alert("Closure")]
    adapter = NpsAlertsAdapter("key", client=_client(_handler(parks, alerts)))
    assert adapter.probe(_POINT) is None


# ── (c) alerts present but all Caution/Information ──


def test_only_informational_alerts_returns_none() -> None:
    parks = [_unit(38.5, -78.4)]
    alerts = [_alert("Caution"), _alert("Information")]
    adapter = NpsAlertsAdapter("key", client=_client(_handler(parks, alerts)))
    assert adapter.probe(_POINT) is None


# ── (d) empty alerts list ──


def test_empty_alerts_returns_none() -> None:
    parks = [_unit(38.5, -78.4)]
    adapter = NpsAlertsAdapter("key", client=_client(_handler(parks, [])))
    assert adapter.probe(_POINT) is None


# ── (e) non-200 / ConnectError on either sub-call never raises ──


def test_parks_failure_returns_none() -> None:
    adapter = NpsAlertsAdapter("key", client=_status_client(500))
    assert adapter.probe(_POINT) is None


def test_parks_connect_error_returns_none() -> None:
    adapter = NpsAlertsAdapter("key", client=_raising_client())
    assert adapter.probe(_POINT) is None


def test_alerts_failure_after_parks_ok_returns_none() -> None:
    parks = [_unit(38.5, -78.4)]

    def handler(request: httpx.Request) -> httpx.Response:
        if "/parks" in str(request.url):
            return httpx.Response(200, json={"data": parks})
        return httpx.Response(500)

    adapter = NpsAlertsAdapter("key", client=_client(handler))
    assert adapter.probe(_POINT) is None


# ── (f) health() status mapping ──


def test_health_transitions() -> None:
    assert (
        NpsAlertsAdapter("key", client=_status_client(401)).health() is AdapterHealth.NEEDS_REAUTH
    )
    assert (
        NpsAlertsAdapter("key", client=_status_client(429)).health() is AdapterHealth.RATE_LIMITED
    )
    assert NpsAlertsAdapter("key", client=_status_client(503)).health() is AdapterHealth.DOWN
    assert NpsAlertsAdapter("key", client=_raising_client()).health() is AdapterHealth.DOWN


# ── (g) from_config self-drop ──


def test_from_config_self_drops_without_key() -> None:
    settings = Settings.from_env({})
    assert NpsAlertsAdapter.from_config(settings) is None


def test_from_config_builds_with_key() -> None:
    settings = Settings.from_env({"NPS_API_KEY": "k"})
    adapter = NpsAlertsAdapter.from_config(settings)
    assert isinstance(adapter, NpsAlertsAdapter)
    assert adapter.kind is ConditionKind.closures


# ── (h) only Closure/Danger survive into value["alerts"] ──


def test_only_closure_and_danger_alerts_survive() -> None:
    parks = [_unit(38.5, -78.4)]
    alerts = [
        _alert("Closure", title="Trail closed"),
        _alert("Caution", title="Bears active"),
        _alert("Danger", title="Flash flood"),
        _alert("Information", title="Visitor center hours"),
    ]
    adapter = NpsAlertsAdapter("key", client=_client(_handler(parks, alerts)))
    fact = adapter.probe(_POINT)
    assert fact is not None
    categories = {a["category"] for a in fact.value["alerts"]}
    assert categories == {"Closure", "Danger"}
    assert fact.value["count"] == 2


# ── capabilities ──


def test_capabilities_shape() -> None:
    caps = NpsAlertsAdapter("key").capabilities()
    assert caps.needs_point is True
    assert caps.needs_site_id is False
    assert caps.is_keyless is False
    assert caps.supports_region == frozenset({"US"})
