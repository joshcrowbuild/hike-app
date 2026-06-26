"""Endpoint test for Epic 002 — AC-4.3.

`POST /episode/{id}/outcome` must drain the belief-update queue as a FastAPI
BackgroundTask *after* the response is sent, never synchronously in the request
path (AC-4.3 / S6 §4.1 queue discipline). This test exercises the real endpoint
wiring with a fake GraphClient (no live Neo4j).

Discriminating the invariant requires watching the *scheduling boundary*, not the
event order: an inline `_drain_queue_bg(...)` call also runs after the write that
populates the queue, so a 'write' → 'drain' order alone cannot tell a scheduled
drain from a synchronous one (Starlette's TestClient runs background tasks to
completion inside the client call). So this test spies on
`BackgroundTasks.add_task`: the drain must be *registered* as a background task and
must NOT be invoked inline before it is scheduled. Under the correct impl the event
stream is ['write', schedule(_drain_queue_bg), 'drain']; under the forbidden
synchronous regression `add_task` is never called for the drain, so the 'schedule'
marker is absent and this test goes red.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fastapi import BackgroundTasks
from fastapi.testclient import TestClient

import api.app as app_mod
from api.app import app
from orchestration.config import Settings


class _FakeScopedSession:
    """Records the episode-ownership read (returns 'exists') and the owned-write
    batch, appending a 'write' marker so the test can assert write-then-drain order."""

    def __init__(self, events: list[Any], viewer_id: str) -> None:
        self.events = events
        self.viewer_id = viewer_id

    def run(self, query: tuple[str, dict[str, Any]]) -> list[dict[str, Any]]:
        cypher, params = query
        if "Episode" in cypher and "RETURN" in cypher:
            return [{"episode_id": params.get("eid")}]  # episode belongs to viewer
        return []

    def execute_write(self, batch: Sequence[tuple[str, dict[str, Any]]]) -> None:
        self.events.append("write")


class _FakeGraphClient:
    def __init__(self, events: list[Any]) -> None:
        self.events = events

    def scoped_session(self, viewer_id: str, granted_ids: Sequence[str] = ()) -> _FakeScopedSession:
        return _FakeScopedSession(self.events, viewer_id)

    def close(self) -> None:  # pragma: no cover - lifespan shutdown
        pass


def test_s4_ac3_drain_registered_as_background_task_not_run_inline(monkeypatch) -> None:
    """AC-4.3: the belief-queue drain is *registered* via BackgroundTasks.add_task (so it
    runs after the response) and is never invoked inline in the request path. The test
    watches the scheduling boundary — order alone cannot distinguish a scheduled drain
    from a synchronous one — so it goes red if a refactor drains the queue inline."""
    events: list[Any] = []

    def _spy_drain(queue: Any, graph_client: Any) -> None:
        events.append(("drain", queue.size()))

    original_add_task = BackgroundTasks.add_task

    def _spy_add_task(self: BackgroundTasks, func: Any, *args: Any, **kwargs: Any) -> None:
        events.append(("schedule", func))
        original_add_task(self, func, *args, **kwargs)

    with TestClient(app) as client:
        app_mod._settings = Settings.from_env({})
        app_mod._graph_client = _FakeGraphClient(events)  # type: ignore[assignment]
        monkeypatch.setattr(app_mod, "_drain_queue_bg", _spy_drain)
        monkeypatch.setattr(BackgroundTasks, "add_task", _spy_add_task)
        # viewer_id defaults to "anonymous" → passes the auth guard; overall=2 (>=2,
        # non-skipped) → enqueues the preference-check marker.
        r = client.post("/episode/ep:anon:1/outcome", json={"overall": 2, "skipped": False})

    assert r.status_code == 200
    assert r.json()["episode_id"] == "ep:anon:1"

    markers = [e if isinstance(e, str) else e[0] for e in events]
    # The drain function was registered as a background task (NOT called inline). This is
    # the discriminator: under a synchronous-drain regression, add_task is never called for
    # the drain, so no 'schedule' marker exists and this assertion fails.
    sched_idx = [
        i
        for i, e in enumerate(events)
        if isinstance(e, tuple) and e[0] == "schedule" and e[1] is app_mod._drain_queue_bg
    ]
    assert sched_idx, "drain must be registered via BackgroundTasks.add_task, not run inline"
    # The synchronous write committed before the drain was even scheduled.
    assert "write" in markers and markers.index("write") < sched_idx[0]
    # The drain never ran before it was scheduled (no inline invocation slipped in first).
    drain_idxs = [i for i, m in enumerate(markers) if m == "drain"]
    assert all(i > sched_idx[0] for i in drain_idxs)
    # And the scheduled drain actually ran after the response, seeing the post-write queue
    # with exactly one enqueued preference-check marker (overall>=2).
    drain_calls = [e for e in events if isinstance(e, tuple) and e[0] == "drain"]
    assert drain_calls and drain_calls[0][1] == 1
