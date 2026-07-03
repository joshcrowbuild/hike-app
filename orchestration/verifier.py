"""Verifier — JIT live verification (Stage 4 §4; Epic 013 reshape; latency follow-up).

`verify` iterates a kind-keyed registry of `LiveAdapter`s with health-driven
primary→fallback: for each `ConditionKind` it calls the first adapter whose
`health()` permits, falling to the next on `down`/`rate_limited`, and keeps only the
facts that actually returned. Source-or-silence (rule #1) is preserved byte-for-byte
— a probe that returns None contributes nothing, so the engine can never surface an
unsourced fact. Live readings are returned, never persisted as graph nodes (rule #3).

`verify_batch` is the same per-point contract, fanned out across many points at
once: every (point, kind) probe runs concurrently across a bounded thread pool
instead of the caller walking candidates one at a time, so wall-clock for a k-candidate
`/plan` is ~one probe's latency instead of `k * len(kinds)` serial round-trips. Both
functions share one resolution routine (`_resolve_kind`) so failover/cache/source-or-
silence semantics can't drift between the sequential and batched paths.

`build_probes` is gone — the per-source `import`/`partial`/`if settings.<x>_key`
ladder moved into each adapter's `from_config` and the registry (Epic 013 C6 fix).
`drive_time` is origin-relative and handled in ranking/pre-filter, not here (AC-5.3).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor

from orchestration.adapters.base import (
    AdapterHealth,
    ConditionKind,
    LiveAdapter,
    Point,
    VerifiedFact,
)
from orchestration.adapters.registry import TTLCache

_UNHEALTHY = (AdapterHealth.DOWN, AdapterHealth.RATE_LIMITED)

# Bound on concurrent (point, kind) probes in `verify_batch`'s fan-out. k candidates x
# up to 5 kinds (weather/air/fire/water/permits) can mean up to 50 tasks for one
# `/plan`; this caps how many run at once regardless of k so a busy request can't
# hammer a rate-limited third-party source (a slow/limited source still degrades to
# None via source-or-silence — this cap is about politeness, not correctness).
DEFAULT_MAX_WORKERS = 8


def _resolve_kind(
    point: Point,
    adapters: list[LiveAdapter],
    *,
    cache: TTLCache | None,
) -> VerifiedFact | None:
    """The one-kind primary→fallback resolution shared by `verify` and
    `verify_batch`: a still-fresh cache hit short-circuits the liveness check, an
    unhealthy adapter (only worth checking when a fallback exists) is skipped, and
    the first adapter that actually returns wins. `None` when every adapter is
    health-blocked or silent (source-or-silence, rule #1)."""
    has_fallback = len(adapters) > 1
    for adapter in adapters:
        if cache is not None:
            cached = cache.peek(adapter, point)
            if cached is not None:
                return cached
        if has_fallback and adapter.health() in _UNHEALTHY:
            continue  # down/rate_limited → fall to the next adapter for this kind
        fact = cache.probe(adapter, point) if cache is not None else adapter.probe(point)
        if fact is not None:
            return fact
    return None


def verify(
    point: Point,
    probes_by_kind: Mapping[ConditionKind, list[LiveAdapter]],
    *,
    cache: TTLCache | None = None,
) -> dict[ConditionKind, VerifiedFact]:
    """For each kind, return the first adapter's fact whose `health()` permits and
    whose `probe()` returned — keep-only-what-returned (rule #1). `drive_time` is
    skipped (origin-relative; resolved in ranking/pre-filter — AC-5.3). A kind whose
    every adapter is health-blocked or returns None is simply absent (AC-3.3)."""
    facts: dict[ConditionKind, VerifiedFact] = {}
    for kind, adapters in probes_by_kind.items():
        if kind is ConditionKind.drive_time:
            continue
        fact = _resolve_kind(point, adapters, cache=cache)
        if fact is not None:
            facts[kind] = fact
    return facts


def _cache_round_key(point: Point) -> tuple[float, float]:
    """Mirror `TTLCache._key`'s coordinate rounding so points that would collapse to
    the same cache entry anyway are coalesced BEFORE fan-out. Weather/AQI/streamflow/
    fire/permits don't vary at ~100 m, so this changes no result (same trails, same
    conditions) — it only means a batch of nearby candidates shares one underlying
    probe instead of racing several concurrent duplicates at the same rate-limited
    source (the TTLCache's network call runs outside its lock by design, so without
    this the concurrent path could double-spend a call the sequential path would
    have served from cache)."""
    return (round(point.lat, 3), round(point.lon, 3))


def verify_batch(
    points: Sequence[Point],
    probes_by_kind: Mapping[ConditionKind, list[LiveAdapter]],
    *,
    cache: TTLCache | None = None,
    max_workers: int = DEFAULT_MAX_WORKERS,
) -> list[dict[ConditionKind, VerifiedFact]]:
    """Batch counterpart to `verify`: returns one facts dict per input point, aligned
    by index, equal to `[verify(p, probes_by_kind, cache=cache) for p in points]` —
    every (point, kind) task still runs `_resolve_kind`'s exact sequential
    primary→fallback + source-or-silence logic; only the *tasks* run concurrently, so
    wall-clock is ~one probe's latency instead of `len(points) * len(kinds)`.

    Points that round to the same TTLCache key are coalesced to one task before
    fan-out (see `_cache_round_key`) — this only removes duplicate concurrent probes
    against an identical cache key, never changes which source answers or what it
    returns. `max_workers` bounds total in-flight probes for the whole call."""
    results: list[dict[ConditionKind, VerifiedFact]] = [{} for _ in points]
    if not points:
        return results
    kinds = [
        kind
        for kind, adapters in probes_by_kind.items()
        if kind is not ConditionKind.drive_time and adapters
    ]
    if not kinds:
        return results

    groups: dict[tuple[float, float], list[int]] = {}
    for i, point in enumerate(points):
        groups.setdefault(_cache_round_key(point), []).append(i)
    representative: dict[tuple[float, float], Point] = {
        key: points[idxs[0]] for key, idxs in groups.items()
    }
    tasks: list[tuple[tuple[float, float], ConditionKind]] = [
        (key, kind) for key in groups for kind in kinds
    ]

    def _run(
        task: tuple[tuple[float, float], ConditionKind],
    ) -> tuple[tuple[float, float], ConditionKind, VerifiedFact | None]:
        key, kind = task
        fact = _resolve_kind(representative[key], probes_by_kind[kind], cache=cache)
        return key, kind, fact

    workers = max(1, min(max_workers, len(tasks)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for key, kind, fact in pool.map(_run, tasks):
            if fact is None:
                continue
            for i in groups[key]:
                results[i][kind] = fact
    return results
