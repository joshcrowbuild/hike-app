"""Scout — candidate generation (Stage 4 §3).

Mostly deterministic: a scoped Cypher traversal (via graph.queries) for trails
near the origin, mapped to Candidates, deduped to the nearest trailhead per trail,
deduped again by trail name (D11 — a trail split into multiple CanonicalTrail
segments must still show as one feed card), and capped to top-K before the
expensive Verifier stage. Runs through a ScopedSession so access control (#4) is
honored at the query layer. Free-text intent parsing (the optional mechanical-tier
LLM call) is added later; structured inputs skip it.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from graph import queries
from graph.client import ScopedSession

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Candidate:
    canonical_id: str
    name: str
    trailhead_id: str
    distance_m: float
    area_id: str | None = None
    is_loop: bool | None = None
    length_mi: float | None = None
    way_type: str | None = None
    outside_boundary: bool | None = None
    point: Any = None
    trailhead_point: Any = None


def _row_to_candidate(row: dict[str, Any]) -> Candidate | None:
    canonical_id = row.get("canonical_id")
    if not canonical_id:
        log.warning("Scout row missing canonical_id — skipping: %r", dict(row))
        return None
    return Candidate(
        canonical_id=canonical_id,
        name=row.get("name") or "",
        trailhead_id=row.get("trailhead_id") or "",
        distance_m=float(row.get("distance_m") or 0.0),
        area_id=row.get("area_id"),
        is_loop=row.get("is_loop"),
        length_mi=row.get("length_mi"),
        way_type=row.get("way_type"),
        outside_boundary=row.get("outside_boundary"),
        point=row.get("point"),
        trailhead_point=row.get("trailhead_point"),
    )


def _norm_name(name: str) -> str:
    """Whitespace/case-normalized trail name — the identity key for presentation
    dedup (D11). Deliberately loose (not the corpus's own identity resolution): two
    OSM ways that were never conflated into one CanonicalTrail (e.g. a canal walk
    split into segments) still read as one trail to a person by name alone."""
    return re.sub(r"\s+", " ", name).strip().casefold()


def _richer(a: Candidate, b: Candidate) -> Candidate:
    """Pick the better representative of two same-name segments: longer wins (a
    missing `length_mi` never beats a known one); nearer breaks a tie."""
    a_len = a.length_mi if a.length_mi is not None else -1.0
    b_len = b.length_mi if b.length_mi is not None else -1.0
    if a_len != b_len:
        return a if a_len > b_len else b
    return a if a.distance_m <= b.distance_m else b


def _dedupe_by_name(candidates: list[Candidate]) -> list[Candidate]:
    """Collapse same-name segments (D11: Richmond's "Canal Walk"/"Pipeline Trail"
    each mapped as multiple CanonicalTrail nodes) to one candidate per distinct
    trail name, keeping the richest (longest, then nearest) segment. Presentation
    only — the corpus keeps every segment node; this just picks one to show.
    An empty/missing name never collapses across candidates (each keys on its own
    canonical_id instead), since there's no name identity to dedupe on."""
    best: dict[str, Candidate] = {}
    for candidate in candidates:
        key = _norm_name(candidate.name) or f"__unnamed__{candidate.canonical_id}"
        best[key] = _richer(best[key], candidate) if key in best else candidate
    return sorted(best.values(), key=lambda c: c.distance_m)


def scout(
    lat: float,
    lon: float,
    session: ScopedSession,
    *,
    radius_m: float = 40_000.0,
    k: int = 10,
) -> list[Candidate]:
    """Return up to `k` nearest candidate trails within `radius_m` of the origin,
    one entry per trail (the nearest trailhead wins). Tops up from a direct
    CanonicalTrail.point query when the trailhead traversal yields fewer than `k`
    trails — covering both a fresh ingest with no Trailhead nodes and an urban region
    (e.g. Richmond) where OSM tags too few trailheads to reach most trails."""
    seen: set[str] = set()
    out: list[Candidate] = []

    def _absorb(rows: list[dict[str, Any]]) -> None:
        candidates = [c for r in rows if (c := _row_to_candidate(r)) is not None]
        for candidate in sorted(candidates, key=lambda c: c.distance_m):
            if candidate.canonical_id in seen:
                continue
            seen.add(candidate.canonical_id)
            out.append(candidate)

    _absorb(session.run(queries.candidate_trails_near(lat, lon, radius_m, k)))

    # Sparse/empty-trailhead top-up: a freshly-ingested urban region can have trails but
    # almost no OSM-tagged Trailhead nodes, so the trailhead traversal returns far fewer
    # than k trails (Richmond returned 1). Fill the remaining slots from the direct
    # CanonicalTrail.point search so point-bearing trails aren't invisible. Trailhead
    # candidates already found keep their trailhead_id (needed for drive-time); direct
    # rows only add trails not already seen. A dense region returns >= k from trailheads,
    # so this second query never runs and its results are unchanged.
    if len(out) < k:
        log.debug(
            "Trailhead traversal yielded %d < k=%d; topping up via direct search", len(out), k
        )
        _absorb(session.run(queries.candidate_trails_near_direct(lat, lon, radius_m, k)))
        out.sort(key=lambda c: c.distance_m)

    return _dedupe_by_name(out)[:k]


def scout_by_name(query_text: str, session: ScopedSession, *, k: int = 10) -> list[Candidate]:
    """Trail-name search candidate generation (Epic 038 / B001 Problem A): a FULLTEXT
    fuzzy match over `CanonicalTrail.name`, best match first. Mirrors `scout()`'s
    absorb/dedupe pattern but is deliberately smaller — there is no spatial top-up (no
    origin to top up from) and, crucially, no re-sort by distance: the FULLTEXT
    relevance ORDER returned by `candidate_trails_by_name` IS the ranking (rule #2 —
    name-match relevance, never confidence, never distance, decides this order), so
    `_dedupe_by_name` here must preserve row order rather than sorting by
    `distance_m` (every row's `distance_m` is null on this path anyway).

    An empty/whitespace-only `query_text` sanitizes to an empty Lucene query string,
    which `db.index.fulltext.queryNodes` rejects at query time — short-circuited here
    (never reaching Cypher) so a blank search is an honest empty result, never a 500."""
    if not query_text or not query_text.strip():
        return []
    rows = session.run(queries.candidate_trails_by_name(query_text, k))
    candidates = [c for r in rows if (c := _row_to_candidate(r)) is not None]
    return _dedupe_by_name_preserving_order(candidates)[:k]


def _dedupe_by_name_preserving_order(candidates: list[Candidate]) -> list[Candidate]:
    """Like `_dedupe_by_name`, but keeps the FIRST-SEEN relative order of the surviving
    keys instead of re-sorting by distance (there is no distance to sort by on the
    name-search path — every candidate's `distance_m` is 0.0/null-mapped). Still keeps
    the richest (longest, then first-seen) segment per distinct name (D11)."""
    best: dict[str, Candidate] = {}
    order: list[str] = []
    for candidate in candidates:
        key = _norm_name(candidate.name) or f"__unnamed__{candidate.canonical_id}"
        if key not in best:
            order.append(key)
            best[key] = candidate
        else:
            best[key] = _richer(best[key], candidate)
    return [best[key] for key in order]
