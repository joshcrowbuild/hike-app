"""Shared pytest fixtures.

The live-Neo4j fixtures here (Epic 015 S2) are the ONLY place a test opens a real
driver connection (AC-2.3). They are *requested* only by `@pytest.mark.neo4j` tests,
so the DB-free fast legs never instantiate them and never import the neo4j driver —
`graph.client.GraphClient` builds its driver lazily, so merely importing this module
on a driver-less leg is safe.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

_SCHEMA = Path(__file__).resolve().parent.parent / "graph" / "schema.cypher"


# ---------------------------------------------------------------------------
# Neo4j test safety guard — DO NOT WEAKEN THIS.
#
# On 2026-07-01 a build lane's `@pytest.mark.neo4j` tests ran with a copied
# `.env` whose NEO4J_URI pointed at the LIVE Aura production database
# (`neo4j+s://...`). `clean_graph` (below) runs `MATCH (n) DETACH DELETE n`
# before every test — against production that wiped the entire corpus.
#
# `neo4j_client` is the ONLY place a test opens a real driver (AC-2.3, see its
# docstring), so this guard runs first thing inside it, before `GraphClient`
# is even constructed. Only a loopback bolt/neo4j URI is allowed; every other
# host, and every Aura-only TLS scheme, is refused outright.
# ---------------------------------------------------------------------------

_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
# Aura is ALWAYS reached over one of these — a local/docker database never is.
# Refuse them unconditionally, even if the host happens to look loopback-ish.
_REMOTE_ONLY_SCHEMES = {"neo4j+s", "neo4j+ssc", "bolt+s", "bolt+ssc"}
# The one deliberately-ugly escape hatch. Anything else (unset, "true", "1",
# "yes") does NOT bypass the guard — only this exact value does.
_ALLOW_REMOTE_ENV = "ALLOW_NEO4J_TESTS_ON_REMOTE"
_ALLOW_REMOTE_VALUE = "yes-i-accept-data-loss"


def _assert_local_neo4j_uri(uri: str) -> None:
    """Refuse (`pytest.fail`) unless `uri` is unambiguously a local database.

    Passes only for a bolt/neo4j URI whose host resolves to a loopback address
    (`localhost` / `127.0.0.1` / `::1`) — which is exactly how CI's service
    container and `make db-up`'s local docker Neo4j are reached (both publish
    bolt on `127.0.0.1:7687` only; see `docker-compose.yml`). Everything else
    is refused, including `neo4j+s://`/`neo4j+ssc://`/`bolt+s://`/`bolt+ssc://`
    (Aura-only, always remote) regardless of hostname, and any scheme pointed
    at a non-loopback host. Fails closed: an unparseable or empty URI refuses,
    it does not pass.
    """
    if os.environ.get(_ALLOW_REMOTE_ENV) == _ALLOW_REMOTE_VALUE:
        return

    parsed = urlsplit(uri)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()

    if scheme in _REMOTE_ONLY_SCHEMES or host not in _LOOPBACK_HOSTS:
        pytest.fail(
            "\n"
            "########################################################################\n"
            "# REFUSING TO RUN @pytest.mark.neo4j TESTS: NEO4J_URI is not local.   #\n"
            "########################################################################\n"
            f"  NEO4J_URI = {uri!r}\n"
            "\n"
            "These tests DETACH DELETE the ENTIRE graph before every test\n"
            "(`clean_graph`). On 2026-07-01 a copied `.env` pointed NEO4J_URI at a\n"
            "live Aura database and this exact test suite wiped the production\n"
            "corpus. This guard exists so that can never happen again.\n"
            "\n"
            "Only a loopback bolt/neo4j URI is allowed, e.g.:\n"
            "    bolt://localhost:7687\n"
            "    bolt://127.0.0.1:7687\n"
            "    neo4j://localhost:7687\n"
            "`neo4j+s://`, `neo4j+ssc://`, `bolt+s://`, `bolt+ssc://`, and any\n"
            "non-loopback host are ALWAYS refused, no matter what.\n"
            "\n"
            "Fix: unset NEO4J_URI, or point it at a local database\n"
            "(`make db-up` starts one via docker compose).\n"
            "\n"
            "If — and only if — you are certain this URI is a disposable,\n"
            "non-production database and you accept it may be irrecoverably wiped,\n"
            "you may bypass this guard with the explicit, deliberately ugly opt-in:\n"
            f"    {_ALLOW_REMOTE_ENV}={_ALLOW_REMOTE_VALUE}\n"
            "There is no other way to bypass this check.\n",
            pytrace=False,
        )


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> Any:
    """Reset the module-level API limiter before each test.

    `api.ratelimit.limiter` accumulates per-IP counts in process; every TestClient call
    shares the same `testclient` remote address, so without a reset one test's requests
    would spend another test's budget and trip a spurious 429. Imported lazily, and the
    import is tolerated-if-absent, so a partial run in an env without the api/slowapi extra
    (e.g. an ingestion-only unit slice) doesn't fail at fixture setup — there's simply no
    limiter to reset.
    """
    try:
        from api.ratelimit import limiter
    except ImportError:
        yield
        return

    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture(autouse=True)
def _prewarmed_api(monkeypatch: Any) -> Any:
    """Pre-warm the API's readiness gate for every test (warm-start lane).

    /health answers 503 until the lifespan's warm-up thread has verified /plan's
    dependency stack against the *real* environment — which a hermetic test never
    has (no Aura, no keys). So by default: never spawn the real warm-up thread
    (`_start_warmup` → no-op) and install an already-warm state, keeping every
    existing TestClient suite hermetic and /health at 200. The warm-up tests
    (test_api_warmup.py) override both to exercise the gate itself. Import
    tolerated-if-absent, mirroring `_reset_rate_limiter`: a slice without the api
    extra has nothing to pre-warm.
    """
    try:
        import api.app as app_mod
    except ImportError:
        yield
        return

    warmed = app_mod._WarmupState()
    warmed.ok.set()
    monkeypatch.setattr(app_mod, "_start_warmup", lambda *a, **k: None)
    monkeypatch.setattr(app_mod, "_warmup", warmed)

    # The feed warmer (Epic 039 B5) must never spawn here either: lifespan wires it
    # to the pre-opened gate above, and a real warm loop would run build_runtime +
    # engine.plan against the AMBIENT environment — real Aura/provider credentials
    # if a .env is exported into the test shell (the exact 2026-07-01 hazard class).
    # The NAME bound in api.app is replaced (not the class itself), so the warmer's
    # own unit tests (test_feed_warmer.py) still exercise the real start() with fakes.
    class _StubFeedWarmer:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._thread = None

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

    monkeypatch.setattr(app_mod, "FeedWarmer", _StubFeedWarmer)
    yield


def _iter_statements(schema_text: str):
    """Yield individual Cypher statements from schema.cypher.

    schema.cypher carries `;` inside its `//` comments (e.g. `// ...; ...`), so `//`
    line-comments must be stripped *before* splitting on `;` — otherwise a `;` in a
    comment would tear a statement in half. No `//` appears inside any string literal in
    this file, so cutting each line at its first `//` is safe. Blank chunks are skipped.
    """
    no_comments = "\n".join(line.split("//", 1)[0] for line in schema_text.splitlines())
    for chunk in no_comments.split(";"):
        if chunk.strip():
            yield chunk.strip()


@pytest.fixture(scope="session")
def neo4j_client() -> Any:
    """A live `GraphClient` built from NEO4J_URI/USER/PASSWORD env (defaults match the CI
    service), with `graph/schema.cypher` applied over the bolt driver — statement-split,
    not via `docker compose exec`/`cypher-shell` (AC-2.1). This is the only fixture that
    opens a live connection (AC-2.3). It fails loudly with a readable driver error if no
    database is reachable — a missing service is a red build, never a silent no-op (AC-1.3).
    """
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    _assert_local_neo4j_uri(uri)  # never construct a driver before this passes

    from graph.client import GraphClient

    client = GraphClient(
        uri,
        os.environ.get("NEO4J_USER", "neo4j"),
        os.environ.get("NEO4J_PASSWORD", "testpassword"),
    )
    bootstrap = client.scoped_session("schema-bootstrap")
    for statement in _iter_statements(_SCHEMA.read_text()):
        bootstrap.run((statement, {}))  # autocommit; unused viewer params are ignored
    try:
        yield client
    finally:
        client.close()


@pytest.fixture
def clean_graph(neo4j_client: Any) -> Any:
    """Clear the whole graph before each test (AC-2.2) so the integration tests are
    independent and order-free. Constraints/indexes are schema, not nodes, so they survive
    the `DETACH DELETE`. Returns the shared session-scoped client."""
    neo4j_client.scoped_session("fixture-reset").run(("MATCH (n) DETACH DELETE n", {}))
    return neo4j_client
