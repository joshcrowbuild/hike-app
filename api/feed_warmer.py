"""Default-frame feed warmer (Epic 039 mitigation ladder B5).

Keeps the anonymous feed cache warm for the common path: on API startup (once the
/plan warm-up readiness gate opens) and then on an env-tunable cadence
(ADVENTURE_FEED_WARM_INTERVAL_S; 0 disables), self-invoke the plan pipeline
**in-process** for each region's default frame — the query/origin/k the frontend
sends before any tuning. The warmed plans land in the same `FeedCache` singleton
viewer requests read (`orchestration/feed_cache.py`), so the first anonymous
visitor after a deploy or a TTL expiry hits a warm cache instead of paying the
cold pipeline. Nothing is persisted — a warmed plan is in-process state with the
cache's own TTL, never a graph node (Rule #3).

Enrichment posture (Rule #6): the warmer never blocks startup (a daemon thread
parked behind the readiness gate) and a warm failure never breaks serving — each
frame is isolated, and every failure degrades to exactly today's behavior: the
next real request pays the cold cost. Concurrency with real traffic is safe by
construction: a request for the same frame either hits the warmed entry or meets
the warmer inside the cache's single-flight gate, the same way two concurrent
identical requests already do.

Cost honesty: a warm run spends real LLM tokens and probe quota on the viewers'
behalf ahead of time. Every run that computes emits the same `PlanMetrics` line a
request would, stamped `warmed=True` — the cadence's spend stays measured, never
hidden. A skip (frame still fresh) spends nothing and emits nothing.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from api.observability import (
    PlanMetrics,
    cache_size,
    estimate_tokens,
    probe_stats_snapshot,
    scrub_viewer,
)

# The private-name imports are deliberate: `_anon_key` IS the cache's key derivation
# (the warmer must prime exactly the keys `plan()` reads), and importing it beats
# adding a public alias to merge-sensitive engine.py for one internal caller.
from orchestration.engine import _anon_key, build_runtime
from orchestration.engine import plan as engine_plan
from orchestration.regions import list_regions

log = logging.getLogger(__name__)

# The frontend's untouched default frame, mirrored from frontend/src/App.tsx's
# `defaultState` folded through frontend/src/data/buildQuery.ts: prompt "" +
# when "weekend morning" + effort "moderate" + party solo ("") + today standard
# ("") → this exact string. If the frontend default tuning changes, this must
# change with it or the warmer primes a frame nobody requests.
DEFAULT_FRAME_QUERY = "weekend morning moderate"
# httpPlanner.ts sends `k: input.k ?? 10` — the picker never sets k.
DEFAULT_FRAME_K = 10

# How often the parked warmer re-checks the readiness gate before its first round.
_READY_POLL_S = 1.0


@dataclass(frozen=True)
class WarmFrame:
    """One region's default /plan input — the frame to keep warm."""

    region_id: str
    origin_key: str
    query: str
    lat: float
    lon: float
    k: int


def default_frames() -> list[WarmFrame]:
    """Each region's default frame, derived from the same `regions/*.geojson`
    config the frontend picker is served (`GET /regions`). The FIRST origin in a
    region's config is its canonical default — config order encodes it (e.g.
    shenandoah-gwj lists frontRoyal first, which is exactly the frontend's
    `defaultState.origin`). A region with no origins has no default frame."""
    frames: list[WarmFrame] = []
    for region in list_regions():
        if not region.origins:
            continue
        origin = region.origins[0]
        frames.append(
            WarmFrame(
                region_id=region.region_id,
                origin_key=origin.key,
                query=DEFAULT_FRAME_QUERY,
                lat=origin.lat,
                lon=origin.lon,
                k=DEFAULT_FRAME_K,
            )
        )
    return frames


