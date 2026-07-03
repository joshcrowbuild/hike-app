"""Guards the Neo4j test safety check in `tests/conftest.py`.

Fix for the 2026-07-01 incident: a build lane's `@pytest.mark.neo4j` tests ran
with a copied `.env` whose NEO4J_URI pointed at the LIVE Aura production
database (`neo4j+s://...`), and `clean_graph`'s `MATCH (n) DETACH DELETE n`
wiped the entire production corpus.

This test is deliberately DB-free (no `@pytest.mark.neo4j`) — it exercises
`_assert_local_neo4j_uri` directly, so it runs in the fast `make test` lane
and can never itself touch a real database.
"""

from __future__ import annotations

import pytest

from tests.conftest import _ALLOW_REMOTE_ENV, _ALLOW_REMOTE_VALUE, _assert_local_neo4j_uri


def test_rejects_the_uri_shape_that_wiped_production() -> None:
    """The exact incident shape: an Aura `neo4j+s://` URI."""
    with pytest.raises(pytest.fail.Exception, match="NEO4J_URI is not local"):
        _assert_local_neo4j_uri("neo4j+s://my-instance.databases.neo4j.io:7687")


@pytest.mark.parametrize(
    "uri",
    [
        "neo4j+s://my-instance.databases.neo4j.io:7687",
        "neo4j+ssc://my-instance.databases.neo4j.io:7687",
        "bolt+s://my-instance.databases.neo4j.io:7687",
        "bolt+ssc://my-instance.databases.neo4j.io:7687",
        "bolt://203.0.113.5:7687",  # non-loopback host, otherwise-plain scheme
        "neo4j://example.com:7687",
        "neo4j+s://localhost:7687",  # remote-only scheme wins even on a local-looking host
        "",  # unparseable / empty must fail closed, never pass by accident
    ],
)
def test_rejects_every_non_local_uri_shape(uri: str) -> None:
    with pytest.raises(pytest.fail.Exception):
        _assert_local_neo4j_uri(uri)


@pytest.mark.parametrize(
    "uri",
    [
        "bolt://localhost:7687",
        "bolt://127.0.0.1:7687",
        "neo4j://localhost:7687",
        "bolt://[::1]:7687",
    ],
)
def test_allows_local_uris(uri: str) -> None:
    _assert_local_neo4j_uri(uri)  # must not raise


def test_explicit_ugly_opt_in_bypasses_the_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_ALLOW_REMOTE_ENV, _ALLOW_REMOTE_VALUE)
    _assert_local_neo4j_uri("neo4j+s://my-instance.databases.neo4j.io:7687")  # must not raise


@pytest.mark.parametrize("near_miss", ["true", "1", "yes", "YES-I-ACCEPT-DATA-LOSS", ""])
def test_near_miss_opt_in_values_do_not_bypass(
    monkeypatch: pytest.MonkeyPatch, near_miss: str
) -> None:
    """Only the exact ugly string bypasses — no accidental truthy value does."""
    monkeypatch.setenv(_ALLOW_REMOTE_ENV, near_miss)
    with pytest.raises(pytest.fail.Exception):
        _assert_local_neo4j_uri("neo4j+s://my-instance.databases.neo4j.io:7687")
