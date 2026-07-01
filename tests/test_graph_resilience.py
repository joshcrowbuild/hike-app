"""Graph driver + query resilience (reliability lane) — hermetic, no live Neo4j.

The public /plan endpoint intermittently 500'd on a stale Aura connection (Aura
server-side-closes idle connections; the driver's first query on a pooled-but-dead
connection throws before it reconnects). The fix, exercised here:

  * a READ (`run`) is wrapped in a bounded transient-retry keyed on the driver's own
    `is_retryable()`, so a ServiceUnavailable / SessionExpired / TransientError self-heals
    on a fresh connection instead of surfacing a 500 (the /plan hot path);
  * a single WRITE (`run_write`) is deliberately NOT retried — an autocommit write that
    dies post-commit-pre-ack raises a *retryable* error (not IncompleteCommit), and
    retrying a non-idempotent owned write would double-apply it;
  * the driver is built with pool config that keeps a connection from outliving Aura's
    ~300s idle close.

Faithfulness: the driver is stubbed, but the stub raises the SAME `is_retryable()`-shaped
errors the real driver raises on a dead connection, so a read test that recovers proves the
runner's retry (had `run` executed the statement once, the transient would propagate). The
$viewer_id/$granted_ids scope merge is asserted untouched (rule #4).
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from graph.client import GraphClient


class _Retryable(Exception):
    """Stand-in for ServiceUnavailable / SessionExpired / TransientError (driver-retryable)."""

    def is_retryable(self) -> bool:
        return True


class _NonRetryable(Exception):
    """Stand-in for a ClientError (bad Cypher, constraint violation) — never retried."""

    def is_retryable(self) -> bool:
        return False


class _Rec:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def data(self) -> dict[str, Any]:
        return self._data


class _Session:
    def __init__(self, driver: "_StubDriver") -> None:
        self._driver = driver

    def __enter__(self) -> "_Session":
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False

    def run(self, cypher: str, **params: Any) -> list[_Rec]:
        return self._driver._dispatch(cypher, params)


class _StubDriver:
    """Scripts per-attempt behavior for `session.run`: the first `fail_times` calls raise
    `fail_kind`, then it returns `rows`. Records every (cypher, params) so scope-merge and
    attempt-count can be asserted. Each `session()` is a fresh connection — exactly what the
    runner's retry acquires after a stale one."""

    def __init__(
        self,
        rows: list[dict[str, Any]] | None = None,
        *,
        fail_times: int = 0,
        fail_kind: type[Exception] = _Retryable,
    ) -> None:
        self._rows = rows if rows is not None else [{"ok": 1}]
        self._fail_times = fail_times
        self._fail_kind = fail_kind
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.closed = False

    def session(self, **_: Any) -> _Session:
        return _Session(self)

    def _dispatch(self, cypher: str, params: dict[str, Any]) -> list[_Rec]:
        self.calls.append((cypher, params))
        if len(self.calls) <= self._fail_times:
            raise self._fail_kind("blip" if self._fail_kind is _Retryable else "bad query")
        return [_Rec(dict(r)) for r in self._rows]

    def close(self) -> None:
        self.closed = True


def _client_with(driver: _StubDriver) -> GraphClient:
    client = GraphClient("bolt://stub", "neo4j", "pw")
    client._driver = driver  # inject the stub; _ensure_driver() returns it as-is
    return client


@pytest.fixture(autouse=True)
def _no_real_backoff(monkeypatch: Any) -> None:
    # The runner's retry resolves time.sleep at call time; keep the suite fast/deterministic.
    monkeypatch.setattr(time, "sleep", lambda _s: None)


# ── Reads: a transient first attempt is auto-recovered ──────────────────────────


def test_read_recovers_after_one_transient_error() -> None:
    driver = _StubDriver(rows=[{"n": 1}], fail_times=1)  # first run raises, then ok
    session = _client_with(driver).scoped_session("anonymous")

    rows = session.run(("MATCH (n) RETURN n", {}))

    assert rows == [{"n": 1}]  # recovered — the runner retried on a fresh connection
    assert len(driver.calls) == 2  # one failed attempt + one success


