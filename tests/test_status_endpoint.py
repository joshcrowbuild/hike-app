"""GET /status — cross-surface grounding endpoint (agent operating model).

Hermetic like the Epic 008 suite (tests/test_api_endpoints.py): the Neo4j driver is
replaced by an in-process stub — no network, no Aura, no API keys. Coverage:

  - the success shape with correctly-typed fields (deploy env, regions, corpus stats,
    graph freshness), reusing the /health stats read for the corpus block;
  - deploy_sha/deploy_branch reflect RENDER_GIT_COMMIT/RENDER_GIT_BRANCH when set and
    are null when unset (local/other hosts) — never guessed (Rule #1);
  - a dead graph degrades every graph-derived field to null with a 200, never a 500,
    mirroring /health's graph=null (Rule #1);
  - over the rate limit → the same clean JSON 429 the rest of the edge serves (#53).
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

import api.app as app_mod
from orchestration.config import Settings

# Canned rows keyed off the query text: the stats read carries COUNT {} subqueries;
# the freshness read aggregates SourceRecord.fetched_at / ingest_version.
_STATS_ROW = {
    "sv": "0.2.0-test",
    "trails": 1481,
    "srs": 2900,
    "ths": 310,
    "edges": 640,
}
_FRESHNESS_ROW = {
    "updated_at": "2026-06-29T14:00:00+00:00",
    "fetched_at": "2026-06-29T13:55:02+00:00",
    "ingest_version": "2026-06",
}


class _StubSession:
    def run(self, query: Any, params: Any = None) -> list[dict[str, Any]]:
        cypher = query[0] if isinstance(query, tuple) else query
        if "COUNT {" in cypher:
            return [dict(_STATS_ROW)]
        if "fetched_at" in cypher:
            return [dict(_FRESHNESS_ROW)]
        raise AssertionError(f"unexpected query in /status test: {cypher!r}")


class _StubGraph:
    def scoped_session(self, viewer_id: str) -> _StubSession:
        return _StubSession()

    def close(self) -> None:  # pragma: no cover - lifespan shutdown
        pass


class _DeadGraph:
    """A graph client whose every read raises — the unreachable-Aura case."""

    def scoped_session(self, viewer_id: str) -> Any:
        raise ConnectionError("graph unreachable")

    def close(self) -> None:  # pragma: no cover - lifespan shutdown
        pass


@pytest.fixture
def client(monkeypatch: Any) -> Any:
    """A TestClient with the graph stubbed and the Render deploy env cleared, so every
    test starts from the local/no-deploy baseline."""
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    monkeypatch.delenv("RENDER_GIT_BRANCH", raising=False)
    c = TestClient(app_mod.app)
    c.__enter__()
    # Override the lifespan-wired singletons with test doubles (no live Aura).
    monkeypatch.setattr(app_mod, "_settings", Settings.from_env({}))
    monkeypatch.setattr(app_mod, "_graph_client", _StubGraph())
    try:
        yield c
    finally:
        c.__exit__(None, None, None)


def test_status_success_shape_and_types(client: Any) -> None:
    resp = client.get("/status")
    assert resp.status_code == 200
    payload = resp.json()

    # No Render env in this process → deploy fields are honestly null, not guessed.
    assert payload["deploy_sha"] is None
    assert payload["deploy_branch"] is None

    assert isinstance(payload["region"], str) and payload["region"]
    assert payload["live_region"] == "US"  # the config default

    # Graph-derived freshness, straight off the canned rows.
    assert payload["schema_version"] == "0.2.0-test"
    assert payload["meta_updated_at"] == "2026-06-29T14:00:00+00:00"
    # last_ingest prefers the real fetched_at datetime over the coarse ingest_version.
    assert payload["last_ingest"] == "2026-06-29T13:55:02+00:00"

    # Corpus block reuses the /health GraphStats shape with correctly-typed counts.
    corpus = payload["corpus"]
    assert corpus is not None
    for key in ("canonical_trails", "source_records", "trailheads", "same_as_edges"):
        assert isinstance(corpus[key], int)
    assert corpus["canonical_trails"] == 1481
    assert corpus["schema_version"] == "0.2.0-test"


def test_status_reports_render_deploy_env(client: Any, monkeypatch: Any) -> None:
    monkeypatch.setenv("RENDER_GIT_COMMIT", "f1c4b60deadbeef")
    monkeypatch.setenv("RENDER_GIT_BRANCH", "main")

    payload = client.get("/status").json()

    assert payload["deploy_sha"] == "f1c4b60deadbeef"
    assert payload["deploy_branch"] == "main"


def test_status_deploy_sha_null_when_env_unset(client: Any) -> None:
    # The fixture clears RENDER_GIT_COMMIT/BRANCH — the local/other-host case.
    payload = client.get("/status").json()
    assert payload["deploy_sha"] is None
    assert payload["deploy_branch"] is None


def test_status_graph_unreachable_degrades_to_nulls_not_500(client: Any, monkeypatch: Any) -> None:
    monkeypatch.setattr(app_mod, "_graph_client", _DeadGraph())

    resp = client.get("/status")

    # Degrade-and-disclose (Rule #1): a dead graph nulls the graph-derived fields but
    # the endpoint still answers 200 — the deploy/region facts remain grounded.
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["corpus"] is None
    assert payload["schema_version"] is None
    assert payload["meta_updated_at"] is None
    assert payload["last_ingest"] is None
    assert isinstance(payload["region"], str) and payload["region"]


def test_status_over_limit_returns_clean_429(client: Any, monkeypatch: Any) -> None:
    # /status shares the /health limit config. A wide window ("/hour") so the count,
    # not the clock, trips here (the established anti-flake pattern).
    monkeypatch.setenv("ADVENTURE_RATELIMIT_HEALTH", "2/hour")

    assert client.get("/status").status_code == 200
    assert client.get("/status").status_code == 200
    limited = client.get("/status")

    assert limited.status_code == 429
    assert "detail" in limited.json()
    assert "rate limit" in limited.json()["detail"].lower()
    assert "retry-after" in {k.lower() for k in limited.headers}
