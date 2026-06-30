"""Epic 008 — automated API contract tests for /health and /plan.

Hermetic by construction (Epic 008 AC): no network, no Aura, no API keys. The Neo4j
driver is replaced by an in-process stub and the orchestration engine is mocked so
/plan returns a deterministic feed — nothing here ever opens a real connection or calls
a model provider. The suite is safe to run in CI with no services and no secrets.

Coverage
  /health — the success shape plus correctly-typed graph stats, and a regression guard
            for #44: the stats query must use COUNT {} subqueries, never the
            size([(pattern)|x]) pattern-comprehension form Aura's Cypher 25 rejects
            (42I06: Invalid input '|'), which had silently left graph=null on every call.
  /plan   — the happy-path request/response contract; viewer authorization (anonymous
            default vs an authenticated viewer, Epic 014 S3); input validation
            (malformed body → 4xx, never a 500); and the #53 per-IP rate limit
            (over the limit → a clean JSON 429).

Adjacent behaviour is also exercised in test_api_ratelimit.py (rate-limit + observability),
test_viewer_auth.py (the auth guard in depth), and test_graph_stats_neo4j.py (the #44
query against a *live* DB). This module is the consolidated endpoint-contract suite and
carries the hermetic /health-shape, input-validation, and dialect-guard coverage those
files don't — none of it needs the `neo4j` marker.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient

import api.app as app_mod
from orchestration.config import Settings

# ── Test doubles ──────────────────────────────────────────────────────────────
#
# The graph stub returns canned health rows and records the Cypher it's handed, so a
# test can assert the dialect of the actual query without a database. The engine is
# replaced by `_canned_feed`; the maps batch read is mocked to {} in the `client`
# fixture, so every session.run() reaching the stub is the /health stats query.

_HEALTH_ROW = {
    "sv": "epic008-test",
    "trails": 42,
    "srs": 100,
    "ths": 7,
    "edges": 12,
}


class _StubSession:
    def __init__(self, recorder: list[str]) -> None:
        self._recorder = recorder

    def run(self, query: Any, params: Any = None) -> list[dict[str, Any]]:
        # _graph_stats passes run((cypher, {})); other callers pass a bare string.
        cypher = query[0] if isinstance(query, tuple) else query
        self._recorder.append(cypher)
        return [dict(_HEALTH_ROW)]


class _StubGraph:
    """A graph client that never touches Neo4j; it hands back canned health rows and
    keeps every Cypher string it ran so a test can inspect the dialect."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    def scoped_session(self, viewer_id: str) -> _StubSession:
        return _StubSession(self.queries)

    def close(self) -> None:  # pragma: no cover - lifespan shutdown
        pass


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


class _Runtime:
    cache = None  # cache_size() reads 0 off this; no live probe cache in the test


def _canned_feed(query: str, origin: object, runtime: object, **kwargs: object) -> _Feed:
    """Deterministic stand-in for orchestration.engine.plan — a two-line card with a
    warning and a feed-level notice, enough to assert the whole wire contract."""
    return _Feed(
        query=query,
        cards=[
            _Card(
                canonical_id="ct:mellow-loop",
                name="Mellow Loop",
                distance_mi=4.2,
                lines=[
                    _Line(text="Stream is flowing", source="usgs", presentation="stated"),
                    _Line(text="AQI may be elevated", source="airnow", presentation="hedged"),
                ],
                warnings=["Bridge out near mile 2"],
            ),
        ],
        notices=("Drive times unavailable",),
    )


_PLAN_BODY = {"query": "something mellow with good views", "lat": 38.5, "lon": -78.4}


@pytest.fixture
def client(monkeypatch: Any) -> Any:
    """A TestClient with the engine, the maps read, and the graph all stubbed so both
    endpoints answer hermetically with no live call."""
    monkeypatch.setattr(app_mod, "build_runtime", lambda *a, **k: _Runtime())
    monkeypatch.setattr("orchestration.engine.plan", _canned_feed)
    monkeypatch.setattr(app_mod, "_fetch_maps_by_canonical", lambda session, ids: {})
    c = TestClient(app_mod.app)
    c.__enter__()
    # Override the lifespan-wired singletons with test doubles (no live Aura).
    monkeypatch.setattr(app_mod, "_settings", Settings.from_env({}))
    monkeypatch.setattr(app_mod, "_graph_client", _StubGraph())
    try:
        yield c
    finally:
        c.__exit__(None, None, None)


# ── /health ───────────────────────────────────────────────────────────────────


def test_health_returns_ok_with_typed_graph_stats(client: Any) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    payload = resp.json()

    assert payload["status"] == "ok"
    assert payload["version"]  # a version string is reported
    assert payload["region"]
    assert isinstance(payload["probes_available"], list)

    graph = payload["graph"]
    assert graph is not None  # stub DB reachable → stats present, not null
    # Counts are present AND correctly typed (ints, never strings/floats)…
    for key in ("canonical_trails", "source_records", "trailheads", "same_as_edges"):
        assert key in graph
        assert isinstance(graph[key], int)
    # …and reflect the canned rows.
    assert graph["canonical_trails"] == 42
    assert graph["source_records"] == 100
    assert graph["trailheads"] == 7
    assert graph["same_as_edges"] == 12
    assert graph["schema_version"] == "epic008-test"


