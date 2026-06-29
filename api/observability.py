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

import hashlib
import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("api.observability")

# Rough blended (input+output) USD per 1K tokens for the cloud yardstick model. Estimate
# only; overridable via `ADVENTURE_LLM_USD_PER_1K` so a price change isn't a code change.
_DEFAULT_USD_PER_1K = 0.009


def scrub_viewer(viewer_id: str) -> str:
    """A short, stable, non-reversible tag for a viewer (Rule #5). `anonymous` stays
    legible as `anon`; any real identity becomes an 8-hex digest, enough to correlate a
    session's calls in the logs without carrying the identity itself.

    A bare SHA-256 of a low-entropy identifier (e.g. an email) is *confirmable* — anyone
    who guesses the value can verify it by re-hashing. Mixing in a deployment-private salt
    (`ADVENTURE_LOG_HASH_SALT`) defeats that while keeping the tag stable within a deploy.
    The salt is optional: absent it, the digest is still non-reversible and adequate for
    log correlation."""
    if viewer_id == "anonymous":
        return "anon"
    salt = os.environ.get("ADVENTURE_LOG_HASH_SALT", "")
    return "vh:" + hashlib.sha256((salt + viewer_id).encode("utf-8")).hexdigest()[:8]


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
    def est_cost_usd(self) -> float:
        return round(self.est_tokens / 1000 * _usd_per_1k(), 6)

    def emit(self) -> None:
        logger.info(
            "plan viewer=%s latency_ms=%.1f cards=%d cache=%d->%d miss=%d warm=%s "
            "est_tokens=%d est_cost_usd=%.6f",
            self.viewer_tag,
            self.latency_ms,
            self.card_count,
            self.cache_entries_before,
            self.cache_entries_after,
            self.cache_misses,
            self.cache_warm,
            self.est_tokens,
            self.est_cost_usd,
        )
