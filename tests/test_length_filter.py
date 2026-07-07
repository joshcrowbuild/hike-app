"""Distance activation: Intent.filters.max_length_mi threaded through plan() into
rank_plan on BOTH call sites (the anonymous/plain-judge path and the personalized-
judge degrade fallback — orchestration/engine.py). The demotion mechanism itself
(is_over_length_demoted) is unit-tested in test_curator.py; rank_plan's use of it is
unit-tested in test_engine.py. This file proves the wiring: a free-text query parsed
into a max_length_mi filter actually reaches whichever rank_plan call runs.

Fakes only; no DB/network (Epic 008 harness).
"""

from __future__ import annotations

from typing import Any

from orchestration.engine import Runtime, plan
from orchestration.providers.base import LLMResponse

_ORIGIN = (38.5, -78.4)


def _row(cid: str, length_mi: float) -> dict[str, Any]:
    return {
        "canonical_id": cid,
        "name": cid,
        "trailhead_id": "th",
        "distance_m": 100.0,
        "point": {"latitude": 38.5, "longitude": -78.4},
        "length_mi": length_mi,
    }


class _Session:
    """World queries return the two trail rows (one short, one over-length);
    personal-overlay queries return empty (no overlay in play)."""

    def run(self, query: tuple[str, dict[str, Any]]) -> list[dict[str, Any]]:
        cypher, _ = query
        if any(k in cypher for k in ("Belief", "PhysicalProfile", "Episode")):
            return []
        # "long" first: absent demotion, judge-indifferent order keeps it first —
        # any reordering to ["short", "long"] must come from the length filter.
        return [_row("long", 12.0), _row("short", 3.0)]


class _FakeProvider:
    """A `ModelProvider` stub that always answers a fixed text (mechanical parse or
    judge ranking, depending on which slot it's wired into)."""

    def __init__(self, name: str, text: str) -> None:
        self.name = name
        self.text = text
        self.calls: list[Any] = []

    def complete(self, request: Any) -> LLMResponse:
        self.calls.append(request)
        return LLMResponse(text=self.text, model=request.model, provider=self.name)


class _RaisingProvider:
    """The deployed local-forced-personalized-judge-unavailable failure mode: every
    complete() raises, forcing plan()'s fallback to the second rank_plan call site."""

    name = "local"

    def complete(self, request: Any) -> LLMResponse:
        raise ConnectionError("local model endpoint unreachable")


_MECHANICAL_8MI = '{"filters": {"max_length_mi": 8}}'
_MECHANICAL_MALFORMED = '{"filters": {"max_length_mi": "eight"}}'


def test_max_length_mi_demotes_via_the_anonymous_plain_judge_path() -> None:
    # use_personal_judge is False for an anonymous viewer with no overlay -> the
    # FIRST rank_plan call site (runtime.judge) is the one that must apply the filter.
    mechanical = _FakeProvider("mech", _MECHANICAL_8MI)
    judge = _FakeProvider("cloud", "[]")  # indifferent -> demotion alone explains reorder
    rt = Runtime(
        session=_Session(),  # type: ignore[arg-type]
        probes={},
        mechanical=(mechanical, "extract-model"),
        judge=(judge, "claude"),
    )

    feed = plan("a hike under 8 miles", _ORIGIN, rt, viewer_id="anonymous")

    assert [c.canonical_id for c in feed.cards] == ["short", "long"]
    assert judge.calls, "the plain judge must be the one that actually ranked"


def test_max_length_mi_demotes_via_the_personalized_fallback_path() -> None:
    # An authenticated viewer whose local-forced personalized judge is unavailable
    # (Epic 014's real failure mode) degrades to the SECOND rank_plan call site
    # (runtime.judge, profile stripped) — the filter must still apply there.
    mechanical = _FakeProvider("mech", _MECHANICAL_8MI)
    fallback_judge = _FakeProvider("cloud", "[]")
    rt = Runtime(
        session=_Session(),  # type: ignore[arg-type]
        probes={},
        mechanical=(mechanical, "extract-model"),
        judge=(fallback_judge, "claude"),
        personalized_judge=(_RaisingProvider(), "local-llama"),
    )

    feed = plan("a hike under 8 miles", _ORIGIN, rt, viewer_id="mem:josh")

    assert [c.canonical_id for c in feed.cards] == ["short", "long"]
    assert fallback_judge.calls, "the fallback judge must be the one that actually ranked"


def test_malformed_max_length_mi_is_a_safe_noop() -> None:
    # The mechanical tier is an LLM parse — a non-numeric value must no-op the
    # filter (valid_max_length_mi) rather than crash plan() or demote everything.
    mechanical = _FakeProvider("mech", _MECHANICAL_MALFORMED)
    judge = _FakeProvider("cloud", "[]")
    rt = Runtime(
        session=_Session(),  # type: ignore[arg-type]
        probes={},
        mechanical=(mechanical, "extract-model"),
        judge=(judge, "claude"),
    )

    feed = plan("a hike under eight miles", _ORIGIN, rt, viewer_id="anonymous")

    # No usable filter -> no demotion -> judge-indifferent input order holds.
    assert [c.canonical_id for c in feed.cards] == ["long", "short"]


def test_no_filter_requested_is_a_safe_noop() -> None:
    # Default Intent (no mechanical tier at all) carries empty filters; a null
    # length_mi on a candidate must never crash the filter either.
    judge = _FakeProvider("cloud", "[]")
    rt = Runtime(session=_Session(), probes={}, judge=(judge, "claude"))  # type: ignore[arg-type]

    feed = plan("trails near me", _ORIGIN, rt, viewer_id="anonymous")

    assert [c.canonical_id for c in feed.cards] == ["long", "short"]
