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
            default vs an authenticated viewer, Epic 014 S3); and input validation
            (malformed body → 4xx, never a 500).

Adjacent behaviour is also exercised in test_api_ratelimit.py (rate-limit + observability),
test_viewer_auth.py (the auth guard in depth), and test_graph_stats_neo4j.py (the #44
query against a *live* DB). This module is the consolidated endpoint-contract suite and
carries the hermetic /health-shape, input-validation, and dialect-guard coverage those
files don't — none of it needs the `neo4j` marker.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
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
    "with_elev": 30,
    "with_multi_source": 18,
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
    sources: list[str] = field(default_factory=list)


@dataclass
class _Warning:
    text: str
    source: str
    observed_at: datetime
    kind: str


@dataclass
class _Unavailable:
    text: str
    source: str
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
    unavailable: list[_Unavailable] = field(default_factory=list)
    conditions: list[_ConditionStatus] = field(default_factory=list)


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
class _Feed:
    query: str
    cards: list[_Card]
    notices: tuple[str, ...] = ()
    set_aside: tuple[_SetAside, ...] = ()


class _Runtime:
    cache = None  # cache_size() reads 0 off this; no live probe cache in the test
    # /search reads these off Runtime to call search_trails — session/probes are never
    # touched for real because search_trails itself is stubbed in every /search test.
    session = None
    probes: dict[Any, Any] = {}
    probe_max_workers = 1


def _canned_feed(query: str, origin: object, runtime: object, **kwargs: object) -> _Feed:
    """Deterministic stand-in for orchestration.engine.plan — a two-line card with a
    warning, an unavailable-condition disclosure, and a feed-level notice, enough to
    assert the whole wire contract."""
    return _Feed(
        query=query,
        cards=[
            _Card(
                canonical_id="ct:mellow-loop",
                name="Mellow Loop",
                distance_mi=4.2,
                lines=[
                    _Line(
                        text="Stream is flowing",
                        source="usgs",
                        presentation="stated",
                        sources=["USGS"],
                    ),
                    _Line(
                        text="AQI may be elevated",
                        source="airnow",
                        presentation="hedged",
                        sources=["AirNow"],
                    ),
                ],
                warnings=[
                    _Warning(
                        text="weather alert: Extreme Heat Warning",
                        source="NWS api.weather.gov",
                        observed_at=datetime(2026, 7, 1, 22, 0, tzinfo=timezone.utc),
                        kind="weather",
                    )
                ],
                unavailable=[
                    _Unavailable(
                        text="water level couldn't be verified (no source responded)",
                        source="no source responded",
                        kind="water",
                    )
                ],
                conditions=[
                    _ConditionStatus(
                        kind="fire",
                        state="no_hazard",
                        source="FIRMS",
                        checked_at=datetime(2026, 7, 1, 22, 0, tzinfo=timezone.utc),
                    ),
                    _ConditionStatus(kind="water", state="unavailable"),
                    _ConditionStatus(kind="permits", state="not_fetched"),
                ],
            ),
        ],
        notices=("Drive times unavailable",),
        set_aside=(
            _SetAside(
                canonical_id="ct:fire-ridge",
                name="Fire Ridge",
                reasons=(
                    _SetAsideReason(
                        text="air quality hazardous (AQI 250) (AirNow)",
                        source="AirNow",
                        kind="air",
                    ),
                ),
            ),
        ),
    )


_PLAN_BODY = {"query": "something mellow with good views", "lat": 38.5, "lon": -78.4}


@pytest.fixture
def client(monkeypatch: Any, tmp_path: Any) -> Any:
    """A TestClient with the engine, the maps read, and the graph all stubbed so both
    endpoints answer hermetically with no live call."""
    monkeypatch.setattr(app_mod, "build_runtime", lambda *a, **k: _Runtime())
    monkeypatch.setattr("orchestration.engine.plan", _canned_feed)
    monkeypatch.setattr(app_mod, "_fetch_maps_by_canonical", lambda session, ids: {})
    # Epic 027: point /health's ingest_diff read at an empty tmp dir by default —
    # otherwise a real data/ingest_stats/ left by a local pipeline run (cwd-relative,
    # gitignored) would leak into hermetic /health tests that don't care about it.
    monkeypatch.setenv("ADVENTURE_INGEST_STATS_DIR", str(tmp_path / "ingest_stats"))
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
    # Elevation-presence gauge (Epic 017 durability): count + derived coverage %.
    assert graph["trails_with_elevation"] == 30
    assert graph["elevation_coverage_pct"] == round(30 / 42 * 100, 1)
    # Corroboration-presence gauge (CDP-01 / Epic 026a): count + derived coverage %.
    assert graph["trails_multi_source"] == 18
    assert graph["corroboration_pct"] == round(18 / 42 * 100, 1)


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


