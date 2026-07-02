"""Per-IP rate limiting + plan observability at the public edge (Phase B).

`/plan` fans out to live APIs and an LLM with real per-call cost; without a per-IP bound
a single client can drain budget (the R5 abuse gap). These assert the happy path still
serves a 200 and that the (N+1)th call inside the window gets a clean JSON 429 — with the
graph + engine mocked so the suite needs no live Aura.

The observability test asserts the structured plan line is emitted and, critically, that
viewer_id never appears in the clear (Rule #5).
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

import api.app as app_mod
from orchestration.config import Settings


@dataclass
class _Line:
    text: str
    source: str
    presentation: str = "stated"


@dataclass
class _Card:
    canonical_id: str
    name: str
    distance_mi: float | None
    lines: list[_Line]
    warnings: list[str] = field(default_factory=list)


@dataclass
class _Feed:
    query: str
    cards: list[_Card]
    notices: tuple[str, ...] = ()
    set_aside: tuple[object, ...] = ()


class _Runtime:
    cache = None  # cache_size() reads 0 off this; no live probe cache in the test


class _StubGraph:
    """A graph client that never touches Neo4j: scoped_session is unused because the maps
    batch read is stubbed out below."""

    def scoped_session(self, viewer_id: str) -> object:
        return object()

    def close(self) -> None:  # pragma: no cover - lifespan shutdown
        pass


def _canned_feed(query: str, origin: object, runtime: object, **kwargs: object) -> _Feed:
    return _Feed(
        query=query,
        cards=[
            _Card(
                canonical_id="t1",
                name="Mellow Loop",
                distance_mi=4.2,
                lines=[_Line(text="Stream is flowing", source="usgs")],
            )
        ],
    )


@contextmanager
def _stubbed_client(monkeypatch, asgi_app) -> Iterator[TestClient]:
    """A TestClient over `asgi_app` with settings, a stub graph, and the engine/maps
    mocked so /plan returns a 200 without any live call."""
    monkeypatch.setattr(app_mod, "build_runtime", lambda *a, **k: _Runtime())
    monkeypatch.setattr("orchestration.engine.plan", _canned_feed)
    monkeypatch.setattr(app_mod, "_fetch_maps_by_canonical", lambda session, ids: {})
    c = TestClient(asgi_app)
    c.__enter__()
    # Override the lifespan-wired singletons with test doubles (no live Aura).
    monkeypatch.setattr(app_mod, "_settings", Settings.from_env({}))
    monkeypatch.setattr(app_mod, "_graph_client", _StubGraph())
    try:
        yield c
    finally:
        c.__exit__(None, None, None)


@pytest.fixture
def client(monkeypatch) -> Iterator[TestClient]:
    with _stubbed_client(monkeypatch, app_mod.app) as c:
        yield c


@pytest.fixture
def proxied_client(monkeypatch) -> Iterator[TestClient]:
    """The app behind uvicorn's real ProxyHeadersMiddleware with the same trust setting
    as the production serve command (`--proxy-headers --forwarded-allow-ips='*'`, see the
    Dockerfile CMD): request.client is rewritten to the first X-Forwarded-For entry before
    slowapi keys on it, exactly as behind Render's proxy."""
    with _stubbed_client(monkeypatch, ProxyHeadersMiddleware(app_mod.app, trusted_hosts="*")) as c:
        yield c


_PLAN_BODY = {"query": "something mellow", "lat": 38.5, "lon": -78.4}


def test_plan_happy_path_returns_200(client) -> None:
    resp = client.post("/plan", json=_PLAN_BODY)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["card_count"] == 1
    assert payload["cards"][0]["canonical_id"] == "t1"


