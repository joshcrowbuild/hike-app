"""Leveled abs+rel per-facet ingest diff (Epic 027) — the finer tier ABOVE the
existing scalar guards (`ADVENTURE_PRUNE_MIN_RATIO`, `verify_before_prune`), not a
replacement for them. Ports the `norm(diff) > abs AND get_rel(diff) > rel` leveled-
threshold idiom from CoMaps `maps_generator/checks/default_check_set.py` /
`check.py` — pattern only, not the two-immutable-directories substrate (CoMaps
borrow plan B1.2).

Within-run only (B1.3): the comparison is this region's pre-load facet snapshot vs.
this run's post-load facet snapshot — nothing is frozen to disk as a cross-run
baseline. `graph/load.py`'s `count_region_facets`/`count_version_facets` produce
the two `dict[str, int]` inputs this module diffs; `ingestion/pipeline.py` wires
the result into the prune gate.

Pure stdlib — no third-party dependency (AC-1.1).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import NamedTuple, Protocol, TypeVar

# Four sensitivity levels, coarsest (least sensitive, biggest change required) first.
# Thresholds nest — any bucket breaching `low` necessarily also breaches every level
# after it — which is what lets `breached_level` report the COARSEST level cleared
# and have that monotonically encode severity (`low` = most severe, `strict` =
# mildest; Design Decision 4). Scaled down from CoMaps' `types` matrix
# (`low=(500,30) medium=(100,20) hard=(100,10)`) for ~1500-trail regional scale.
LEVELS: dict[str, tuple[float, float]] = {
    "low": (100.0, 50.0),
    "medium": (50.0, 30.0),
    "hard": (25.0, 20.0),
    "strict": (10.0, 10.0),
}

# The levels that gate the prune (AC-1.6): `hard` or any coarser (more severe) level.
# A bucket clearing only `strict` never lands here — routine per-run churn must not
# block a healthy re-ingest (B1.4).
_HARD_OR_COARSER = frozenset({"low", "medium", "hard"})

_DEFAULT_STATS_DIR = "data/ingest_stats"


class FacetRow(NamedTuple):
    """One bucket's diff. `_asdict()` gives the exact `stats.json` bucket shape
    (AC-3.7)."""

    dimension: str
    value: str
    pre: int
    post: int
    delta: int
    rel_pct: float
    breached_level: str | None


def get_rel(delta: int, pre: int) -> float:
    """`abs(delta) * 100 / pre`, with `pre == 0` yielding `100.0` — ported from
    CoMaps `check.py`'s `get_rel` (AC-1.3): a bucket with no prior baseline (a
    brand-new facet value) is treated as maximally changed rather than dividing by
    zero."""
    if pre == 0:
        return 100.0
    return abs(delta) * 100 / pre


def _breaches(delta: int, rel_pct: float, threshold: tuple[float, float]) -> bool:
    abs_threshold, rel_threshold = threshold
    return abs(delta) > abs_threshold and rel_pct > rel_threshold


def breached_level(delta: int, rel_pct: float) -> str | None:
    """The coarsest level this `(delta, rel_pct)` pair breaches (AC-1.2/1.4), or
    `None` if it clears none. Checks `LEVELS` in its (coarsest-first) declaration
    order and returns on the first match, so the result is the LEAST-sensitive level
    breached — not the most-sensitive, which would collapse every non-null bucket to
    `'strict'` (Design Decision 4)."""
    for name, threshold in LEVELS.items():
        if _breaches(delta, rel_pct, threshold):
            return name
    return None


def diff_facets(pre: dict[str, int], post: dict[str, int]) -> list[FacetRow]:
    """One row per bucket key present in EITHER snapshot (AC-1.5). A bucket that
    vanished entirely (`post=0, pre>0`) still appears, with `delta = -pre`; a
    brand-new bucket (`pre=0`) appears with `rel_pct=100.0` (see `get_rel`)."""
    rows: list[FacetRow] = []
    for key in sorted(set(pre) | set(post)):
        dimension, _, value = key.partition("=")
        pre_v = pre.get(key, 0)
        post_v = post.get(key, 0)
        delta = post_v - pre_v
        rel_pct = get_rel(delta, pre_v)
        rows.append(
            FacetRow(
                dimension=dimension,
                value=value,
                pre=pre_v,
                post=post_v,
                delta=delta,
                rel_pct=rel_pct,
                breached_level=breached_level(delta, rel_pct),
            )
        )
    return rows


def breached_hard(rows: list[FacetRow]) -> list[FacetRow]:
    """The buckets that gate the prune: those breaching `hard` or any coarser
    (more severe) level (AC-1.6). This can only ever be used to BLOCK a prune the
    scalar guards would have allowed, never to permit one they would have blocked
    (B1.4) — callers must not use this result to override `verify_before_prune` or
    `ADVENTURE_PRUNE_MIN_RATIO`."""
    return [r for r in rows if r.breached_level in _HARD_OR_COARSER]


class _HasDelta(Protocol):
    @property
    def delta(self) -> int: ...


_Row = TypeVar("_Row", bound=_HasDelta)


def sorted_by_abs_delta(rows: list[_Row]) -> list[_Row]:
    """`rows` sorted by `abs(delta)` descending — the `stats.json` bucket order
    (AC-3.7) and the ordering `/health`'s `top_deltas` (AC-4.4) selects its top ≤5
    from. Generic over anything carrying a `.delta` int (structurally satisfied by
    both the pipeline's `FacetRow` and the API's `IngestDiffBucket` pydantic model),
    so the writer (`ingestion/pipeline.py`) and reader (`api/app.py`) share one sort
    instead of each hand-rolling an equivalent key function."""
    return sorted(rows, key=lambda r: abs(r.delta), reverse=True)


def ingest_stats_path(region_id: str, base: str | os.PathLike[str] | None = None) -> Path:
    """Where a region's `stats.json` lives — the single shared resolver both the
    pipeline (writer, `ingestion/pipeline.py`) and `/health` (reader, `api/app.py`)
    import, so they always agree on the path (AC-4.1). `base` overrides for tests;
    production resolves `ADVENTURE_INGEST_STATS_DIR`, falling back to
    `data/ingest_stats`."""
    if base is not None:
        root = base
    else:
        root = os.environ.get("ADVENTURE_INGEST_STATS_DIR") or _DEFAULT_STATS_DIR
    return Path(root) / f"{region_id}.json"
