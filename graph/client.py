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

from collections.abc import Callable, Sequence
from typing import Any

from graph.queries import assert_scoped_write

Rows = list[dict[str, Any]]
Runner = Callable[[str, dict[str, Any]], Rows]
# Runs a list of already-scope-merged (cypher, params) in ONE managed transaction.
TxRunner = Callable[[list[tuple[str, dict[str, Any]]]], None]


class ScopedSession:
    """Runs `(cypher, params)` query specs with the viewer's scope merged in."""

    def __init__(
        self,
        viewer_id: str,
        granted_ids: Sequence[str],
        runner: Runner,
        tx_runner: TxRunner | None = None,
    ) -> None:
        self._viewer_id = viewer_id
        self._granted_ids = list(granted_ids)
        self._runner = runner
        self._tx_runner = tx_runner

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
        return self._runner(cypher, merged)

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

            self._driver = neo4j.GraphDatabase.driver(self._uri, auth=(self._user, self._password))
        return self._driver

    def scoped_session(self, viewer_id: str, granted_ids: Sequence[str] = ()) -> ScopedSession:
        def runner(cypher: str, params: dict[str, Any]) -> Rows:
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

        return ScopedSession(viewer_id, granted_ids, runner, tx_runner)

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None
