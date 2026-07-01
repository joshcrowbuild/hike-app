"""Neo4j access — permission-scoped from the first query (rule #4 / thread T2).

Every read **and write** of an owned node goes through a `ScopedSession`, which
injects the viewer's identity (`$viewer_id` / `$granted_ids`) into every
statement's params. `run` is the read choke point; `run_write` is the write
choke point (Epic 011) — it additionally *refuses* an owned-label write that
carries no owner-scope clause, so no writer can create or overwrite another
owner's node by forgetting the clause. Combined with the `graph.queries`
builders — the only sanctioned place to author Cypher touching owned nodes —
this is the single seam that guarantees no statement reads or writes ungranted
nodes. Phase 0 is single-user, but the seam exists now so it can't be
retrofitted later.

`viewer_id` is **unauthenticated** today (gap-audit C3): `run_write` scopes to
whatever viewer it is handed; a forged `viewer_id` is still a forged write. This
epic hardens the query/data layer (a forgotten clause), not the auth boundary
(a forged identity) — that is a separate spec decision.

DB execution is injected (`runner`) so the param-scoping is testable without a
live database; the default runner lazily builds the neo4j driver.
"""

from __future__ import annotations

import os
import random
import time
from collections.abc import Callable, Sequence
from typing import Any

import certifi

from graph.queries import assert_scoped_write

# Aura is reached over neo4j+s:// (strict TLS). Python's ssl module verifies the
# server certificate against the OS trust store, which on some hosts (incl.
# python:3.11-slim before ca-certificates is installed) has no CA bundle Python can
# find — the driver then fails with "Unable to retrieve routing information". Point
# ssl at certifi's bundle BEFORE any driver builds its TLS context (the lazy driver
# below). `setdefault` so an operator-provided value still wins; verification stays
# strict — we keep neo4j+s:// and never downgrade to neo4j+ssc:// or trust-all.
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("SSL_CERT_DIR", os.path.dirname(certifi.where()))

Rows = list[dict[str, Any]]
Runner = Callable[[str, dict[str, Any]], Rows]
# Runs a list of already-scope-merged (cypher, params) in ONE managed transaction.
TxRunner = Callable[[list[tuple[str, dict[str, Any]]]], None]

# Bounded transient-retry for a single autocommit statement (reliability lane). Aura
# server-side-closes idle connections; the first query on a pooled-but-dead connection
# raises SessionExpired / ServiceUnavailable before the driver reconnects, and a
# momentary cluster blip raises TransientError — all of which the *next* attempt on a
# fresh connection clears. Caps keep the worst-case added latency tiny (3 attempts = at
# most 2 short backoffs) so it stays far under /plan's 60s budget.
_RETRY_MAX_ATTEMPTS = 3
_RETRY_BASE_DELAY_S = 0.1
_RETRY_MAX_DELAY_S = 1.0


def _is_retryable(exc: BaseException) -> bool:
    """True for a neo4j error the driver itself marks retryable (ServiceUnavailable /
    SessionExpired / TransientError). Keyed on the driver's own `is_retryable()` so we
    import no neo4j exception types and match its managed-transaction decision *exactly* —
    including that a non-idempotent lost commit (IncompleteCommit) reports False and is
    never retried. A non-neo4j error (no `is_retryable`) is never retried."""
    check = getattr(exc, "is_retryable", None)
    return bool(callable(check) and check())


def _run_with_retry(
    work: Callable[[], Rows],
    *,
    sleep: Callable[[float], None] | None = None,
    jitter: Callable[[], float] | None = None,
) -> Rows:
    """Run `work()` (which opens a *fresh* session each call), retrying on a retryable
    neo4j error so a stale/blipped connection self-heals instead of surfacing a 500. A
    non-retryable error, or the final attempt's, is re-raised unchanged. `sleep`/`jitter`
    resolve at call time so a test can monkeypatch them."""
    do_sleep = time.sleep if sleep is None else sleep
    do_jitter = random.random if jitter is None else jitter
    attempt = 0
    while True:
        try:
            return work()
        except Exception as exc:  # noqa: BLE001 — re-raised unless the driver marks it retryable
            attempt += 1
            if attempt >= _RETRY_MAX_ATTEMPTS or not _is_retryable(exc):
                raise
            delay = min(_RETRY_MAX_DELAY_S, _RETRY_BASE_DELAY_S * (2 ** (attempt - 1)))
            do_sleep(delay + do_jitter() * _RETRY_BASE_DELAY_S)


