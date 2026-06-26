"""Epic 003 S5/S6 — context-assembly wiring inside engine.plan().

Asserts the engine contract the context_assembly unit tests can't reach:
  - AC-5.3: personal context is assembled from the POST-guardrail candidate set and
    rides only the taste-rank call — it never changes which trails are surfaced.
  - AC-5.4: context is assembled once per plan() and passed to a SINGLE rank call.
  - AC-6.2: the feed is identical in structure whether or not personal context exists.

Fakes only; no DB/network. The spy judge returns "[]" so _parse_ids keeps every
candidate (input order), giving both the seeded and anonymous runs the same feed.
"""

from __future__ import annotations

from typing import Any

from orchestration.engine import Runtime, plan
from orchestration.providers.base import LLMResponse


def _row(cid: str, lat: float = 38.5, lon: float = -78.4, dist: float = 100.0) -> dict[str, Any]:
    return {
        "canonical_id": cid,
        "name": cid,
        "trailhead_id": "th",
        "distance_m": dist,
        "point": {"latitude": lat, "longitude": lon},
    }


def _belief_row() -> dict[str, Any]:
    """A stated preference that survives the decay/floor filter → non-empty context."""
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
    """Fake ScopedSession: Belief → belief_rows; PhysicalProfile/Episode → [] (recording
    the Episode query's candidate_ids); anything else → the trail rows."""

    def __init__(self, trail_rows: list[dict], belief_rows: list[dict]) -> None:
        self.trail_rows = trail_rows
        self.belief_rows = belief_rows
        self.episode_candidate_ids: list[Any] = []

    def run(self, query: tuple[str, dict[str, Any]]) -> list[dict[str, Any]]:
        cypher, params = query
        if "Belief" in cypher:
            return self.belief_rows
        if "PhysicalProfile" in cypher:
            return []
        if "Episode" in cypher:
            self.episode_candidate_ids.append(params.get("candidate_ids"))
            return []
        return self.trail_rows


class _SpyJudge:
    """Records each complete() call; returns '[]' so _parse_ids keeps all candidates."""

    def __init__(self, name: str = "local") -> None:
        self.name = name
        self.calls: list[Any] = []

    def complete(self, request: Any) -> LLMResponse:
        self.calls.append(request)
        return LLMResponse(text="[]", model=request.model, provider=self.name)


_TRAILS = [_row("a"), _row("b"), _row("c")]
_ORIGIN = (38.5, -78.4)


def _runtime(belief_rows: list[dict]) -> tuple[Runtime, _SpyJudge, _SpyJudge, _Session]:
    cloud = _SpyJudge("anthropic")
    local = _SpyJudge("local")
    session = _Session(list(_TRAILS), belief_rows)
    rt = Runtime(
        session=session,  # type: ignore[arg-type]
        probes={},
        judge=(cloud, "claude"),  # type: ignore[arg-type]
        personalized_judge=(local, "local-llama"),  # type: ignore[arg-type]
    )
    return rt, cloud, local, session


def test_s5_ac4_context_assembled_once_single_rank_call() -> None:
    """AC-5.4: context is assembled once per plan() and passed to a SINGLE rank call — the
    judge's complete() fires exactly once for all candidates, not once per candidate."""
    rt, _cloud, local, _session = _runtime([_belief_row()])
    plan("mellow views", _ORIGIN, rt, viewer_id="mem:josh")
    assert len(local.calls) == 1


def test_s5_ac3_context_uses_post_pipeline_candidates_and_rides_only_the_rank() -> None:
    """AC-5.3: personal context is assembled from the POST-guardrail candidate set (the
    same trails that become the feed) and is injected only into the taste-rank call — never
    into trail selection."""
    rt, _cloud, local, session = _runtime([_belief_row()])
    feed = plan("mellow views", _ORIGIN, rt, viewer_id="mem:josh")
    feed_ids = {c.canonical_id for c in feed.cards}
    assert session.episode_candidate_ids, "context assembly must run for a seeded viewer"
    assert set(session.episode_candidate_ids[0]) == feed_ids  # post-pipeline candidate set
    assert local.calls and "PERSONAL CONTEXT" in local.calls[0].messages[0]["content"]


def test_s6_ac2_feed_structure_identical_with_or_without_context() -> None:
    """AC-6.2: the feed is identical in structure whether or not personal context exists —
    a seeded (overlay) viewer and an anonymous viewer get the same cards in the same shape,
    so personal context never changes which trails are surfaced."""
    rt_ctx, _c1, _l1, _s1 = _runtime([_belief_row()])
    feed_ctx = plan("mellow views", _ORIGIN, rt_ctx, viewer_id="mem:josh")

    rt_anon, _c2, _l2, _s2 = _runtime([])  # no overlay
    feed_anon = plan("mellow views", _ORIGIN, rt_anon, viewer_id="anonymous")

    def shape(feed: Any) -> list[tuple]:
        return [(c.canonical_id, c.name, len(c.lines), len(c.warnings)) for c in feed.cards]

    assert shape(feed_ctx) == shape(feed_anon)
    assert len(feed_ctx.cards) == len(_TRAILS)  # non-trivial: the trails are actually present
