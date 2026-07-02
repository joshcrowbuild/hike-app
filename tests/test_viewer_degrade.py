"""Personal context never takes down /plan (Rules #6/#7 — enrichment, not dependency).

Regression for the viewer-path 500: on a hosted deploy with no on-device model, the
local-forced personalized judge (Epic 014 privacy routing) fails on every authenticated
/plan while the anonymous path (cloud judge) works. plan() must degrade any failure in
the viewer path — personalized ranking OR context assembly — to the anonymous-quality
feed with a disclosed notice, never an exception. The overlay is STRIPPED from the
fallback rank so it still never reaches the cloud judge (Rule #5).

Fakes only; no DB/network (Epic 008 harness).
"""

from __future__ import annotations

from typing import Any

import pytest

from orchestration.engine import PERSONAL_CONTEXT_UNAVAILABLE_NOTICE, Runtime, plan
from orchestration.providers.base import LLMResponse


def _row(cid: str) -> dict[str, Any]:
    return {
        "canonical_id": cid,
        "name": cid,
        "trailhead_id": "th",
        "distance_m": 100.0,
        "point": {"latitude": 38.5, "longitude": -78.4},
    }


def _belief_row() -> dict[str, Any]:
    """A stated preference surviving the decay/floor filter → non-empty overlay."""
    return {
        "key": "likes_views",
        "value": True,
        "axis": "preference",
        "type": "stated",
        "confidence": 0.8,
        "corroboration_n": 5,
        "decays": False,
        "decay_half_life_days": 90,
        "last_updated_at": None,
    }


class _Session:
    """Fake ScopedSession routing by query text; personal-overlay queries can be
    made to fail or to return rows, world queries return the trail rows."""

    def __init__(
        self,
        belief_rows: list[dict] | None = None,
        episode_rows: list[dict] | None = None,
        fail_overlay: bool = False,
    ) -> None:
        self.belief_rows = belief_rows or []
        self.episode_rows = episode_rows or []
        self.fail_overlay = fail_overlay

    def run(self, query: tuple[str, dict[str, Any]]) -> list[dict[str, Any]]:
        cypher, _ = query
        if "Belief" in cypher or "PhysicalProfile" in cypher or "Episode" in cypher:
            if self.fail_overlay:
                raise RuntimeError("overlay query failed (e.g. dangling post-prune reference)")
            if "Belief" in cypher:
                return self.belief_rows
            if "Episode" in cypher:
                return self.episode_rows
            return []
        return [_row("a"), _row("b"), _row("c")]


class _SpyJudge:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[Any] = []

    def complete(self, request: Any) -> LLMResponse:
        self.calls.append(request)
        return LLMResponse(text="[]", model=request.model, provider=self.name)


class _DeadJudge:
    """The deployed failure mode: the local-forced provider has no reachable endpoint,
    so every complete() raises (openai.APIConnectionError in prod; any Exception here)."""

    name = "local"
    calls: list[Any] = []

    def complete(self, request: Any) -> LLMResponse:
        raise ConnectionError("local model endpoint unreachable")


_ORIGIN = (38.5, -78.4)


def _runtime(session: _Session, judge: Any, personalized: Any) -> Runtime:
    return Runtime(
        session=session,  # type: ignore[arg-type]
        probes={},
        judge=(judge, "claude") if judge else None,
        personalized_judge=(personalized, "local-llama") if personalized else None,
    )


# ── The root cause: personalized (local-forced) judge unavailable on the deploy ──


def test_personalized_judge_failure_degrades_to_anonymous_quality_feed() -> None:
    """Regression for the viewer-path 500: the personalized judge raising must yield
    the anonymous-quality feed with the disclosure notice — not an exception."""
    cloud = _SpyJudge("anthropic")
    rt = _runtime(_Session(belief_rows=[_belief_row()]), cloud, _DeadJudge())

    feed = plan("mellow views", _ORIGIN, rt, viewer_id="mem:josh")

    assert len(feed.cards) == 3, "the feed must survive the personalized-judge failure"
    assert PERSONAL_CONTEXT_UNAVAILABLE_NOTICE in feed.notices
    assert cloud.calls, "fallback ranks with the plain judge (anonymous quality)"


def test_fallback_rank_strips_the_overlay_from_the_cloud_judge() -> None:
    """Rule #5: the degrade path may use the cloud judge, but only with the overlay
    STRIPPED — the assembled personal context never rides the fallback profile."""
    cloud = _SpyJudge("anthropic")
    rt = _runtime(_Session(belief_rows=[_belief_row()]), cloud, _DeadJudge())

    plan("mellow views", _ORIGIN, rt, viewer_id="mem:josh")

    assert cloud.calls
    for call in cloud.calls:
        assert "PERSONAL CONTEXT" not in call.messages[0]["content"]


def test_personalized_failure_without_plain_judge_returns_unranked_feed() -> None:
    """No plain judge to fall back to → the guardrail-passing order ships as-is,
    still disclosed, still not a 500."""
    rt = _runtime(_Session(belief_rows=[_belief_row()]), None, _DeadJudge())

    feed = plan("mellow views", _ORIGIN, rt, viewer_id="mem:josh")

    assert len(feed.cards) == 3
    assert PERSONAL_CONTEXT_UNAVAILABLE_NOTICE in feed.notices


# ── The whole class: any context-assembly failure degrades-and-discloses ──


def test_context_assembly_failure_degrades_disclosed() -> None:
    """A viewer whose overlay queries fail (e.g. a corpus prune left the personal
    overlay referencing vanished world nodes and the graph read errors) still gets a
    feed: empty context, disclosed notice, ranking proceeds."""
    local = _SpyJudge("local")
    rt = _runtime(_Session(fail_overlay=True), _SpyJudge("anthropic"), local)

    feed = plan("mellow views", _ORIGIN, rt, viewer_id="mem:josh")

    assert len(feed.cards) == 3
    assert PERSONAL_CONTEXT_UNAVAILABLE_NOTICE in feed.notices
    assert local.calls, "ranking still runs (personalized judge, empty context)"
    assert "PERSONAL CONTEXT" not in local.calls[0].messages[0]["content"]


def test_episode_referencing_vanished_trail_still_plans() -> None:
    """A seeded viewer whose Episode survived a corpus prune that removed its trail:
    the row carries no trail name/date. Assembly tolerates it; /plan succeeds."""
    episode_rows = [{"trail_name": None, "date": None, "overall": "good"}]
    local = _SpyJudge("local")
    rt = _runtime(_Session(episode_rows=episode_rows), _SpyJudge("anthropic"), local)

    feed = plan("mellow views", _ORIGIN, rt, viewer_id="mem:josh")

    assert len(feed.cards) == 3
    assert local.calls, "personalized ranking runs on the intact context"


# ── Anonymous path unchanged ──


def test_anonymous_judge_failure_still_raises() -> None:
    """A plain-judge failure on the anonymous path is NOT a personal-context failure
    and keeps its existing behavior (surfaces as an error, retried/reported upstream)."""
    rt = _runtime(_Session(), _DeadJudge(), _SpyJudge("local"))

    with pytest.raises(ConnectionError):
        plan("mellow views", _ORIGIN, rt, viewer_id="anonymous")


def test_anonymous_feed_has_no_degrade_notice() -> None:
    cloud = _SpyJudge("anthropic")
    rt = _runtime(_Session(), cloud, _SpyJudge("local"))

    feed = plan("mellow views", _ORIGIN, rt, viewer_id="anonymous")

    assert len(feed.cards) == 3
    assert PERSONAL_CONTEXT_UNAVAILABLE_NOTICE not in feed.notices
    assert cloud.calls
