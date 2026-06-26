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

import pytest

_SCHEMA = Path(__file__).resolve().parent.parent / "graph" / "schema.cypher"


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
    from graph.client import GraphClient

    client = GraphClient(
        os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
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
