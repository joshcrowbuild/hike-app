"""Degrade-and-disclose: the API logs the real cause before degrading (Epic R7).

Silently swallowing exceptions (graph stats → null, /plan → generic 500) hid both a
Cypher-25 bug and a missing-provider crash. These assert the graceful degrade is
preserved (Rule #1) AND that the cause is logged server-side, not swallowed.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi.testclient import TestClient

import api.app as app_mod
from orchestration.config import Settings


class _NoopClient:
    def close(self) -> None:  # pragma: no cover - lifespan shutdown
        pass


def test_graph_stats_logs_and_degrades_on_error(monkeypatch, caplog) -> None:
    class _BoomSession:
        def run(self, query: object) -> object:
            raise RuntimeError("cypher boom")

    class _BoomClient:
        def scoped_session(self, viewer_id: str) -> _BoomSession:
            return _BoomSession()

    monkeypatch.setattr(app_mod, "_graph_client", _BoomClient())
    monkeypatch.setattr(app_mod, "_settings", Settings.from_env({}))

    with caplog.at_level(logging.ERROR, logger="api.app"):
        result = app_mod._graph_stats()

    assert result is None  # graceful degrade preserved (Rule #1: graph=null, not a 500)
    assert any(r.levelname == "ERROR" and r.exc_info for r in caplog.records)  # but disclosed


def test_plan_logs_cause_and_returns_generic_500(monkeypatch, caplog) -> None:
    def _boom(*args: object, **kwargs: object) -> object:
        raise RuntimeError("provider missing boom")

    monkeypatch.setattr(app_mod, "build_runtime", _boom)

    client = TestClient(app_mod.app)
    client.__enter__()
    monkeypatch.setattr(app_mod, "_settings", Settings.from_env({}))
    monkeypatch.setattr(app_mod, "_graph_client", _NoopClient())
    try:
        with caplog.at_level(logging.ERROR, logger="api.app"):
            resp = client.post("/plan", json={"query": "loop", "lat": 38.5, "lon": -78.4})
    finally:
        client.__exit__(None, None, None)

    assert resp.status_code == 500
    assert resp.json()["detail"] == "Internal error"  # generic to the client...
    # ...but the real cause is logged server-side with a traceback.
    records = [r for r in caplog.records if r.levelname == "ERROR" and r.exc_info]
    assert records, "expected an ERROR log with a traceback"
    # The log carries the exception CLASS + a correlation id (reliability lane), and the
    # same id rides back in a header so the residual 500 is one grep away in Render logs.
    message = records[0].getMessage()
    assert "error_class=RuntimeError" in message
    assert "cid=" in message
    correlation_id = resp.headers.get("X-Correlation-Id")
    assert correlation_id and correlation_id in message


def test_generic_exception_handler_never_leaks_exception_text(caplog) -> None:
    # H2: the last-resort handler must return a constant body — never str(exc), which
    # can carry internals (paths, query fragments, library internals, rule #10).
    async def _raise_and_handle() -> object:
        try:
            raise RuntimeError("password=hunter2 at /internal/db/host:5432")
        except RuntimeError as exc:
            return await app_mod.generic_exception_handler(None, exc)

    with caplog.at_level(logging.ERROR, logger="api.app"):
        response = asyncio.run(_raise_and_handle())

    assert response.status_code == 500
    body = response.body.decode("utf-8")
    assert body == '{"detail":"Internal error"}'
    assert "hunter2" not in body
    # ...but the real cause is still logged server-side with a traceback.
    records = [r for r in caplog.records if r.levelname == "ERROR" and r.exc_info]
    assert records, "expected an ERROR log with a traceback"