# ── /health ingest_diff (Epic 027 S4) ──────────────────────────────────────────


def _write_ingest_stats(tmp_path: Any, region: str, payload: dict[str, Any]) -> None:
    (tmp_path / f"{region}.json").write_text(json.dumps(payload))


def test_health_ingest_diff_null_when_no_stats_file(
    client: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    """AC-4.3: absent stats.json degrades to ingest_diff=null, never a 500 — status
    stays ok."""
    monkeypatch.setenv("ADVENTURE_INGEST_STATS_DIR", str(tmp_path))
    resp = client.get("/health")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "ok"
    assert payload["ingest_diff"] is None


def test_health_ingest_diff_populated_with_sorted_top_deltas(
    client: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    """AC-4.2/4.4: a present stats.json populates ingest_diff, top_deltas sorted by
    |delta| descending, and worst_breached_level reports the coarsest breach."""
    monkeypatch.setenv("ADVENTURE_INGEST_STATS_DIR", str(tmp_path))
    _write_ingest_stats(
        tmp_path,
        "shenandoah-gwj",
        {
            "region": "shenandoah-gwj",
            "ingest_version": "shenandoah-gwj-2026-07",
            "generated_at": "2026-07-07T00:00:00+00:00",
            "prune_blocked": True,
            "buckets": [
                # Deliberately NOT pre-sorted, to prove /health sorts defensively.
                {
                    "dimension": "source",
                    "value": "osm",
                    "pre": 1000,
                    "post": 990,
                    "delta": -10,
                    "rel_pct": 1.0,
                    "breached_level": None,
                },
                {
                    "dimension": "source",
                    "value": "nps",
                    "pre": 1000,
                    "post": 100,
                    "delta": -900,
                    "rel_pct": 90.0,
                    "breached_level": "low",
                },
                {
                    "dimension": "way_type",
                    "value": "path",
                    "pre": 1000,
                    "post": 850,
                    "delta": -150,
                    "rel_pct": 15.0,
                    "breached_level": "strict",
                },
            ],
        },
    )

    resp = client.get("/health")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "ok"
    diff = payload["ingest_diff"]
    assert diff is not None
    assert diff["region"] == "shenandoah-gwj"
    assert diff["prune_blocked"] is True
    assert diff["worst_breached_level"] == "low"  # coarsest across ALL buckets, not just top-5
    top = diff["top_deltas"]
    deltas = [abs(b["delta"]) for b in top]
    assert deltas == sorted(deltas, reverse=True)
    assert top[0]["value"] == "nps"
    assert len(top) <= 5


def test_health_ingest_diff_worst_level_none_when_nothing_breached(
    client: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    monkeypatch.setenv("ADVENTURE_INGEST_STATS_DIR", str(tmp_path))
    _write_ingest_stats(
        tmp_path,
        "shenandoah-gwj",
        {
            "region": "shenandoah-gwj",
            "ingest_version": "shenandoah-gwj-2026-07",
            "generated_at": "2026-07-07T00:00:00+00:00",
            "prune_blocked": False,
            "buckets": [
                {
                    "dimension": "source",
                    "value": "osm",
                    "pre": 1000,
                    "post": 995,
                    "delta": -5,
                    "rel_pct": 0.5,
                    "breached_level": None,
                }
            ],
        },
    )

    resp = client.get("/health")

    diff = resp.json()["ingest_diff"]
    assert diff["prune_blocked"] is False
    assert diff["worst_breached_level"] is None


def test_health_and_pipeline_share_ingest_stats_path_resolver() -> None:
    """AC-4.1: writer (pipeline) and reader (/health) import the SAME resolver
    function — not merely equivalent logic — so they can never drift apart."""
    import ingestion.pipeline as pipeline_mod
    from ingestion.checks.facet_diff import ingest_stats_path

    assert app_mod.ingest_stats_path is ingest_stats_path
    assert pipeline_mod.ingest_stats_path is ingest_stats_path


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
    # A VERIFIED hazard rides the card as a prominent source+timestamp-stamped warning
    # (decision of 2026-07-01) — never a bare string, never a set-aside.
    assert card["warnings"] == [
        {
            "text": "weather alert: Extreme Heat Warning",
            "source": "NWS api.weather.gov",
            "observed_at": "2026-07-01T22:00:00+00:00",
            "kind": "weather",
        }
    ]

    # Lines expose the presentation vocabulary as confidence_level (Rule #2).
    assert [line["confidence_level"] for line in card["lines"]] == ["stated", "hedged"]
    assert card["lines"][0]["text"] == "Stream is flowing"
    assert card["lines"][0]["source"] == "usgs"
    # Per-fact live sources (Epic 026a) — carried straight through, honest single-entry.
    assert card["lines"][0]["sources"] == ["USGS"]
    assert card["lines"][1]["sources"] == ["AirNow"]

    # An UNVERIFIABLE condition rides the CARD as a disclosed note (decision of
    # 2026-07-02, rule #6) — it never causes the trail to be set aside.
    assert card["unavailable"] == [
        {
            "text": "water level couldn't be verified (no source responded)",
            "source": "no source responded",
            "kind": "water",
        }
    ]

    # Set-aside disclosure (Epic 018 S5): only a VERIFIED hard threshold (hazardous
    # AQI) rides the feed set aside, with cause + source, kept off `cards` (a safety
    # gate, never a ranked demotion). Verified hazards are NOT here — they stay
    # cards (2026-07-01), and neither do unverifiable conditions (2026-07-02).
    assert [c["canonical_id"] for c in payload["cards"]] == ["ct:mellow-loop"]
    assert len(payload["set_aside"]) == 1
    aside = payload["set_aside"][0]
    assert aside["canonical_id"] == "ct:fire-ridge"
    assert aside["name"] == "Fire Ridge"
    reason = aside["reasons"][0]
    assert reason["kind"] == "air"
    assert reason["source"] == "AirNow"
    assert "hazardous" in reason["text"]
    assert reason["source"] in reason["text"]  # source-stamped

    # Per-kind condition dispositions (Epic 018 S4 / CDP-02): distinct silence
    # states ride the wire — an answered clear carries its source + timestamp,
    # an un-probed kind says so, and neither is a blank the client must guess about.
    assert card["conditions"] == [
        {
            "kind": "fire",
            "state": "no_hazard",
            "source": "FIRMS",
            "checked_at": "2026-07-01T22:00:00+00:00",
            "detail": "",
        },
        {"kind": "water", "state": "unavailable", "source": "", "checked_at": None, "detail": ""},
        {"kind": "permits", "state": "not_fetched", "source": "", "checked_at": None, "detail": ""},
    ]

    # Maps/terrain fields degrade to null when absent — never fabricated (Rule #1).
    assert card["geometry"] is None
    assert card["elevation_profile"] is None
    assert card["trailhead"] is None


# ── /plan: viewer authorization (Epic 014 S3) ──────────────────────────────────


def test_plan_k_at_new_cap_is_accepted(client: Any) -> None:
    # AH3: the public max was lowered from 50 to 20 (each candidate fans out to
    # several live probes) — 20 itself must still be a valid, accepted value.
    resp = client.post("/plan", json={**_PLAN_BODY, "k": 20})
    assert resp.status_code == 200


def test_plan_defaults_to_anonymous_viewer(client: Any) -> None:
    # No viewer_id in the body → anonymous default → the open world path serves a 200,
    # not an auth wall.
    resp = client.post("/plan", json=_PLAN_BODY)
    assert resp.status_code == 200


def test_s2_ac1_anonymous_plan_200_zero_credentials(client: Any, monkeypatch: Any) -> None:
    """Epic 043 S2 DoD regression: anonymous /plan returns 200 with ZERO credentials —
    no Authorization header, no dev secret, no managed auth wired. Anonymous browsing
    of the world stays a first-class, un-gated product no matter what auth is added."""
    monkeypatch.setattr(app_mod, "_settings", Settings.from_env({}))
    monkeypatch.setattr(app_mod, "_jwt_verifier", None)  # managed auth not configured
    resp = client.post("/plan", json={**_PLAN_BODY, "viewer_id": "anonymous"})
    assert resp.status_code == 200


def test_s1_plan_with_valid_bearer_token_returns_200(client: Any, monkeypatch: Any) -> None:
    """Epic 043 S1: a valid Supabase (ES256) token → the token's sub becomes the
    viewer and the request proceeds to a 200 through the same stubbed engine."""
    import time as _time

    import jwt as _jwt
    from cryptography.hazmat.primitives.asymmetric import ec as _ec

    from api.auth import JWTVerifier

    priv = _ec.generate_private_key(_ec.SECP256R1())
    jwk = _jwt.algorithms.get_default_algorithms()["ES256"].to_jwk(priv.public_key(), as_dict=True)
    jwk.update({"kid": "k1", "alg": "ES256", "use": "sig"})
    token = _jwt.encode(
        {"sub": "sub-uuid", "aud": "authenticated", "exp": int(_time.time()) + 60},
        priv,
        algorithm="ES256",
        headers={"kid": "k1"},
    )
    monkeypatch.setattr(app_mod, "_settings", Settings.from_env({}))
    monkeypatch.setattr(
        app_mod,
        "_jwt_verifier",
        JWTVerifier(
            "https://x/jwks", audience="authenticated", http_get=lambda _u: {"keys": [jwk]}
        ),
    )
    resp = client.post(
        "/plan",
        json={**_PLAN_BODY, "viewer_id": "anonymous"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


def test_plan_authenticated_viewer_with_dev_secret(client: Any, monkeypatch: Any) -> None:
    # Epic 043 S3: the dev-secret path is now HARD-GATED — honored only when the gate
    # is explicitly enabled (a local-dev escape hatch, off in production).
    monkeypatch.setattr(
        app_mod,
        "_settings",
        Settings.from_env(
            {"ADVENTURE_DEV_VIEWER_SECRET": "s3cret", "ADVENTURE_ALLOW_DEV_VIEWER_SECRET": "1"}
        ),
    )
    monkeypatch.setattr(app_mod, "_jwt_verifier", None)
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
        # AH3: each candidate fans out to several live probes; the public max is 20.
        pytest.param({"query": "x", "lat": 38.5, "lon": -78.4, "k": 21}, id="k-above-new-cap"),
        pytest.param(
            {"query": "x", "lat": 38.5, "lon": -78.4, "viewer_id": "josh; DROP TABLE"},
            id="viewer-id-bad-chars",
        ),
        pytest.param(
            {"query": "x", "lat": 38.5, "lon": -78.4, "viewer_id": "a" * 65},
            id="viewer-id-too-long",
        ),
        # 2026-07-12 review: the free-text query flows into provider prompts and log
        # lines — cap it at the edge so an unbounded body 422s, never becomes substrate.
        pytest.param(
            {"query": "q" * 501, "lat": 38.5, "lon": -78.4},
            id="query-over-max-length",
        ),
    ],
)
def test_plan_malformed_body_is_422_never_500(client: Any, body: dict[str, Any]) -> None:
    resp = client.post("/plan", json=body)
    # The contract: validation rejects the request loudly (422), never crashes (500).
    assert resp.status_code != 500
    assert 400 <= resp.status_code < 500
    assert resp.status_code == 422


def test_plan_query_at_max_length_is_accepted(client: Any) -> None:
    # Valid input is unchanged by the cap: a 500-char query still plans normally.
    resp = client.post("/plan", json={**_PLAN_BODY, "query": "q" * 500})
    assert resp.status_code == 200


def test_plan_invalid_json_body_is_4xx_never_500(client: Any) -> None:
    resp = client.post(
        "/plan", content=b"{not valid json", headers={"Content-Type": "application/json"}
    )
    assert resp.status_code != 500
    assert 400 <= resp.status_code < 500


# ── /search — trail-name search (Epic 038 / B001 Problem A) ──────────────────────
#
# The fixed contract: POST /search {query, k?} -> the EXACT same FeedResponse model
# /plan returns (reused, not a parallel shape). Hermetic: orchestration.engine.
# search_trails is stubbed so no graph/probe call ever happens.


def test_search_happy_path_returns_feed_response_shape(client: Any, monkeypatch: Any) -> None:
    from orchestration.curator import GuardrailVerdict
    from orchestration.engine import PlannedBatch, PlannedTrail
    from orchestration.scout import Candidate

    def _stub_search_trails(query: str, session: Any, probes: Any, **kwargs: Any) -> Any:
        candidate = Candidate(
            canonical_id="ct:old-rag-loop",
            name="Old Rag Loop",
            trailhead_id="",
            distance_m=0.0,
        )
        return PlannedBatch(
            trails=[PlannedTrail(candidate, {}, {}, GuardrailVerdict(False))],
        )

    monkeypatch.setattr("orchestration.engine.search_trails", _stub_search_trails)

    resp = client.post("/search", json={"query": "Old Rag"})
    assert resp.status_code == 200
    payload = resp.json()

    # Exactly the FeedResponse contract: query + cards + card_count (+ defaults).
    assert payload["query"] == "Old Rag"
    assert payload["card_count"] == 1
    assert len(payload["cards"]) == 1
    card = payload["cards"][0]
    assert card["canonical_id"] == "ct:old-rag-loop"
    assert card["name"] == "Old Rag Loop"
    assert payload["set_aside"] == []
    assert payload["conditions_complete"] is True


def test_search_no_match_returns_empty_feed_never_an_error(client: Any, monkeypatch: Any) -> None:
    from orchestration.engine import PlannedBatch

    def _stub_empty(query: str, session: Any, probes: Any, **kwargs: Any) -> Any:
        return PlannedBatch(trails=[])

    monkeypatch.setattr("orchestration.engine.search_trails", _stub_empty)

    resp = client.post("/search", json={"query": "zzqxw-nonexistent-9999"})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["cards"] == []
    assert payload["card_count"] == 0


def test_search_has_no_lat_lon_in_its_request_contract(client: Any, monkeypatch: Any) -> None:
    # The fixed contract (Epic 038): {query, k?} only — no lat/lon, unlike /plan.
    from orchestration.engine import PlannedBatch

    monkeypatch.setattr(
        "orchestration.engine.search_trails",
        lambda query, session, probes, **kwargs: PlannedBatch(trails=[]),
    )
    resp = client.post("/search", json={"query": "Old Rag", "lat": 38.5, "lon": -78.4})
    # Extra fields are simply ignored by pydantic (not an error) — lat/lon play no role.
    assert resp.status_code == 200


def test_search_malformed_body_is_422_never_500(client: Any) -> None:
    resp = client.post("/search", json={"k": 10})  # missing required "query"
    assert resp.status_code != 500
    assert resp.status_code == 422


def test_search_query_over_max_length_is_422(client: Any) -> None:
    resp = client.post("/search", json={"query": "q" * 501})
    assert resp.status_code == 422


def test_search_k_out_of_bounds_is_422(client: Any) -> None:
    resp = client.post("/search", json={"query": "Old Rag", "k": 21})
    assert resp.status_code == 422


def test_trail_card_happy_path_returns_feed_response_with_one_card(
    client: Any, monkeypatch: Any
) -> None:
    # Epic 045 S3: GET /trail/{id}/card returns a FeedResponse with one verified card.
    from orchestration.curator import GuardrailVerdict
    from orchestration.engine import PlannedBatch, PlannedTrail
    from orchestration.scout import Candidate

    def _stub_plan_by_id(canonical_id: str, session: Any, probes: Any, **kwargs: Any) -> Any:
        candidate = Candidate(
            canonical_id="ct:osm:way_138445924",
            name="Old Rag Loop",
            trailhead_id="",
            distance_m=0.0,
        )
        return PlannedBatch(
            trails=[PlannedTrail(candidate, {}, {}, GuardrailVerdict(False))],
        )

    monkeypatch.setattr("orchestration.engine.plan_trail_by_id", _stub_plan_by_id)

    resp = client.get("/trail/ct:osm:way_138445924/card")
    assert resp.status_code == 200
    payload = resp.json()

    # Exactly the FeedResponse contract.
    assert payload["query"] == ""
    assert payload["card_count"] == 1
    assert len(payload["cards"]) == 1
    card = payload["cards"][0]
    assert card["canonical_id"] == "ct:osm:way_138445924"
    assert card["name"] == "Old Rag Loop"
    assert payload["set_aside"] == []
    assert payload["conditions_complete"] is True


def test_trail_card_unknown_id_returns_empty_feed_never_404(client: Any, monkeypatch: Any) -> None:
    # Epic 045 S3.4: unknown id returns an honest-empty FeedResponse, never 404.
    from orchestration.engine import PlannedBatch

    def _stub_empty(canonical_id: str, session: Any, probes: Any, **kwargs: Any) -> Any:
        return PlannedBatch(trails=[])

    monkeypatch.setattr("orchestration.engine.plan_trail_by_id", _stub_empty)

    resp = client.get("/trail/ct:osm:way_unknown_9999/card")
    assert resp.status_code == 200  # Never 404, never an error
    payload = resp.json()
    assert payload["cards"] == []
    assert payload["card_count"] == 0


def test_trail_card_invalid_id_format_is_422(client: Any) -> None:
    # The canonical_id pattern validation is enforced at the path layer.
    resp = client.get("/trail/invalid-format/card")
    assert resp.status_code == 422
