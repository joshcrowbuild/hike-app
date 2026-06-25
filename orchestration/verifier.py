"""Verifier — JIT live verification (Stage 4 §4; Epic 013 reshape).

`verify` iterates a kind-keyed registry of `LiveAdapter`s with health-driven
primary→fallback: for each `ConditionKind` it calls the first adapter whose
`health()` permits, falling to the next on `down`/`rate_limited`, and keeps only the
facts that actually returned. Source-or-silence (rule #1) is preserved byte-for-byte
— a probe that returns None contributes nothing, so the engine can never surface an
unsourced fact. Live readings are returned, never persisted as graph nodes (rule #3).

`build_probes` is gone — the per-source `import`/`partial`/`if settings.<x>_key`
ladder moved into each adapter's `from_config` and the registry (Epic 013 C6 fix).
`drive_time` is origin-relative and handled in ranking/pre-filter, not here (AC-5.3).
"""

from __future__ import annotations

from collections.abc import Mapping

from orchestration.adapters.base import (
    AdapterHealth,
    ConditionKind,
    LiveAdapter,
    Point,
    VerifiedFact,
)
from orchestration.adapters.registry import TTLCache

_UNHEALTHY = (AdapterHealth.DOWN, AdapterHealth.RATE_LIMITED)


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
        # health() gates failover, so it is only worth a round-trip when a fallback
        # candidate actually exists. For a lone adapter (the common case), probe directly
        # and let a None drive source-or-silence — no wasted GET, no quota spent, no
        # self-inflicted rate-limiting on the keyed sources.
        has_fallback = len(adapters) > 1
        for adapter in adapters:
            # A still-fresh cache hit short-circuits the liveness check + probe call.
            if cache is not None:
                cached = cache.peek(adapter, point)
                if cached is not None:
                    facts[kind] = cached
                    break
            if has_fallback and adapter.health() in _UNHEALTHY:
                continue  # down/rate_limited → fall to the next adapter for this kind
            fact = cache.probe(adapter, point) if cache is not None else adapter.probe(point)
            if fact is not None:
                facts[kind] = fact
                break  # first success wins per kind
    return facts