class FeedWarmer:
    """Background default-frame warmer. `start()` parks a daemon thread behind
    `ready` (the /plan warm-up gate) so warming never races a still-cold
    dependency stack, then runs a round immediately and every `interval_s` after.
    Collaborators are injectable so tests run hermetically with fakes."""

    def __init__(
        self,
        settings: Any,
        graph_client: Any,
        *,
        ready: threading.Event,
        interval_s: float,
        frames: Callable[[], Iterable[WarmFrame]] = default_frames,
        build_runtime_fn: Callable[..., Any] = build_runtime,
        plan_fn: Callable[..., Any] = engine_plan,
    ) -> None:
        self._settings = settings
        self._graph_client = graph_client
        self._ready = ready
        self._interval_s = interval_s
        self._frames = frames
        self._build_runtime = build_runtime_fn
        self._plan = plan_fn
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Spawn the warm loop — or no-op (logged) when disabled. Disabled when the
        cadence is 0 (the operator kill switch) or when the anonymous feed cache
        itself is off (warming would compute plans nothing ever reads)."""
        if self._interval_s <= 0:
            log.info("feed warmer disabled (ADVENTURE_FEED_WARM_INTERVAL_S=0)")
            return
        if getattr(self._settings, "feed_cache_ttl_s", 0) <= 0:
            log.info("feed warmer disabled: anonymous feed cache is off (nothing to prime)")
            return
        self._thread = threading.Thread(target=self._loop, daemon=True, name="feed-warmer")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def run_round(self) -> int:
        """Warm every default frame once, isolating each frame's failure (a broken
        region/provider must not starve the rest of the round — Rule #6). Returns
        how many frames actually computed (skips and failures excluded)."""
        warmed = 0
        for frame in self._frames():
            if self._stop.is_set():
                break
            try:
                if self._warm_frame(frame):
                    warmed += 1
            except Exception:
                log.exception(
                    "feed warm failed region=%s origin=%s; next request pays the cold cost",
                    frame.region_id,
                    frame.origin_key,
                )
        return warmed

    def _warm_frame(self, frame: WarmFrame) -> bool:
        """Warm one frame through the real request path (`build_runtime` +
        `engine.plan`, viewer anonymous) so the cached entry is byte-identical to
        what a request would have computed. Skips without spending when the frame
        is still fresh (`peek` — never counts against the cache's hit/miss stats)."""
        runtime = self._build_runtime(self._settings, self._graph_client, "anonymous")
        feed_cache = runtime.feed_cache
        if feed_cache is None:  # cache kill-switched after start — nothing to prime
            return False
        if feed_cache.peek(_anon_key(frame.query, (frame.lat, frame.lon), frame.k)):
            return False  # still warm — spend nothing
        started = time.perf_counter()
        cache_before = cache_size(runtime.cache)
        stats_before = probe_stats_snapshot(runtime.cache)
        feed = self._plan(
            frame.query, (frame.lat, frame.lon), runtime, k=frame.k, viewer_id="anonymous"
        )
        # Metrics honesty, mirroring api/app.py's /plan route: a hit-after-wait
        # (a concurrent request computed this frame inside the single-flight gate)
        # spent nothing here, so its tokens are zeroed, not re-estimated.
        feed_cache_hit = bool(getattr(runtime, "feed_cache_hit", False))
        if feed_cache_hit:
            est_tokens = 0
        else:
            line_texts = [line.text for card in feed.cards for line in card.lines]
            est_tokens = estimate_tokens(frame.query, *line_texts)
        PlanMetrics(
            viewer_tag=scrub_viewer("anonymous"),
            latency_ms=(time.perf_counter() - started) * 1000,
            card_count=len(feed.cards),
            cache_entries_before=cache_before,
            cache_entries_after=cache_size(runtime.cache),
            est_tokens=est_tokens,
            probe_stats_before=stats_before,
            probe_stats_after=probe_stats_snapshot(runtime.cache),
            feed_cache_hit=feed_cache_hit,
            warmed=True,
        ).emit()
        return True

    def _loop(self) -> None:
        # Park behind the readiness gate: warming before the dependency stack has
        # verified would just hammer whatever /health is still waiting on.
        while not self._ready.is_set():
            if self._stop.wait(_READY_POLL_S):
                return
        while not self._stop.is_set():
            try:
                self.run_round()
            except Exception:  # belt-and-braces: the loop itself must never die
                log.exception("feed warm round failed; retrying on the next cadence")
            if self._stop.wait(self._interval_s):
                return