def test_plan_rate_limited_returns_clean_429(client, monkeypatch) -> None:
    # A wide window ("/hour") so three quick requests can't straddle a window reset and
    # flake; the count, not the clock, is what trips here.
    monkeypatch.setenv("ADVENTURE_RATELIMIT_PLAN", "2/hour")

    ok1 = client.post("/plan", json=_PLAN_BODY)
    ok2 = client.post("/plan", json=_PLAN_BODY)
    limited = client.post("/plan", json=_PLAN_BODY)

    assert ok1.status_code == 200
    assert ok2.status_code == 200
    assert limited.status_code == 429
    # Clean JSON envelope mirroring the rest of the API, not slowapi's bare-text default.
    assert "detail" in limited.json()
    assert "rate limit" in limited.json()["detail"].lower()
    # The advertised back-off contract: a 429 carries Retry-After so a client backs off.
    assert "retry-after" in {k.lower() for k in limited.headers}


def test_plan_buckets_are_keyed_per_forwarded_client_ip(proxied_client, monkeypatch) -> None:
    # Behind Render's proxy the TCP peer is the proxy for every request; without the
    # proxy-header rewrite all clients share ONE bucket and the second client below would
    # get a 429 off the first client's traffic. With the production middleware + trust
    # setting, exhausting client A's bucket must leave client B's untouched.
    monkeypatch.setenv("ADVENTURE_RATELIMIT_PLAN", "1/hour")

    xff_a = {"X-Forwarded-For": "203.0.113.10"}
    xff_b = {"X-Forwarded-For": "203.0.113.20"}
    a_ok = proxied_client.post("/plan", json=_PLAN_BODY, headers=xff_a)
    a_limited = proxied_client.post("/plan", json=_PLAN_BODY, headers=xff_a)
    b_ok = proxied_client.post("/plan", json=_PLAN_BODY, headers=xff_b)

    assert a_ok.status_code == 200
    assert a_limited.status_code == 429  # client A exhausted its own bucket...
    assert b_ok.status_code == 200  # ...without spending from client B's


def test_health_rate_limited_returns_429(client, monkeypatch) -> None:
    monkeypatch.setenv("ADVENTURE_RATELIMIT_HEALTH", "1/hour")
    assert client.get("/health").status_code == 200
    assert client.get("/health").status_code == 429


def test_outcome_write_endpoint_is_rate_limited(client, monkeypatch) -> None:
    # The graph-write + background-drain path must be bounded too (the same R5 gap on an
    # adjacent endpoint). A 404 still counts against the limiter — the limit fires before
    # the route body — so we can prove the bound without a real episode.
    monkeypatch.setenv("ADVENTURE_RATELIMIT_OUTCOME", "1/hour")
    body = {"overall": 4}
    first = client.post("/episode/ep-unknown/outcome", json=body)
    second = client.post("/episode/ep-unknown/outcome", json=body)
    assert first.status_code != 429  # first call reaches the route (404/422/etc.)
    assert second.status_code == 429  # second is bounded


def test_plan_observability_scrubs_viewer_id(client, monkeypatch, caplog) -> None:
    # A real (non-anonymous) viewer must be authorized; configure the dev secret so the
    # request reaches the engine, then assert the identity never lands in the logs.
    monkeypatch.setattr(
        app_mod, "_settings", Settings.from_env({"ADVENTURE_DEV_VIEWER_SECRET": "s3cret"})
    )
    secret_viewer = "josh@example.com"

    with caplog.at_level(logging.INFO, logger="api.observability"):
        resp = client.post(
            "/plan",
            json={**_PLAN_BODY, "viewer_id": secret_viewer},
            headers={"X-Dev-Viewer-Secret": "s3cret"},
        )

    assert resp.status_code == 200
    records = [r for r in caplog.records if r.name == "api.observability"]
    assert records, "expected a structured plan observability line"
    line = records[-1].getMessage()
    assert "latency_ms=" in line and "est_tokens=" in line and "est_cost_usd=" in line
    assert secret_viewer not in line  # Rule #5: viewer_id never logged in the clear
    assert "vh:" in line  # …only a short non-reversible digest