def test_read_merges_scope_untouched_by_retry() -> None:
    driver = _StubDriver(rows=[{"n": 1}])
    session = _client_with(driver).scoped_session("mem:josh", ["mem:ruby"])

    session.run(("MATCH (e) WHERE e.owner_id = $viewer_id RETURN e", {"extra": 7}))

    _, params = driver.calls[0]
    # Access control preserved: the runner merged the viewer scope, untouched (rule #4).
    assert params["viewer_id"] == "mem:josh"
    assert params["granted_ids"] == ["mem:ruby"]
    assert params["extra"] == 7


def test_read_reraises_persistent_transient_after_budget() -> None:
    driver = _StubDriver(fail_times=99)  # every attempt is transient → never recovers
    session = _client_with(driver).scoped_session("anonymous")

    with pytest.raises(_Retryable):
        session.run(("MATCH (n) RETURN n", {}))
    assert len(driver.calls) == 3  # bounded to _RETRY_MAX_ATTEMPTS, then it gives up


def test_read_does_not_retry_non_transient_error() -> None:
    driver = _StubDriver(fail_times=1, fail_kind=_NonRetryable)
    session = _client_with(driver).scoped_session("anonymous")

    with pytest.raises(_NonRetryable):
        session.run(("MATCH (n) RETURN bad", {}))
    assert len(driver.calls) == 1  # a client error is surfaced immediately, never retried


# ── Writes: a single owned write is NOT retried (post-commit-ack double-write hazard) ──


def test_run_write_is_not_retried_on_transient() -> None:
    # An autocommit write that dies in the post-commit ack window raises a *retryable*
    # error (not IncompleteCommit); retrying would double-apply a non-idempotent write (e.g.
    # episode_count = ...+1). So run_write must NOT auto-retry — the transient propagates on a
    # single attempt, exactly as before the reliability lane. (Atomic batches get their retry
    # from the managed execute_write path instead.)
    driver = _StubDriver(fail_times=1)
    session = _client_with(driver).scoped_session("mem:josh")

    cypher = "MERGE (b:Belief {owner_id: $viewer_id, belief_id: $bid}) RETURN b.belief_id"
    with pytest.raises(_Retryable):
        session.run_write((cypher, {"bid": "b1"}))
    assert len(driver.calls) == 1  # never retried — no double-execution


def test_run_write_happy_path_executes_once() -> None:
    driver = _StubDriver(rows=[{"belief_id": "b1"}])
    session = _client_with(driver).scoped_session("mem:josh")

    cypher = (
        "MERGE (b:Belief {owner_id: $viewer_id, belief_id: $bid}) RETURN b.belief_id AS belief_id"
    )
    rows = session.run_write((cypher, {"bid": "b1"}))

    assert rows == [{"belief_id": "b1"}]
    assert len(driver.calls) == 1  # a healthy write is a plain single autocommit


# ── Driver pool config: recycle before Aura's ~300s idle close ──────────────────


def test_driver_built_with_resilience_config(monkeypatch: Any) -> None:
    # neo4j is a lazy/optional dep absent from the base test env; inject a fake module so
    # `import neo4j` inside _ensure_driver picks it up and we capture the driver kwargs
    # without the package (keeps this a hermetic DB-free unit test).
    import sys
    import types

    captured: dict[str, Any] = {}

    class _D:
        def close(self) -> None:
            pass

    def _spy(uri: str, **kwargs: Any) -> _D:
        captured["uri"] = uri
        captured.update(kwargs)
        return _D()

    fake_neo4j = types.ModuleType("neo4j")
    fake_neo4j.GraphDatabase = type("_GDB", (), {"driver": staticmethod(_spy)})  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "neo4j", fake_neo4j)

    GraphClient("bolt://x", "u", "p")._ensure_driver()

    assert captured["auth"] == ("u", "p")
    # Must recycle a pooled connection before Aura server-side-closes it (~300s).
    assert captured["max_connection_lifetime"] <= 300
    assert captured["liveness_check_timeout"] is not None
    assert captured["connection_acquisition_timeout"] > 0
    # Managed-transaction retry budget (used by the write batch path) stays under /plan's 60s.
    assert 0 < captured["max_transaction_retry_time"] < 60


def test_verify_connectivity_delegates_to_driver() -> None:
    class _ConnDriver:
        def __init__(self) -> None:
            self.checked = False

        def verify_connectivity(self) -> None:
            self.checked = True

    driver = _ConnDriver()
    client = GraphClient("bolt://stub", "u", "p")
    client._driver = driver
    client.verify_connectivity()
    assert driver.checked
