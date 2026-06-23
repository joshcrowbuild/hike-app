"""Neo4j access — permission-scoped from the first query (rule #4 / thread T2).

Every read goes through a `ScopedSession`, which injects the viewer's identity
(`$viewer_id` / `$granted_ids`) into every statement's params. Combined with the
`graph.queries` builders — the only sanctioned place to write Cypher touching
owned nodes — this is the single choke point that guarantees no query returns
ungranted nodes. Phase 0 is single-user, but the seam exists now so it can't be
retrofitted later.

DB execution is injected (`runner`) so the param-scoping is testable without a
live database; the default runner lazily builds the neo4j driver.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

Rows = list[dict[str, Any]]
Runner = Callable[[str, dict[str, Any]], Rows]


class ScopedSession:
    """Runs `(cypher, params)` query specs with the viewer's scope merged in."""

    def __init__(self, viewer_id: str, granted_ids: Sequence[str], runner: Runner) -> None:
        self._viewer_id = viewer_id
        self._granted_ids = list(granted_ids)
        self._runner = runner

    def run(self, query: tuple[str, dict[str, Any]]) -> Rows:
        cypher, params = query
        merged = {"viewer_id": self._viewer_id, "granted_ids": self._granted_ids, **params}
        return self._runner(cypher, merged)


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

        return ScopedSession(viewer_id, granted_ids, runner)

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None
