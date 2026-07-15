"""Epic 043 S5 — the first authenticated write: POST /episode.

Two layers:
  * the domain writer (`orchestration.episode_create.create_manual_episode`) lands
    the Episode through the Epic-011 scoped-write seam (`execute_write`), reusing
    the batch-only `queries.upsert_episode` builder — no new write path (AC-5.1);
  * the endpoint requires a verified identity — anonymous / forged-token → 403
    (AC-5.2).

Fully hermetic: a fake ScopedSession records the write batch; an EC P-256 signer
mints tokens locally.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

import api.app as app_mod
from api.app import app
from api.auth import JWTVerifier
from graph.queries import assert_scoped_write
from orchestration.config import Settings
from orchestration.episode_create import ManualEpisodeRequest, create_manual_episode

_AUD = "authenticated"


# ── domain writer (AC-5.1: scoped-write seam, existing builder) ──


class _RecordingSession:
    """Records the write batch and asserts each owned statement passes the
    owner-scope guard — proving the write rides the real seam, not a bypass."""

    def __init__(self, viewer_id: str) -> None:
        self.viewer_id = viewer_id
        self.batches: list[list[tuple[str, dict[str, Any]]]] = []

    def execute_write(self, batch: Sequence[tuple[str, dict[str, Any]]]) -> None:
        for cypher, _params in batch:
            assert_scoped_write(cypher)  # each owned stmt must carry the scope clause
        self.batches.append(list(batch))


def test_s5_ac1_manual_episode_uses_scoped_write_seam_and_upsert_builder() -> None:
    session = _RecordingSession("sub-josh")
    req = ManualEpisodeRequest(client_episode_id="trip-42", canonical_id="ct:old-rag")
    result = create_manual_episode("sub-josh", req, session)

    assert result.episode_id == "ep:sub-josh:trip-42"  # owner embedded in the id
    assert result.owner_id == "sub-josh"
    assert result.canonical_id == "ct:old-rag"
    # One atomic batch: Person ensure + Episode upsert + DID wire + ON wire.
    assert len(session.batches) == 1
    batch = session.batches[0]
    joined = "\n".join(c for c, _ in batch)
    assert "MERGE (e:Episode {episode_id: $eid, owner_id: $viewer_id})" in joined  # the builder
    assert "MERGE (p)-[:DID]->(e)" in joined
    assert "MERGE (e)-[:ON]->(t)" in joined


def test_s5_manual_episode_watch_free_no_trail() -> None:
    """A bare 'I did this' with no trail and no metrics is a valid Episode
    (watch-free, Rule #6) — the ON wire is simply omitted."""
    session = _RecordingSession("sub-x")
    req = ManualEpisodeRequest(client_episode_id="trip-1")
    result = create_manual_episode("sub-x", req, session)
    assert result.canonical_id is None
    joined = "\n".join(c for c, _ in session.batches[0])
    assert "MERGE (e)-[:ON]->(t)" not in joined  # no trail → no ON edge


# ── endpoint auth (AC-5.2) — anonymous/forged → 403; signed-in → owned write ──


class _FakeScopedSession:
    def __init__(self, events: list[Any], viewer_id: str) -> None:
        self.events = events
        self.viewer_id = viewer_id

    def execute_write(self, batch: Sequence[tuple[str, dict[str, Any]]]) -> None:
        self.events.append(("write", self.viewer_id, len(list(batch))))


class _FakeGraphClient:
    def __init__(self, events: list[Any]) -> None:
        self.events = events

    def scoped_session(self, viewer_id: str, granted_ids: Sequence[str] = ()) -> _FakeScopedSession:
        return _FakeScopedSession(self.events, viewer_id)

    def close(self) -> None:  # pragma: no cover
        pass


class _Signer:
    def __init__(self, kid: str = "k1") -> None:
        self.kid = kid
        self._priv = ec.generate_private_key(ec.SECP256R1())

    def jwk(self) -> dict[str, Any]:
        pub = jwt.algorithms.get_default_algorithms()["ES256"].to_jwk(
            self._priv.public_key(), as_dict=True
        )
        pub.update({"kid": self.kid, "alg": "ES256", "use": "sig"})
        return pub

    def token(self, sub: str, *, exp_delta: int = 3600) -> str:
        return jwt.encode(
            {"sub": sub, "aud": _AUD, "exp": int(time.time()) + exp_delta},
            self._priv,
            algorithm="ES256",
            headers={"kid": self.kid},
        )


_BODY = {"client_episode_id": "trip-9", "canonical_id": "ct:old-rag"}


def test_s5_ac2_anonymous_episode_create_rejected() -> None:
    with TestClient(app) as client:
        app_mod._settings = Settings.from_env({})
        app_mod._jwt_verifier = None
        app_mod._graph_client = _FakeGraphClient([])  # type: ignore[assignment]
        r = client.post("/episode", json=_BODY)  # no credentials at all
    assert r.status_code == 403


def test_s5_ac2_forged_token_episode_create_rejected() -> None:
    signer = _Signer()
    with TestClient(app) as client:
        app_mod._settings = Settings.from_env({})
        app_mod._jwt_verifier = JWTVerifier(
            "https://x/jwks", audience=_AUD, http_get=lambda _u: {"keys": [signer.jwk()]}
        )
        app_mod._graph_client = _FakeGraphClient([])  # type: ignore[assignment]
        impostor = _Signer(kid=signer.kid)  # same kid, foreign key
        r = client.post(
            "/episode", json=_BODY, headers={"Authorization": f"Bearer {impostor.token('x')}"}
        )
    assert r.status_code == 403
    app_mod._jwt_verifier = None


def test_s5_signed_in_episode_create_lands_owned_write() -> None:
    events: list[Any] = []
    signer = _Signer()
    with TestClient(app) as client:
        app_mod._settings = Settings.from_env({})
        app_mod._jwt_verifier = JWTVerifier(
            "https://x/jwks", audience=_AUD, http_get=lambda _u: {"keys": [signer.jwk()]}
        )
        app_mod._graph_client = _FakeGraphClient(events)  # type: ignore[assignment]
        r = client.post(
            "/episode",
            json=_BODY,
            headers={"Authorization": f"Bearer {signer.token('sub-verified')}"},
        )
    assert r.status_code == 200
    assert r.json()["episode_id"] == "ep:sub-verified:trip-9"
    # The write was scoped to the VERIFIED sub, not any client-claimed id.
    assert events and events[0][0] == "write" and events[0][1] == "sub-verified"
    app_mod._jwt_verifier = None


def test_s5_episode_create_malformed_client_id_is_422() -> None:
    signer = _Signer()
    with TestClient(app) as client:
        app_mod._settings = Settings.from_env({})
        app_mod._jwt_verifier = JWTVerifier(
            "https://x/jwks", audience=_AUD, http_get=lambda _u: {"keys": [signer.jwk()]}
        )
        app_mod._graph_client = _FakeGraphClient([])  # type: ignore[assignment]
        r = client.post(
            "/episode",
            json={"client_episode_id": "bad id;DROP"},  # separators/space rejected
            headers={"Authorization": f"Bearer {signer.token('sub')}"},
        )
    assert r.status_code == 422
    app_mod._jwt_verifier = None
