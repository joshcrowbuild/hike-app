"""Minimal structured observability for the `/plan` fan-out (Phase B).

`/plan` is the one endpoint that spends real money and quota per call (live third-party
probes + an LLM). To run it on a public deploy we need to *see* each call's cost and
latency — without leaking who made it. Each call emits one structured log line carrying:

- wall-clock latency,
- live-probe cache movement (a warm cache means the fan-out spent no third-party quota),
- an *estimated* LLM token + dollar cost derived from the query and rendered feed.

The cost is an estimate, not billed truth: the provider seam has no real usage hook yet,
so the figure is labelled `est_*` and is never surfaced to a user (Rule #1 —
unverifiable facts are flagged, not fabricated).

`viewer_id` is NEVER logged in the clear. It is reduced to a short non-reversible digest
so a session's calls can be correlated for debugging without putting an identity into the
logs (Rule #5: the private overlay's identity is substrate, not telemetry).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

# Canonical home is orchestration.logsafe (importable by every layer without a
# layering inversion); re-exported here so existing `api.observability` call
# sites keep working.
from orchestration.logsafe import scrub_viewer

__all__ = [
    "PlanMetrics",
    "cache_size",
    "estimate_tokens",
    "probe_stats_snapshot",
    "scrub_viewer",
]

logger = logging.getLogger("api.observability")

# Rough blended (input+output) USD per 1K tokens for the cloud yardstick model. Estimate
# only; overridable via `ADVENTURE_LLM_USD_PER_1K` so a price change isn't a code change.
_DEFAULT_USD_PER_1K = 0.009


def estimate_tokens(*texts: str) -> int:
    """~4 chars/token, the standard rough English estimate, summed over every supplied
    string (the query plus each rendered card line) for a whole-request figure."""
    chars = sum(len(t) for t in texts if t)
    return (chars + 3) // 4


def cache_size(cache: Any) -> int:
    """Live-probe cache occupancy, read defensively. The TTLCache keeps entries in a
    private `_store` dict; a `None` cache or an unexpected shape reads as 0 so
    observability can never break the request path."""
    store = getattr(cache, "_store", None)
    return len(store) if store is not None else 0


def probe_stats_snapshot(cache: Any) -> Any:
    """A detached snapshot of the live-probe cost/latency counters (Epic 018 S6 AC-6.1),
    read defensively. The TTLCache exposes cumulative `stats` (a ProbeStats); a `None`
    cache or a stub without one yields a zeroed ProbeStats so the route can snapshot
    before/after unconditionally and observability can never break the request path."""
    from orchestration.adapters.registry import ProbeStats

    stats = getattr(cache, "stats", None)
    return stats.snapshot() if stats is not None else ProbeStats()


def _usd_per_1k() -> float:
    raw = os.environ.get("ADVENTURE_LLM_USD_PER_1K")
    if raw is None:
        return _DEFAULT_USD_PER_1K
    try:
        return float(raw)
    except ValueError:
        return _DEFAULT_USD_PER_1K


@dataclass
class PlanMetrics:
    """One `/plan` call's cost/latency record. Built in the route, then `emit()`-ted as a
    single structured log line."""

    viewer_tag: str
    latency_ms: float
    card_count: int
    cache_entries_before: int
    cache_entries_after: int
    est_tokens: int
    # Live fan-out cost/latency (Epic 018 S6 AC-6.1): before/after snapshots of the
    # cache's cumulative ProbeStats. Deltas give this request's true third-party call
    # count and per-kind wall-clock (defaulted so the field is optional at call sites /
    # in tests). `Any` to avoid a hard import cycle back into the adapter registry here.
    probe_stats_before: Any = None
    probe_stats_after: Any = None
    # Engine-layer anonymous plan cache (Epic 039 S2): True when this /plan was served
    # from `FeedCache` — no intent-parse or taste-rank LLM call ran and no live probe
    # fired. The caller (api/app.py) is responsible for zeroing `est_tokens` on a hit
    # rather than estimating it from the (still rendered) cached card text, or the
    # log would fabricate spend that was never spent. `live_calls`/`cache_hits`/
    # `cache_misses` below already read as zero on a hit without any special-casing,
    # since `probe_stats_before`/`_after` are unchanged when no probe ran.
    feed_cache_hit: bool = False

    @property
    def cache_misses(self) -> int:
        """New live-probe entries — each is a third-party call actually spent this request.
        A size delta, so it under-counts when the cache is at its FIFO cap (an insertion
        that evicts an old entry leaves the size flat): a coarse cost signal, not exact."""
        return max(0, self.cache_entries_after - self.cache_entries_before)

    @property
    def cache_warm(self) -> bool:
        """True when the fan-out added no entries and the cache was already populated —
        i.e. served entirely from cache (a clean hit)."""
        return self.cache_misses == 0 and self.cache_entries_before > 0

    @property
    def live_calls(self) -> int:
        """This request's true underlying third-party probe count (miss delta) — exact,
        unlike `cache_misses` which under-counts at the FIFO cap. 0 when stats absent."""
        return max(0, self._after("misses") - self._before("misses"))

    @property
    def cache_hits(self) -> int:
        """Probes this request served from the TTL cache — quota the tuned windows saved."""
        return max(0, self._after("hits") - self._before("hits"))

    @property
    def wall_ms_by_kind(self) -> dict[str, float]:
        """Per-`ConditionKind` underlying-probe wall-clock spent this request (after−before,
        per kind), so a slow source is visible. Empty when stats absent (AC-6.1)."""
        before = getattr(self.probe_stats_before, "wall_ms_by_kind", {}) or {}
        after = getattr(self.probe_stats_after, "wall_ms_by_kind", {}) or {}
        out: dict[str, float] = {}
        for kind, ms in after.items():
            delta = round(ms - before.get(kind, 0.0), 1)
            if delta > 0:
                out[kind] = delta
        return out

    def _before(self, attr: str) -> int:
        return int(getattr(self.probe_stats_before, attr, 0) or 0)

    def _after(self, attr: str) -> int:
        return int(getattr(self.probe_stats_after, attr, 0) or 0)

    @property
    def est_cost_usd(self) -> float:
        return round(self.est_tokens / 1000 * _usd_per_1k(), 6)

    def emit(self) -> None:
        logger.info(
            "plan viewer=%s latency_ms=%.1f cards=%d cache=%d->%d miss=%d warm=%s "
            "live_calls=%d cache_hits=%d wall_by_kind=%s est_tokens=%d est_cost_usd=%.6f "
            "feed_cache_hit=%s",
            self.viewer_tag,
            self.latency_ms,
            self.card_count,
            self.cache_entries_before,
            self.cache_entries_after,
            self.cache_misses,
            self.cache_warm,
            self.live_calls,
            self.cache_hits,
            self.wall_ms_by_kind,
            self.est_tokens,
            self.est_cost_usd,
            self.feed_cache_hit,
        )
