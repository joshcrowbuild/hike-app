"""Epic 040 — the two-phase wire contract (`/plan` phase:"cards" + `/plan/conditions`).

Hermetic like tests/test_api_endpoints.py: the graph client is a stub, the engine's
two-phase functions are canned, no network or provider is ever touched. Covers:

  * `/plan` with phase:"cards" routes to `plan_cards` and self-describes
    `conditions_complete` honestly (False on a phase-1 response, True when the
    engine served a warm full plan);
  * the server kill switch (ADVENTURE_TWO_PHASE_ENABLED=0) makes phase:"cards"
    serve the classic single-pass response (D6);
  * `phase` absent stays the classic path with `conditions_complete: true`
    (the old-client contract);
  * `POST /plan/conditions`: the patch shape (per-card conditions/lines/warnings/
    unavailable through the shared renderer), the disclosed set-aside + unknown
    lists, request bounds (empty/oversized id lists 422), the `/plan`-class rate
    limit, and the fail-closed non-anonymous auth gate (AC-2.4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

import api.app as app_mod
from orchestration.config import Settings

# ── engine-shaped test doubles (duck-typed like tests/test_api_endpoints.py) ──


@dataclass
class _Line:
    text: str
    source: str
    presentation: str = "stated"
    sources: list[str] = field(default_factory=list)
    # Epic 046 S1: `FeedLineResponse`/`_condition_fields` now read `body`/`age`
    # too; defaulted so this file's existing call sites are unaffected — these
    # tests assert wire SHAPE, not `body`/`age` content.
    body: str = ""
    age: str = ""


@dataclass
class _Warning:
    text: str
    source: str
    observed_at: datetime
    kind: str


@dataclass
class _ConditionStatus:
    kind: str
    state: str
    source: str = ""
    checked_at: datetime | None = None
    detail: str = ""


@dataclass
class _Card:
    canonical_id: str
    name: str
    distance_mi: float | None
    lines: list[_Line]
    warnings: list[_Warning] = field(default_factory=list)
    unavailable: list[Any] = field(default_factory=list)
    conditions: list[_ConditionStatus] = field(default_factory=list)


@dataclass
class _Feed:
    query: str
    cards: list[_Card]
    notices: tuple[str, ...] = ()
    set_aside: tuple[Any, ...] = ()


@dataclass
class _SetAsideReason:
    text: str
    source: str
    kind: str


@dataclass
class _SetAside:
    canonical_id: str
    name: str
    reasons: tuple[_SetAsideReason, ...]


@dataclass
class _Patch:
    cards: list[_Card]
    set_aside: tuple[_SetAside, ...]
    unknown: tuple[str, ...]
    from_cache: bool = False


class _Runtime:
    cache = None
    feed_cache_hit = False


class _StubSession:
    def run(self, query: Any, params: Any = None) -> list[dict[str, Any]]:
        return []


class _StubGraph:
    def scoped_session(self, viewer_id: str) -> _StubSession:
        return _StubSession()

    def close(self) -> None:  # pragma: no cover - lifespan shutdown
        pass


_NOT_FETCHED = [
    _ConditionStatus(kind=k, state="not_fetched")
    for k in ("weather", "air", "fire", "water", "closures", "permits")
]


def _phase1_feed(query: str) -> _Feed:
    return _Feed(
        query=query,
        cards=[_Card("ct:a", "Trail A", 4.2, lines=[], conditions=list(_NOT_FETCHED))],
    )


def _full_feed(query: str) -> _Feed:
    return _Feed(
        query=query,
        cards=[
            _Card(
                "ct:a",
                "Trail A",
                4.2,
                lines=[_Line("Clear skies", "nws", "stated", ["NWS"])],
                conditions=[
                    _ConditionStatus(
                        kind="weather",
                        state="present",
                        source="NWS",
                        checked_at=datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc),
                    )
                ],
            )
        ],
    )


def _canned_patch(*args: Any, **kwargs: Any) -> _Patch:
    return _Patch(
        cards=[
            _Card(
                "ct:a",
                "Trail A",
                4.2,
                lines=[_Line("Clear skies", "nws", "stated", ["NWS"])],
                conditions=[
                    _ConditionStatus(
                        kind="weather",
                        state="present",
                        source="NWS",
                        checked_at=datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc),
                    )
                ],
            )
        ],
        set_aside=(
            _SetAside(
                "ct:smoky",
                "Smoky Ridge",
                (_SetAsideReason("air quality hazardous (AQI 320) (AirNow)", "AirNow", "air"),),
            ),
        ),
        unknown=("ct:ghost",),
    )


_PLAN_BODY = {"query": "something mellow", "lat": 38.5, "lon": -78.4}
_CONDITIONS_BODY = {
    "query": "something mellow",
    "lat": 38.5,
    "lon": -78.4,
    "canonical_ids": ["ct:a", "ct:smoky", "ct:ghost"],
}


@pytest.fixture
def client(monkeypatch: Any, tmp_path: Any) -> Any:
    monkeypatch.setattr(app_mod, "build_runtime", lambda *a, **k: _Runtime())
    monkeypatch.setattr(
        "orchestration.two_phase.plan_cards",
        lambda query, origin, runtime, *, k, viewer_id: (_phase1_feed(query), False),
    )
    monkeypatch.setattr("orchestration.two_phase.plan_conditions", _canned_patch)
    monkeypatch.setattr("orchestration.engine.plan", lambda query, *a, **k: _full_feed(query))
    monkeypatch.setattr(app_mod, "_fetch_maps_by_canonical", lambda session, ids: {})
    monkeypatch.setenv("ADVENTURE_INGEST_STATS_DIR", str(tmp_path / "ingest_stats"))
    c = TestClient(app_mod.app)
    c.__enter__()
    monkeypatch.setattr(app_mod, "_settings", Settings.from_env({}))
    monkeypatch.setattr(app_mod, "_graph_client", _StubGraph())
    try:
        yield c
    finally:
        c.__exit__(None, None, None)


# ── /plan phase:"cards" ───────────────────────────────────────────────────────


def test_plan_phase_cards_returns_incomplete_not_fetched_feed(client: Any) -> None:
    resp = client.post("/plan", json={**_PLAN_BODY, "phase": "cards"})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["conditions_complete"] is False
    card = payload["cards"][0]
    assert card["lines"] == []
    assert card["warnings"] == []
    assert {c["state"] for c in card["conditions"]} == {"not_fetched"}
    # An unanswered kind carries no attribution on the wire (rule #1).
    assert all(c["source"] == "" and c["checked_at"] is None for c in card["conditions"])


def test_plan_without_phase_is_classic_and_complete(client: Any) -> None:
    resp = client.post("/plan", json=_PLAN_BODY)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["conditions_complete"] is True
    assert payload["cards"][0]["lines"][0]["text"] == "Clear skies"


def test_plan_phase_cards_with_kill_switch_serves_full_response(
    client: Any, monkeypatch: Any
) -> None:
    # D6: ADVENTURE_TWO_PHASE_ENABLED=0 → phase:"cards" serves the classic
    # single-pass response, self-described complete so the client skips call two.
    monkeypatch.setattr(
        app_mod, "_settings", Settings.from_env({"ADVENTURE_TWO_PHASE_ENABLED": "0"})
    )
    resp = client.post("/plan", json={**_PLAN_BODY, "phase": "cards"})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["conditions_complete"] is True
    assert payload["cards"][0]["conditions"][0]["state"] == "present"


def test_plan_phase_cards_warm_key_self_describes_complete(client: Any, monkeypatch: Any) -> None:
    # The D7 warm-key case: plan_cards itself reports complete=True.
    monkeypatch.setattr(
        "orchestration.two_phase.plan_cards",
        lambda query, origin, runtime, *, k, viewer_id: (_full_feed(query), True),
    )
    resp = client.post("/plan", json={**_PLAN_BODY, "phase": "cards"})
    assert resp.status_code == 200
    assert resp.json()["conditions_complete"] is True


def test_plan_rejects_unknown_phase(client: Any) -> None:
    resp = client.post("/plan", json={**_PLAN_BODY, "phase": "everything"})
    assert resp.status_code == 422


# ── Epic 052 WP-5 — ETag + Cache-Control on the /plan SHELL phase only ──────
# (design-system-v0.2 Part III.3): the phase:"cards" response gets a validator
# so the client's background revalidate can be a cheap 304; the classic
# complete response and /plan/conditions (live, ephemeral — Rule #3) never do.


def test_plan_phase_cards_carries_etag_and_private_cache_control(client: Any) -> None:
    resp = client.post("/plan", json={**_PLAN_BODY, "phase": "cards"})
    assert resp.status_code == 200
    assert resp.headers["etag"].startswith('"') and resp.headers["etag"].endswith('"')
    assert "private" in resp.headers["cache-control"]
    assert "no-cache" in resp.headers["cache-control"]


def test_plan_phase_cards_conditional_post_with_matching_etag_returns_cheap_304(
    client: Any,
) -> None:
    first = client.post("/plan", json={**_PLAN_BODY, "phase": "cards"})
    etag = first.headers["etag"]

    second = client.post(
        "/plan", json={**_PLAN_BODY, "phase": "cards"}, headers={"if-none-match": etag}
    )

    assert second.status_code == 304
    assert second.headers["etag"] == etag
    assert second.content == b""


def test_plan_phase_cards_conditional_post_with_stale_etag_serves_full_body(client: Any) -> None:
    resp = client.post(
        "/plan",
        json={**_PLAN_BODY, "phase": "cards"},
        headers={"if-none-match": '"not-the-real-etag"'},
    )
    assert resp.status_code == 200
    assert resp.json()["cards"]


def test_plan_classic_response_carries_no_caching_headers(client: Any) -> None:
    # The classic/complete response already carries live conditions — never a
    # stable "shell" a client should conditionally re-fetch.
    resp = client.post("/plan", json=_PLAN_BODY)
    assert resp.status_code == 200
    assert "etag" not in {k.lower() for k in resp.headers}
    assert "cache-control" not in {k.lower() for k in resp.headers}


def test_plan_phase_cards_kill_switch_serves_no_caching_headers(
    client: Any, monkeypatch: Any
) -> None:
    # D6: with the kill switch off, phase:"cards" degrades to the classic path —
    # it must not carry the shell's caching headers either.
    monkeypatch.setattr(
        app_mod, "_settings", Settings.from_env({"ADVENTURE_TWO_PHASE_ENABLED": "0"})
    )
    resp = client.post("/plan", json={**_PLAN_BODY, "phase": "cards"})
    assert resp.status_code == 200
    assert "etag" not in {k.lower() for k in resp.headers}


# ── POST /plan/conditions ─────────────────────────────────────────────────────


def test_conditions_patch_shape(client: Any) -> None:
    resp = client.post("/plan/conditions", json=_CONDITIONS_BODY)
    assert resp.status_code == 200
    payload = resp.json()

    patch = payload["patches"][0]
    assert patch["canonical_id"] == "ct:a"
    assert patch["lines"][0]["text"] == "Clear skies"
    weather = patch["conditions"][0]
    assert weather["state"] == "present"
    assert weather["source"] == "NWS"
    assert weather["checked_at"]  # answered → sourced + timestamped

    # A hard-blocked id comes back as a disclosed set-aside, never a card (AC-2.2).
    assert payload["set_aside"][0]["canonical_id"] == "ct:smoky"
    assert payload["set_aside"][0]["reasons"][0]["source"] == "AirNow"
    # An id the engine couldn't resolve is disclosed, never fabricated.
    assert payload["unknown"] == ["ct:ghost"]


def test_conditions_patch_carries_no_caching_headers(client: Any) -> None:
    # Rule #3 / spec III.3: the conditions overlay is fast/ephemeral, fetched
    # JIT — it must never carry a validator that could tempt a client into
    # reusing a stale hazard read.
    resp = client.post("/plan/conditions", json=_CONDITIONS_BODY)
    assert resp.status_code == 200
    assert "etag" not in {k.lower() for k in resp.headers}
    assert "cache-control" not in {k.lower() for k in resp.headers}


def test_conditions_request_bounds(client: Any) -> None:
    # Empty and oversized id lists 422 at the edge (AC-2.4: bounded to k's cap).
    resp = client.post("/plan/conditions", json={**_CONDITIONS_BODY, "canonical_ids": []})
    assert resp.status_code == 422
    too_many = [f"ct:{i}" for i in range(21)]
    resp = client.post("/plan/conditions", json={**_CONDITIONS_BODY, "canonical_ids": too_many})
    assert resp.status_code == 422
    # Per-item hygiene: a control character or an over-long id 422s before it can
    # reach a graph read, a log line, or the echoed `unknown` list.
    for bad in ["ct:\x00evil", "x" * 201]:
        resp = client.post("/plan/conditions", json={**_CONDITIONS_BODY, "canonical_ids": [bad]})
        assert resp.status_code == 422


def test_conditions_non_anonymous_requires_auth(client: Any) -> None:
    # Fail-closed like /plan (AC-2.4): no configured dev secret → any
    # non-anonymous viewer is rejected regardless of headers.
    resp = client.post("/plan/conditions", json={**_CONDITIONS_BODY, "viewer_id": "mem:josh"})
    assert resp.status_code == 403


def test_conditions_shares_the_plan_rate_limit_class(client: Any, monkeypatch: Any) -> None:
    monkeypatch.setenv("ADVENTURE_RATELIMIT_PLAN", "2/hour")
    ok1 = client.post("/plan/conditions", json=_CONDITIONS_BODY)
    ok2 = client.post("/plan/conditions", json=_CONDITIONS_BODY)
    limited = client.post("/plan/conditions", json=_CONDITIONS_BODY)
    assert ok1.status_code == 200
    assert ok2.status_code == 200
    assert limited.status_code == 429


def test_conditions_engine_failure_maps_to_typed_500(client: Any, monkeypatch: Any) -> None:
    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("probe registry exploded")

    monkeypatch.setattr("orchestration.two_phase.plan_conditions", _boom)
    resp = client.post("/plan/conditions", json=_CONDITIONS_BODY)
    assert resp.status_code == 500
    assert resp.json() == {"detail": "Internal error"}
    assert "x-correlation-id" in {k.lower() for k in resp.headers}
