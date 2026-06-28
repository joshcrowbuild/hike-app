"""TLS hardening for the Neo4j connection (Aura CA-path gap).

graph/client.py points Python's ssl module at certifi's CA bundle on import, so the
strict-TLS neo4j+s:// connection to Aura can verify the server cert even on hosts
(e.g. python:3.11-slim) where the ssl module finds no system bundle. These assert:
  1. importing graph.client sets SSL_CERT_FILE to an existing file when it is unset,
  2. an operator-provided SSL_CERT_FILE is respected (setdefault, not overwrite), and
  3. the connection path stays STRICT TLS — the URI is passed through unchanged
     (no neo4j+ssc:// rewrite) and no trust-all / encryption-off kwarg is added.
"""

from __future__ import annotations

import importlib
import os
import sys
import types

import certifi

import graph.client


def test_import_sets_ssl_cert_file_to_existing_file_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)

    importlib.reload(graph.client)

    cert_file = os.environ.get("SSL_CERT_FILE")
    assert cert_file == certifi.where()
    assert cert_file is not None and os.path.isfile(cert_file)

    cert_dir = os.environ.get("SSL_CERT_DIR")
    assert cert_dir == os.path.dirname(certifi.where())
    assert cert_dir is not None and os.path.isdir(cert_dir)


def test_operator_ssl_cert_file_is_respected(monkeypatch) -> None:
    # setdefault must not clobber an operator-provided bundle.
    monkeypatch.setenv("SSL_CERT_FILE", "/operator/custom/ca-bundle.pem")

    importlib.reload(graph.client)

    assert os.environ["SSL_CERT_FILE"] == "/operator/custom/ca-bundle.pem"


def test_connection_path_stays_strict_tls(monkeypatch) -> None:
    """The driver is built with the URI exactly as given — strict neo4j+s:// — and
    with no kwarg that downgrades TLS (no encrypted=False, no trust-all)."""
    calls: dict[str, object] = {}

    class _FakeDriver:
        def close(self) -> None:  # pragma: no cover - not exercised here
            pass

    class _FakeGraphDatabase:
        @staticmethod
        def driver(uri: str, **kwargs: object) -> _FakeDriver:
            calls["uri"] = uri
            calls["kwargs"] = kwargs
            return _FakeDriver()

    fake_neo4j = types.ModuleType("neo4j")
    fake_neo4j.GraphDatabase = _FakeGraphDatabase  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "neo4j", fake_neo4j)

    from graph.client import GraphClient

    client = GraphClient("neo4j+s://abc123.databases.neo4j.io", "neo4j", "pw")
    client._ensure_driver()

    # Scheme is unchanged: still the strict, fully-verified neo4j+s:// — never +ssc.
    assert calls["uri"] == "neo4j+s://abc123.databases.neo4j.io"
    assert "+ssc" not in str(calls["uri"])

    kwargs = calls["kwargs"]
    assert isinstance(kwargs, dict)
    # No TLS downgrade: no trust-all, no explicit encryption-off.
    assert "trust" not in kwargs
    assert kwargs.get("encrypted", True) is not False
