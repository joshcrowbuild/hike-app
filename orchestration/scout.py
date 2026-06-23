"""Scout — candidate generation (Stage 4 §3).

Mostly deterministic: a scoped Cypher traversal (via graph.queries) for trails
near the origin, mapped to Candidates, deduped to the nearest trailhead per trail,
and capped to top-K before the expensive Verifier stage. Runs through a
ScopedSession so access control (#4) is honored at the query layer. Free-text
intent parsing (the optional mechanical-tier LLM call) is added later; structured
inputs skip it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from graph import queries
from graph.client import ScopedSession


@dataclass(frozen=True)
class Candidate:
    canonical_id: str
    name: str
    trailhead_id: str
    distance_m: float
    area_id: str | None = None
    is_loop: bool | None = None
    length_mi: float | None = None
    point: Any = None


def _row_to_candidate(row: dict[str, Any]) -> Candidate:
    return Candidate(
        canonical_id=row["canonical_id"],
        name=row.get("name") or "",
        trailhead_id=row.get("trailhead_id") or "",
        distance_m=float(row.get("distance_m") or 0.0),
        area_id=row.get("area_id"),
        is_loop=row.get("is_loop"),
        length_mi=row.get("length_mi"),
        point=row.get("point"),
    )


def scout(
    lat: float,
    lon: float,
    session: ScopedSession,
    *,
    radius_m: float = 40_000.0,
    k: int = 10,
) -> list[Candidate]:
    """Return up to `k` nearest candidate trails within `radius_m` of the origin,
    one entry per trail (the nearest trailhead wins)."""
    rows = session.run(queries.candidate_trails_near(lat, lon, radius_m, k))

    seen: set[str] = set()
    out: list[Candidate] = []
    for candidate in sorted((_row_to_candidate(r) for r in rows), key=lambda c: c.distance_m):
        if candidate.canonical_id in seen:
            continue
        seen.add(candidate.canonical_id)
        out.append(candidate)
    return out[:k]
