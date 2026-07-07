"""Epic 008 harness — /health readiness gating on the /plan warm-up (warm-start lane).

Render gates deploy cutover on healthCheckPath /health. Before this lane, /health
answered 200 the moment settings loaded, so Render cut traffic over to instances
whose /plan dependency stack (Neo4j driver pool, provider SDK clients, the live
adapter registry) was still cold — and the FIRST /plan after every deploy ate the
cold init as a one-off 500. These tests pin the new contract hermetically (no
network, no Aura, no API keys, Epic 008 AC):

  * /health is 503 while warm-up is pending and 200 once a warm round succeeded;
  * a cold-start init failure surfaces in /health (503 + disclosed cause, Rule #1)
    instead of riding the first /plan as a 500 — and /health recovers to 200 when
    the dependency comes back, without a redeploy;
  * the warm round is FREE: it constructs provider clients via warm() but never
    calls complete() — warm-up must not spend tokens.

The conftest `_prewarmed_api` autouse fixture keeps every *other* suite pre-warmed;
tests here install their own state / run the real loop to exercise the gate itself.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

import api.app as app_mod
from orchestration.config import Settings

# ── Test doubles ──────────────────────────────────────────────────────────────


class _StubSession:
    def __init__(self, schema_format_row: Any = "__unset__") -> None:
        self._schema_format_row = schema_format_row

    def run(self, query: Any, params: Any = None) -> list[dict[str, Any]]:
        text = query[0] if isinstance(query, tuple) else query
        if "schema_format" in text and self._schema_format_row != "__unset__":
            if self._schema_format_row is _RAISE:
                raise RuntimeError("schema probe blip (stub)")
            return [{"sf": self._schema_format_row}]
        return []  # /health stats degrade to graph=null — readiness is unaffected


_RAISE = object()  # sentinel: the stubbed schema_format read raises instead of returning


class _WarmGraph:
    """Graph double for the warm-up path: `verify_connectivity` fails `fail_times`
    times (a dependency that is down), then succeeds (it recovered). `schema_format`
    controls what the schema-compatibility probe reads on `scoped_session().run(...)`
    (`"__unset__"` keeps the default no-schema-format stub behavior)."""

    def __init__(self, fail_times: int = 0, schema_format: Any = "__unset__") -> None:
        self.calls = 0
        self.fail_times = fail_times
        self.schema_format = schema_format

    def verify_connectivity(self) -> None:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("connection refused (stub)")

    def scoped_session(self, viewer_id: str) -> _StubSession:
        return _StubSession(self.schema_format)

    def close(self) -> None:  # pragma: no cover - lifespan shutdown
        pass


class _GatedGraph(_WarmGraph):
    """Down until the test flips `recovered` — keeps the failing-/health assertion
    race-free (the loop cannot succeed behind the test's back)."""

    def __init__(self) -> None:
        super().__init__()
        self.recovered = threading.Event()

    def verify_connectivity(self) -> None:
        self.calls += 1
        if not self.recovered.is_set():
            raise RuntimeError("connection refused (stub)")


class _RecorderProvider:
    """Counts warm() vs complete() so a test can prove warm-up never spends tokens."""

    def __init__(self) -> None:
        self.warmed = 0
        self.completed = 0

    def warm(self) -> None:
        self.warmed += 1

    def complete(self, request: Any) -> Any:  # pragma: no cover - must never run
        self.completed += 1
        raise AssertionError("warm-up must never request a completion")


class _Resolution:
    def __init__(self, provider: _RecorderProvider) -> None:
        self.provider = provider


def _install_free_stack(monkeypatch: Any, provider: _RecorderProvider) -> list[tuple[str, bool]]:
    """Stub the provider registry + adapter registry under `_warm_plan_path` so a
    warm round runs with no SDK import and no config requirements; returns the
    (role, touches_private_overlay) pairs the round resolved."""
    resolved: list[tuple[str, bool]] = []

    def fake_resolve(
        role: str, settings: Settings, *, touches_private_overlay: bool = False
    ) -> _Resolution:
        resolved.append((role, touches_private_overlay))
        return _Resolution(provider)

    monkeypatch.setattr(app_mod, "resolve", fake_resolve)
    monkeypatch.setattr(app_mod.registry, "probes_for", lambda region, settings: {})
    return resolved


def _wait_for(predicate: Any, timeout_s: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


_FAST = {"ADVENTURE_WARMUP_DEADLINE_S": "0"}  # fail a down dependency immediately


# ── /health gates on warm-up ──────────────────────────────────────────────────


def test_health_503_while_warming_200_after(monkeypatch: Any) -> None:
    """The Render cutover contract: /health refuses (503) until a warm-up round has
    succeeded, then serves the normal 200 shape."""
    monkeypatch.setattr(app_mod, "_settings", Settings.from_env({}))
    monkeypatch.setattr(app_mod, "_graph_client", _WarmGraph())
    state = app_mod._WarmupState()
    monkeypatch.setattr(app_mod, "_warmup", state)
    client = TestClient(app_mod.app)

    cold = client.get("/health")
    assert cold.status_code == 503
    assert "warming up" in cold.json()["detail"].lower()

    state.ok.set()  # what a successful warm round does
    warm = client.get("/health")
    assert warm.status_code == 200
    assert warm.json()["status"] == "ok"
    assert isinstance(warm.json()["probes_available"], list)


def test_cold_start_failure_surfaces_in_health_and_recovers(monkeypatch: Any) -> None:
    """A dependency that is down at boot surfaces in /health as a 503 with its cause
    disclosed (Rule #1) — Render then keeps traffic on the previous instance, so no
    user's first /plan eats the failure. When the dependency comes back, the loop's
    next round succeeds and /health flips to 200 without a redeploy."""
    provider = _RecorderProvider()
    _install_free_stack(monkeypatch, provider)
    monkeypatch.setattr(app_mod, "_WARMUP_RETRY_PAUSE_S", 0.02)
    graph = _GatedGraph()  # down until the test flips it back
    settings = Settings.from_env(_FAST)
    monkeypatch.setattr(app_mod, "_settings", settings)
    monkeypatch.setattr(app_mod, "_graph_client", graph)
    state = app_mod._WarmupState()
    monkeypatch.setattr(app_mod, "_warmup", state)
    client = TestClient(app_mod.app)

    thread = threading.Thread(
        target=app_mod._warmup_loop, args=(state, settings, graph), daemon=True
    )
    thread.start()
    try:
        # The failure is REPORTED (bounded round, not a hang) and disclosed verbatim.
        assert _wait_for(lambda: state.error is not None)
        failing = client.get("/health")
        assert failing.status_code == 503
        assert "RuntimeError" in failing.json()["detail"]

        # The dependency recovers → a later round succeeds → ready, error cleared.
        graph.recovered.set()
        assert _wait_for(state.ok.is_set)
        assert state.error is None
        assert client.get("/health").status_code == 200
    finally:
        state.stop.set()
        thread.join(timeout=2)


# ── The warm round itself ─────────────────────────────────────────────────────


def test_warm_round_covers_plan_stack_without_spending_tokens(monkeypatch: Any) -> None:
    """One round touches every lazily-built /plan dependency — the graph driver, the
    exact three provider resolutions build_runtime performs (including the
    privacy-routed personalized judge), and the adapter registry — and constructs
    provider clients via warm() only: complete() is never called (no token spend)."""
    provider = _RecorderProvider()
    resolved = _install_free_stack(monkeypatch, provider)
    graph = _WarmGraph()
    state = app_mod._WarmupState()

    app_mod._warm_plan_path(state, Settings.from_env(_FAST), graph)

    assert graph.calls == 1
    assert resolved == [("extract", False), ("curate", False), ("curate", True)]
    assert provider.warmed == 3
    assert provider.completed == 0  # warm-up is free by contract
    assert state.probe_keys == []  # stubbed registry → recorded for /health


def test_warm_round_retries_graph_within_deadline(monkeypatch: Any) -> None:
    """A graph that blips once during the round's budget is retried and the round
    still succeeds — the deadline bounds a slow-but-alive Aura, it doesn't turn one
    transient refusal into a failed deploy round."""
    provider = _RecorderProvider()
    _install_free_stack(monkeypatch, provider)
    graph = _WarmGraph(fail_times=1)
    state = app_mod._WarmupState()
    settings = Settings.from_env({"ADVENTURE_WARMUP_DEADLINE_S": "5"})

    app_mod._warm_plan_path(state, settings, graph)

    assert graph.calls == 2  # failed once, retried within the budget, succeeded


# ── Schema-format compatibility gate (Epic 024) ───────────────────────────────


def test_verify_schema_format_refuses_newer_graph() -> None:
    graph = _WarmGraph(schema_format=app_mod.EXPECTED_SCHEMA_FORMAT + 1)
    with pytest.raises(app_mod.SchemaFormatError) as exc_info:
        app_mod._verify_schema_format(graph)
    message = str(exc_info.value)
    assert str(app_mod.EXPECTED_SCHEMA_FORMAT + 1) in message
    assert str(app_mod.EXPECTED_SCHEMA_FORMAT) in message


@pytest.mark.parametrize(
    "schema_format",
    [
        pytest.param("EXPECTED", id="equal"),
        pytest.param("EXPECTED_MINUS_1", id="older"),
        pytest.param(None, id="absent-legacy-graph"),
        pytest.param(_RAISE, id="read-raises"),
    ],
)
def test_verify_schema_format_proceeds_without_refusal(schema_format: Any) -> None:
    if schema_format == "EXPECTED":
        schema_format = app_mod.EXPECTED_SCHEMA_FORMAT
    elif schema_format == "EXPECTED_MINUS_1":
        schema_format = app_mod.EXPECTED_SCHEMA_FORMAT - 1
    graph = _WarmGraph(schema_format=schema_format)
    app_mod._verify_schema_format(graph)  # must not raise


def test_warm_round_refuses_newer_schema_format(monkeypatch: Any) -> None:
    """AC-3.1/3.4: a confirmed-newer graph schema_format fails the warm round with
    both numbers in the message; AC-3.3: it's a plain exception, never a crash."""
    provider = _RecorderProvider()
    _install_free_stack(monkeypatch, provider)
    graph = _WarmGraph(schema_format=app_mod.EXPECTED_SCHEMA_FORMAT + 1)
    state = app_mod._WarmupState()

    with pytest.raises(app_mod.SchemaFormatError):
        app_mod._warm_plan_path(state, Settings.from_env(_FAST), graph)

    # Providers never ran — the schema gate raised before that stage of the round.
    assert provider.warmed == 0


def test_health_503_discloses_incompatible_schema_format_and_status_still_responds(
    monkeypatch: Any,
) -> None:
    """AC-3.3/3.4: the incompatibility surfaces on /health as a disclosed 503 naming
    both integers, never a dropped connection — and /status keeps responding."""
    provider = _RecorderProvider()
    _install_free_stack(monkeypatch, provider)
    monkeypatch.setattr(app_mod, "_WARMUP_RETRY_PAUSE_S", 0.02)
    graph = _WarmGraph(schema_format=app_mod.EXPECTED_SCHEMA_FORMAT + 1)
    settings = Settings.from_env(_FAST)
    monkeypatch.setattr(app_mod, "_settings", settings)
    monkeypatch.setattr(app_mod, "_graph_client", graph)
    state = app_mod._WarmupState()
    monkeypatch.setattr(app_mod, "_warmup", state)
    client = TestClient(app_mod.app)

    thread = threading.Thread(
        target=app_mod._warmup_loop, args=(state, settings, graph), daemon=True
    )
    thread.start()
    try:
        assert _wait_for(lambda: state.error is not None)
        health = client.get("/health")
        assert health.status_code == 503
        detail = health.json()["detail"]
        assert str(app_mod.EXPECTED_SCHEMA_FORMAT + 1) in detail
        assert str(app_mod.EXPECTED_SCHEMA_FORMAT) in detail

        status = client.get("/status")
        assert status.status_code == 200
    finally:
        state.stop.set()
        thread.join(timeout=2)
