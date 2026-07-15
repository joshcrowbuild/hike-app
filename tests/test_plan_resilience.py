"""End-to-end /plan resilience (reliability lane) — hermetic, no Aura, no keys.

Ties the two hardened paths to the endpoint contract the frontend depends on:

  * a transient graph blip on a CORE read self-heals → /plan 200 (had the read used bare
    session.run instead of the managed read transaction, the same blip would 500);
  * a transient provider blip self-heals through the seam's retry → /plan 200;
  * a genuinely unrecoverable failure (retries exhausted, or a non-transient error) returns
    a clean, TYPED 500 the frontend's classify() maps to kind:"server" — never an unhandled
    crash — and carries a correlation id header; a non-transient error is not retried.

The engine is stubbed to a thin `plan` that performs exactly one real graph read or one
real provider call through the injected fault-injecting double, so the assertions ride the
real runner (graph/client.py) and the real provider seam.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient

import api.app as app_mod
from graph.client import GraphClient
from orchestration.config import Settings

# Doubles reused from the per-unit suites (no anthropic import → runs in the base test env):
# a driver stub raising is_retryable()-shaped errors, and a duck-typed provider status error
# (the seam keys retry on .status_code, so this drives it identically to a real SDK error).
from tests.test_graph_resilience import _NonRetryable, _StubDriver
from tests.test_provider_retry import _DuckStatusError

_PLAN_BODY = {"query": "something mellow", "lat": 38.5, "lon": -78.4}


@pytest.fixture(autouse=True)
def _no_real_backoff(monkeypatch: Any) -> None:
    # Both the graph runner's retry and the provider seam's resolve time.sleep at call time;
    # neutralize it so the suite neither waits nor flakes on backoff timing.
    monkeypatch.setattr(time, "sleep", lambda _s: None)


# ── Minimal feed shapes (what _feed_response reads off engine.plan's return) ─────


@dataclass
class _Line:
    text: str
    source: str
    presentation: str = "stated"
    sources: list[str] = field(default_factory=list)
    # Epic 045 S1: `FeedLineResponse`/`_condition_fields` now read `body`/`age`
    # too; defaulted so this file's existing call sites are unaffected — these
    # tests assert wire SHAPE, not `body`/`age` content.
    body: str = ""
    age: str = ""


@dataclass
class _Card:
    canonical_id: str
    name: str
    distance_mi: float | None
    lines: list[_Line] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unavailable: list[str] = field(default_factory=list)
    conditions: list[object] = field(default_factory=list)


@dataclass
class _Feed:
    query: str
    cards: list[_Card]
    notices: tuple[str, ...] = ()
    set_aside: tuple[object, ...] = ()


class _Runtime:
    cache = None


def _install(monkeypatch: Any, graph_client: Any, plan_impl: Any) -> TestClient:
    """A TestClient whose /plan runs `plan_impl` as the engine and reads through
    `graph_client`. Singletons are overridden AFTER lifespan startup (no live Aura)."""
    monkeypatch.setattr(app_mod, "build_runtime", lambda *a, **k: _Runtime())
    monkeypatch.setattr("orchestration.engine.plan", plan_impl)
    monkeypatch.setattr(app_mod, "_fetch_maps_by_canonical", lambda session, ids: {})
    client = TestClient(app_mod.app)
    client.__enter__()
    monkeypatch.setattr(app_mod, "_settings", Settings.from_env({}))
    monkeypatch.setattr(app_mod, "_graph_client", graph_client)
    return client


def _graph_client_with(driver: _StubDriver) -> GraphClient:
    gc = GraphClient("bolt://stub", "neo4j", "pw")
    gc._driver = driver
    return gc


def _plan_that_reads(query: str, origin: Any, runtime: Any, **kwargs: Any) -> _Feed:
    """Engine stand-in that performs ONE core graph read through the injected runner."""
    app_mod._graph_client.scoped_session("anonymous").run(("MATCH (n) RETURN n LIMIT 1", {}))
    return _Feed(query=query, cards=[_Card("ct:loop", "Loop", 4.2, [_Line("ok", "usgs")])])


# ── Graph path ──────────────────────────────────────────────────────────────────


def test_plan_200_when_graph_read_recovers_from_transient(monkeypatch: Any) -> None:
    driver = _StubDriver(rows=[{"n": 1}], fail_times=1)  # transient once, then success
    client = _install(monkeypatch, _graph_client_with(driver), _plan_that_reads)
    try:
        resp = client.post("/plan", json=_PLAN_BODY)
    finally:
        client.__exit__(None, None, None)

    assert resp.status_code == 200  # runner retried on a fresh connection → self-healed
    assert resp.json()["cards"][0]["canonical_id"] == "ct:loop"
    assert len(driver.calls) == 2  # one failed attempt, one success


def test_plan_500_typed_when_graph_read_persistently_fails(monkeypatch: Any) -> None:
    driver = _StubDriver(fail_times=99)  # never recovers
    client = _install(monkeypatch, _graph_client_with(driver), _plan_that_reads)
    try:
        resp = client.post("/plan", json=_PLAN_BODY)
    finally:
        client.__exit__(None, None, None)

    # A clean, typed 5xx the frontend classify() maps to kind:"server" — not a crash.
    assert resp.status_code == 500
    assert resp.json() == {"detail": "Internal error"}
    assert resp.headers.get("X-Correlation-Id")  # residual 500 is greppable
    assert len(driver.calls) == 3  # retried up to the budget before giving up


def test_plan_does_not_retry_non_transient_graph_error(monkeypatch: Any) -> None:
    driver = _StubDriver(fail_times=1, fail_kind=_NonRetryable)  # e.g. a bad-Cypher ClientError
    client = _install(monkeypatch, _graph_client_with(driver), _plan_that_reads)
    try:
        resp = client.post("/plan", json=_PLAN_BODY)
    finally:
        client.__exit__(None, None, None)

    assert resp.status_code == 500
    assert resp.json() == {"detail": "Internal error"}
    assert len(driver.calls) == 1  # surfaced immediately — never retried


# ── Provider path ───────────────────────────────────────────────────────────────


class _FlakyAnthropic:
    def __init__(self, errors: list[Exception]) -> None:
        self._errors = list(errors)
        self.calls = 0
        self.messages = self

    def create(self, **kw: Any) -> Any:
        self.calls += 1
        if self._errors:
            raise self._errors.pop(0)

        class _O:
            def __init__(self, **k: Any) -> None:
                self.__dict__.update(k)

        return _O(content=[_O(type="text", text="ok")], model=kw["model"], usage=None)


def _plan_that_calls_provider(errors: list[Exception]) -> Any:
    fake = _FlakyAnthropic(errors)

    def _plan(query: str, origin: Any, runtime: Any, **kwargs: Any) -> _Feed:
        from orchestration.providers.anthropic_claude import AnthropicProvider
        from orchestration.providers.base import LLMRequest

        AnthropicProvider("key", client=fake).complete(
            LLMRequest(system="s", messages=[{"role": "user", "content": "hi"}], model="m")
        )
        return _Feed(query=query, cards=[_Card("ct:loop", "Loop", 4.2)])

    _plan.fake = fake  # type: ignore[attr-defined]
    return _plan


def test_plan_200_when_provider_recovers_from_transient(monkeypatch: Any) -> None:
    plan_impl = _plan_that_calls_provider([_DuckStatusError(529)])  # overloaded, then success
    client = _install(monkeypatch, _graph_client_with(_StubDriver()), plan_impl)
    try:
        resp = client.post("/plan", json=_PLAN_BODY)
    finally:
        client.__exit__(None, None, None)

    assert resp.status_code == 200  # provider retry self-healed
    assert plan_impl.fake.calls == 2


def test_plan_500_typed_when_provider_persistently_overloaded(monkeypatch: Any) -> None:
    plan_impl = _plan_that_calls_provider([_DuckStatusError(529) for _ in range(3)])
    client = _install(monkeypatch, _graph_client_with(_StubDriver()), plan_impl)
    try:
        resp = client.post("/plan", json=_PLAN_BODY)
    finally:
        client.__exit__(None, None, None)

    assert resp.status_code == 500
    assert resp.json() == {"detail": "Internal error"}
    assert resp.headers.get("X-Correlation-Id")
    assert plan_impl.fake.calls == 3  # bounded attempts, then the real cause → typed 5xx