class ScopedSession:
    """Runs `(cypher, params)` query specs with the viewer's scope merged in."""

    def __init__(
        self,
        viewer_id: str,
        granted_ids: Sequence[str],
        runner: Runner,
        tx_runner: TxRunner | None = None,
        write_runner: Runner | None = None,
    ) -> None:
        self._viewer_id = viewer_id
        self._granted_ids = list(granted_ids)
        self._runner = runner
        self._tx_runner = tx_runner
        # A single owned write executes through its OWN runner in production — one that does
        # NOT auto-retry, because an autocommit write that dies in the post-commit ack window
        # raises a *retryable* error (not IncompleteCommit) and re-running a non-idempotent
        # write would double-apply it (see GraphClient.scoped_session). A test that injects
        # only one fake runner keeps today's behavior: `run_write` falls back to it.
        self._write_runner = write_runner or runner

    def run(self, query: tuple[str, dict[str, Any]]) -> Rows:
        cypher, params = query
        merged = {"viewer_id": self._viewer_id, "granted_ids": self._granted_ids, **params}
        return self._runner(cypher, merged)

    def run_write(self, query: tuple[str, dict[str, Any]]) -> Rows:
        """Write choke point for owned nodes (rule #4, extended to writes). Refuses
        an owned-label `MERGE`/`SET`/`CREATE` lacking an owner-scope clause —
        raising `UnscopedWriteError` *before* the runner is ever called — then
        merges `$viewer_id` / `$granted_ids` exactly as `run` does. World-only
        writes pass through unguarded (they are correctly unowned)."""
        cypher, params = query
        assert_scoped_write(cypher)
        merged = {"viewer_id": self._viewer_id, "granted_ids": self._granted_ids, **params}
        return self._write_runner(cypher, merged)

    def execute_write(self, queries: Sequence[tuple[str, dict[str, Any]]]) -> None:
        """Run several writes in ONE managed transaction — all commit or none
        (atomicity). Each owned-label statement is guarded by `assert_scoped_write`
        and gets `$viewer_id`/`$granted_ids` merged, exactly as `run_write` does;
        unowned writes (e.g. the severed `:CommonsObservation`) pass the guard
        untouched. Used by the commons fork (Epic 010), where the Episode + wires
        and the de-identified observation must commit together (Stage 9 §2.1)."""
        if self._tx_runner is None:
            raise RuntimeError("ScopedSession was built without a transaction runner")
        merged: list[tuple[str, dict[str, Any]]] = []
        for cypher, params in queries:
            assert_scoped_write(cypher)
            merged.append(
                (cypher, {"viewer_id": self._viewer_id, "granted_ids": self._granted_ids, **params})
            )
        self._tx_runner(merged)


class GraphClient:
    """Holds the Neo4j driver and hands out ScopedSessions. Driver built lazily
    (`import neo4j`) so importing this module needs no DB and no neo4j install."""

    def __init__(self, uri: str, user: str, password: str) -> None:
        self._uri = uri
        self._user = user
        self._password = password
        self._driver: Any = None

    def _ensure_driver(self) -> Any:
        if self._driver is None:
            import neo4j  # lazy

            # Resilience config (reliability lane). Aura server-side-closes idle
            # connections after ~300s; the driver's default max_connection_lifetime
            # (3600s) is far longer, so a pooled idle connection can be dead on reuse —
            # the first query then throws SessionExpired/ServiceUnavailable before it
            # reconnects (the intermittent stale-connection 500 this lane targets).
            #   * max_connection_lifetime < the server idle close so a socket is recycled
            #     before Aura can drop it;
            #   * liveness_check_timeout pings a connection idle past it before handing it
            #     out, so a just-expired socket is replaced rather than failing a query;
            #   * connection_acquisition_timeout fails loudly instead of hanging the /plan
            #     fan-out if the pool is exhausted;
            #   * max_transaction_retry_time budgets the managed-transaction retry loop used
            #     by the write-batch path (`tx_runner`'s execute_write) — under /plan's 60s.
            # Single reads/writes get their own bounded retry in `scoped_session` below.
            self._driver = neo4j.GraphDatabase.driver(
                self._uri,
                auth=(self._user, self._password),
                max_connection_lifetime=180,
                liveness_check_timeout=30,
                connection_acquisition_timeout=30,
                max_transaction_retry_time=15,
            )
        return self._driver

    def scoped_session(self, viewer_id: str, granted_ids: Sequence[str] = ()) -> ScopedSession:
        # READS (`run`) are wrapped in a bounded transient-retry so a stale Aura connection
        # (or a momentary cluster blip) self-heals on a fresh connection instead of surfacing
        # a 500 — this is the /plan hot path the reliability lane targets. Retry is
        # unconditionally safe here because a read has no side effects.
        #
        # A single WRITE (`run_write`) is deliberately NOT retried: an autocommit statement
        # emits no CommitResponse, so a connection death in the post-commit ack window raises
        # a *retryable* ServiceUnavailable/SessionExpired (never IncompleteCommit), and
        # re-running a non-idempotent owned write (e.g. episode_count = ...+1) would
        # double-apply it. This matches the pre-lane write behavior (no retry). Atomic
        # multi-write batches instead go through `tx_runner`'s managed `execute_write`, which
        # DOES retry safely because its true lost-commit surfaces as (non-retryable)
        # IncompleteCommit.
        #
        # The $viewer_id/$granted_ids scope merge already happened in ScopedSession (rule #4);
        # these runners only execute the finished (cypher, params) — never the query text — so
        # access control is unchanged either way.
        def read_runner(cypher: str, params: dict[str, Any]) -> Rows:
            def work() -> Rows:
                driver = self._ensure_driver()
                with driver.session() as session:
                    return [record.data() for record in session.run(cypher, **params)]

            return _run_with_retry(work)

        def write_runner(cypher: str, params: dict[str, Any]) -> Rows:
            driver = self._ensure_driver()
            with driver.session() as session:
                return [record.data() for record in session.run(cypher, **params)]

        def tx_runner(merged_queries: list[tuple[str, dict[str, Any]]]) -> None:
            driver = self._ensure_driver()
            with driver.session() as session:

                def work(tx: Any) -> None:
                    for cypher, params in merged_queries:
                        tx.run(cypher, **params)

                session.execute_write(work)  # commits on success, rolls back on raise

        return ScopedSession(viewer_id, granted_ids, read_runner, tx_runner, write_runner)

    def verify_connectivity(self) -> None:
        """Eagerly build the driver and check the server is reachable (raises on failure).
        Called best-effort at API startup so a dead pool is detected — and the connection
        pool warmed — before the first /plan, rather than on a user's request."""
        self._ensure_driver().verify_connectivity()

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None
