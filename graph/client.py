"""Neo4j access — permission-scoped from the first query (rule #4 / thread T2).

Every traversal is scoped to the viewer; the engine never emits a query that
could return ungranted nodes. This wrapper is the single choke point that
guarantees it (Stage 2 §7 `scopedQuery(viewer)`). Phase 0 is single-user, but the
seam exists now so it can't be retrofitted later.

Stage 0 ships the contract; the driver wiring (lazy `import neo4j`) lands in
Stage 4.
"""

from __future__ import annotations


def scoped_session(viewer_id: str) -> object:
    """Return a query interface that injects `viewer_id` access scoping into every
    Cypher statement. Implemented in Stage 4."""
    raise NotImplementedError("graph.scoped_session is implemented in Stage 4")