def test_health_query_uses_count_subquery_not_pattern_comprehension(monkeypatch: Any) -> None:
    """Regression guard for #44. Aura's Cypher 25 rejects the size([(pattern)|x])
    pattern-comprehension form (42I06: Invalid input '|'), which had silently left
    graph=null on every /health. The stats query must use COUNT {} subqueries and carry
    no pattern-comprehension pipe. Asserted hermetically against the exact Cypher the
    handler runs; the live-DB counterpart is test_graph_stats_neo4j.py."""
    graph = _StubGraph()
    monkeypatch.setattr(app_mod, "_graph_client", graph)
    monkeypatch.setattr(app_mod, "_settings", Settings.from_env({}))

    stats = app_mod._graph_stats()

    assert stats is not None  # parsed cleanly off the canned rows (no swallowed error)
    assert len(graph.queries) == 1
    cypher = graph.queries[0]
    assert "COUNT {" in cypher  # the Cypher-5/25-valid subquery form
    assert "size(" not in cypher.lower()  # not the rejected pattern-comprehension form
    assert "|" not in cypher  # the exact 42I06 trigger (Invalid input '|')


# ── /plan: happy-path contract ─────────────────────────────────────────────────


def test_plan_happy_path_contract(client: Any) -> None:
    resp = client.post("/plan", json=_PLAN_BODY)
    assert resp.status_code == 200
    payload = resp.json()

    # Feed envelope
    assert payload["query"] == _PLAN_BODY["query"]
    assert payload["card_count"] == 1
    assert len(payload["cards"]) == payload["card_count"]
    assert payload["notices"] == ["Drive times unavailable"]

    # Card shape
    card = payload["cards"][0]
    assert card["canonical_id"] == "ct:mellow-loop"
    assert card["name"] == "Mellow Loop"
    assert card["distance_mi"] == 4.2
    assert card["warnings"] == ["Bridge out near mile 2"]

    # Lines expose the presentation vocabulary as confidence_level (Rule #2).
    assert [line["confidence_level"] for line in card["lines"]] == ["stated", "hedged"]
    assert card["lines"][0]["text"] == "Stream is flowing"
    assert card["lines"][0]["source"] == "usgs"

    # Maps/terrain fields degrade to null when absent — never fabricated (Rule #1).
    assert card["geometry"] is None
    assert card["elevation_profile"] is None
    assert card["trailhead"] is None


# ── /plan: viewer authorization (Epic 014 S3) ──────────────────────────────────


def test_plan_defaults_to_anonymous_viewer(client: Any) -> None:
    # No viewer_id in the body → anonymous default → the open world path serves a 200,
    # not an auth wall.
    resp = client.post("/plan", json=_PLAN_BODY)
    assert resp.status_code == 200


def test_plan_authenticated_viewer_with_dev_secret(client: Any, monkeypatch: Any) -> None:
    monkeypatch.setattr(
        app_mod, "_settings", Settings.from_env({"ADVENTURE_DEV_VIEWER_SECRET": "s3cret"})
    )
    # A provided viewer_id is honored only with the configured secret…
    ok = client.post(
        "/plan",
        json={**_PLAN_BODY, "viewer_id": "mem:josh"},
        headers={"X-Dev-Viewer-Secret": "s3cret"},
    )
    assert ok.status_code == 200
    # …the same viewer without the secret fails closed (403), never served.
    forged = client.post("/plan", json={**_PLAN_BODY, "viewer_id": "mem:josh"})
    assert forged.status_code == 403


# ── /plan: input validation (malformed body → 4xx, never 500) ───────────────────


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({}, id="empty"),
        pytest.param({"lat": 38.5, "lon": -78.4}, id="missing-query"),
        pytest.param({"query": "x", "lon": -78.4}, id="missing-lat"),
        pytest.param({"query": "x", "lat": 38.5}, id="missing-lon"),
        pytest.param({"query": "x", "lat": 200, "lon": -78.4}, id="lat-out-of-range"),
        pytest.param({"query": "x", "lat": 38.5, "lon": 400}, id="lon-out-of-range"),
        pytest.param({"query": "x", "lat": "north", "lon": -78.4}, id="lat-wrong-type"),
        pytest.param({"query": "x", "lat": 38.5, "lon": -78.4, "k": 0}, id="k-below-min"),
        pytest.param({"query": "x", "lat": 38.5, "lon": -78.4, "k": 999}, id="k-above-max"),
    ],
)
def test_plan_malformed_body_is_422_never_500(client: Any, body: dict[str, Any]) -> None:
    resp = client.post("/plan", json=body)
    # The contract: validation rejects the request loudly (422), never crashes (500).
    assert resp.status_code != 500
    assert 400 <= resp.status_code < 500
    assert resp.status_code == 422


def test_plan_invalid_json_body_is_4xx_never_500(client: Any) -> None:
    resp = client.post(
        "/plan", content=b"{not valid json", headers={"Content-Type": "application/json"}
    )
    assert resp.status_code != 500
    assert 400 <= resp.status_code < 500


# ── /plan: #53 per-IP rate limit ────────────────────────────────────────────────


def test_plan_over_limit_returns_clean_429(client: Any, monkeypatch: Any) -> None:
    # A wide window ("/hour") so the count, not the clock, is what trips here.
    monkeypatch.setenv("ADVENTURE_RATELIMIT_PLAN", "2/hour")

    assert client.post("/plan", json=_PLAN_BODY).status_code == 200
    assert client.post("/plan", json=_PLAN_BODY).status_code == 200
    limited = client.post("/plan", json=_PLAN_BODY)

    assert limited.status_code == 429
    # Clean JSON envelope mirroring the rest of the API, plus the back-off contract.
    assert "detail" in limited.json()
    assert "rate limit" in limited.json()["detail"].lower()
    assert "retry-after" in {k.lower() for k in limited.headers}
