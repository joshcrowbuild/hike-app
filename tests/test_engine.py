"""Engine composition test — Scout -> Verifier -> guardrail filter.

Fake session + fake adapters; no DB, no network. Asserts the verified-vs-unverifiable
split (revised 2026-07-02): a verified hazard stays a card wearing a prominent
warning; an unverifiable required condition ALSO stays a card, carrying a disclosed
"conditions unavailable" note (rule #6: an outage must never blank the feed); only a
verified hard threshold (hazardous AQI) is set aside.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from orchestration.adapters.base import (
    AdapterHealth,
    ConditionKind,
    LiveAdapter,
    LiveCapabilities,
    Point,
    VerifiedFact,
)
from orchestration.confidence import compute, for_fact
from orchestration.curator import GuardrailVerdict
from orchestration.engine import (
    CachedPlan,
    PlannedTrail,
    Runtime,
    _anon_key,
    _compute_plan,
    _render_feed,
    plan,
    plan_from_origin,
    rank_plan,
)
from orchestration.feed_cache import FeedCache
from orchestration.providers.base import LLMResponse
from orchestration.scout import Candidate


class _FakeSession:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def run(self, query: tuple[str, dict[str, Any]]) -> list[dict[str, Any]]:
        cypher, _ = query
        # Context assembly queries (Belief, PhysicalProfile, Episode) return []
        # so they don't leak trail rows into the personal-context path.
        if any(k in cypher for k in ("Belief", "PhysicalProfile", "Episode")):
            return []
        return self.rows


class _FakeAdapter(LiveAdapter):
    """A point-probe adapter driven by a (lat, lon) -> value function."""

    def __init__(self, name: str, kind: ConditionKind, fn: Callable[[float, float], Any]) -> None:
        self.name = name
        self.kind = kind
        self._fn = fn

    def capabilities(self) -> LiveCapabilities:
        return LiveCapabilities(True, False, True)

    def probe(self, point: Point, when: datetime | None = None) -> VerifiedFact | None:
        value = self._fn(point.lat, point.lon)
        return None if value is None else _fact(value)

    def health(self) -> AdapterHealth:
        return AdapterHealth.OK

    @classmethod
    def from_config(cls, settings: Any) -> "LiveAdapter | None":
        return None


def _weather_probes(fn: Callable[[float, float], Any]) -> dict[ConditionKind, list[LiveAdapter]]:
    return {ConditionKind.weather: [_FakeAdapter("w", ConditionKind.weather, fn)]}


def _air_probes(fn: Callable[[float, float], Any]) -> dict[ConditionKind, list[LiveAdapter]]:
    return {ConditionKind.air: [_FakeAdapter("a", ConditionKind.air, fn)]}


class _SourcedAdapter(LiveAdapter):
    """Like `_FakeAdapter`, but the fact carries a REAL, multi-word source label
    (e.g. "EPA AirNow") instead of the generic "t" — needed to exercise the D3
    short-provider consistency pass on a set-aside reason (`_set_aside`)."""

    def __init__(self, kind: ConditionKind, source: str, fn: Callable[[float, float], Any]) -> None:
        self.name = "sourced"
        self.kind = kind
        self._source = source
        self._fn = fn

    def capabilities(self) -> LiveCapabilities:
        return LiveCapabilities(True, False, True)

    def probe(self, point: Point, when: datetime | None = None) -> VerifiedFact | None:
        value = self._fn(point.lat, point.lon)
        return (
            None
            if value is None
            else VerifiedFact(
                value=value, source=self._source, fetched_at=datetime.now(timezone.utc)
            )
        )

    def health(self) -> AdapterHealth:
        return AdapterHealth.OK

    @classmethod
    def from_config(cls, settings: Any) -> "LiveAdapter | None":
        return None


def _fact(value: Any) -> VerifiedFact:
    return VerifiedFact(value=value, source="t", fetched_at=datetime.now(timezone.utc))


def _row(cid: str, lat: float, lon: float, dist: float) -> dict[str, Any]:
    return {
        "canonical_id": cid,
        "name": cid,
        "trailhead_id": "th",
        "distance_m": dist,
        "point": {"latitude": lat, "longitude": lon},
    }


def test_verified_hazard_stays_a_card_wearing_a_warning() -> None:
    # Decision of 2026-07-01: a VERIFIED active alert shows the trail with a
    # prominent source-stamped warning — it never hides it (rule #2: a safety flag
    # is presentation, never a ranking/eligibility penalty).
    rows = [_row("clear", 38.5, -78.4, 100), _row("alerted", 39.0, -79.0, 200)]

    def weather(lat: float, lon: float) -> Any:
        return {"active_alerts": ["Extreme Heat Warning"] if lat == 39.0 else []}

    batch = plan_from_origin(
        38.5,
        -78.4,
        _FakeSession(rows),  # type: ignore[arg-type]
        _weather_probes(weather),
        k=10,
    )
    assert [p.candidate.canonical_id for p in batch.trails] == ["clear", "alerted"]
    assert batch.set_aside == ()  # a verified hazard is never set aside
    alerted = batch.trails[1]
    (warning,) = alerted.verdict.warnings
    assert "Extreme Heat Warning" in warning.text
    assert warning.source == "t"  # source-stamped from the alerting fact …
    assert warning.observed_at == alerted.facts[ConditionKind.weather].fetched_at  # … + aged
    assert batch.trails[0].verdict.warnings == ()  # the clear trail wears nothing


def test_failed_weather_probe_stays_a_card_with_disclosure() -> None:
    # The P0 regression (rule #6): weather was probed and no source answered → the
    # alert state is unverifiable, but an outage must never blank the feed. The
    # trail STAYS a card carrying a disclosed "conditions unavailable" note — it
    # must never ride the feed looking checked-clear (rule #1), nor be hidden.
    rows = [_row("verified", 38.5, -78.4, 100), _row("probe-failed", 39.0, -79.0, 200)]

    def weather(lat: float, lon: float) -> Any:
        return None if lat == 39.0 else {"active_alerts": []}

    batch = plan_from_origin(
        38.5,
        -78.4,
        _FakeSession(rows),  # type: ignore[arg-type]
        _weather_probes(weather),
        k=10,
    )
    assert {p.candidate.canonical_id for p in batch.trails} == {"verified", "probe-failed"}
    assert batch.set_aside == ()  # unverifiable is disclosed, never set aside
    failed = next(p for p in batch.trails if p.candidate.canonical_id == "probe-failed")
    (note,) = failed.verdict.unavailable
    assert "couldn't be verified" in note.reason
    assert note.kind == "weather"
    verified = next(p for p in batch.trails if p.candidate.canonical_id == "verified")
    assert verified.verdict.unavailable == ()


def test_unavailable_condition_surfaces_through_plan_without_penalizing_rank() -> None:
    # rule #6: an unverifiable condition never demotes or hides a trail — it stays a
    # ranked card carrying its disclosure. The class here is the unverifiable one
    # (failed alerts sub-call → active_alerts=None).
    rows = [
        _row("safe-a", 38.5, -78.4, 100),
        _row("unverifiable", 39.0, -79.0, 150),
        _row("safe-b", 38.6, -78.3, 200),
    ]

    def weather(lat: float, lon: float) -> Any:
        return {"active_alerts": None if lat == 39.0 else []}

    runtime = Runtime(session=_FakeSession(rows), probes=_weather_probes(weather))  # type: ignore[arg-type]
    feed = plan("trails near me", (38.5, -78.4), runtime, k=10)
    card_ids = {c.canonical_id for c in feed.cards}
    assert card_ids == {"safe-a", "safe-b", "unverifiable"}  # nothing silently vanishes
    assert feed.set_aside == ()
    unverifiable_card = next(c for c in feed.cards if c.canonical_id == "unverifiable")
    (note,) = unverifiable_card.unavailable
    assert "couldn't be verified" in note.text
    assert note.kind == "weather"


def test_total_weather_outage_never_blanks_the_feed() -> None:
    # The exact P0 regression: every weather probe fails (no source responds for
    # any candidate) — the full set of trails must still ride the feed as cards,
    # each disclosing "conditions unavailable", with set_aside empty (rule #6).
    rows = [
        _row("a", 38.5, -78.4, 100),
        _row("b", 39.0, -79.0, 150),
        _row("c", 38.6, -78.3, 200),
    ]

    def weather(lat: float, lon: float) -> Any:
        return None  # every probe fails

    runtime = Runtime(session=_FakeSession(rows), probes=_weather_probes(weather))  # type: ignore[arg-type]
    feed = plan("trails near me", (38.5, -78.4), runtime, k=10)
    assert {c.canonical_id for c in feed.cards} == {"a", "b", "c"}
    assert feed.set_aside == ()
    for card in feed.cards:
        (note,) = card.unavailable
        assert "couldn't be verified" in note.text
        assert note.kind == "weather"


def test_verified_hazardous_aqi_still_sets_the_trail_aside() -> None:
    # Set-aside is now reserved for genuine VERIFIED hard-blocks (rule #6 only
    # changed the unverifiable-condition policy). Hazardous AQI is a real, verified
    # threshold — it must keep blocking exactly as before.
    rows = [_row("clean-air", 38.5, -78.4, 100), _row("hazardous-air", 39.0, -79.0, 200)]

    def aqi(lat: float, lon: float) -> Any:
        return {"aqi": 250} if lat == 39.0 else {"aqi": 40}

    batch = plan_from_origin(
        38.5,
        -78.4,
        _FakeSession(rows),  # type: ignore[arg-type]
        _air_probes(aqi),
        k=10,
    )
    assert [p.candidate.canonical_id for p in batch.trails] == ["clean-air"]
    assert [s.canonical_id for s in batch.set_aside] == ["hazardous-air"]
    reason = batch.set_aside[0].reasons[0]
    assert "hazardous" in reason.text
    assert reason.kind == "air"


def test_set_aside_reason_wears_the_short_provider_not_the_raw_source() -> None:
    # D3 consistency pass: a set-aside reason's parenthetical is the SHORT provider
    # name ("EPA"), never the raw domain-suffixed source ("EPA AirNow") — matching
    # how a card warning and a condition line already present. `reason.source`
    # keeps the full label, unshortened, for a future inspectable detail surface.
    rows = [_row("hazardous-air", 39.0, -79.0, 200)]

    def aqi(lat: float, lon: float) -> Any:
        return {"aqi": 250}

    batch = plan_from_origin(
        38.5,
        -78.4,
        _FakeSession(rows),  # type: ignore[arg-type]
        {ConditionKind.air: [_SourcedAdapter(ConditionKind.air, "EPA AirNow", aqi)]},
        k=10,
    )
    reason = batch.set_aside[0].reasons[0]
    assert reason.text == "air quality hazardous (AQI 250) (EPA)"
    assert reason.source == "EPA AirNow"


def test_verified_hazard_warning_rides_the_feed_card() -> None:
    # The end-to-end plan(): a verified alert reaches the FeedCard's warnings[] with
    # text + source + observed-at (mirroring how lines[] carries source/confidence).
    rows = [_row("alerted", 38.5, -78.4, 100)]

    def weather(lat: float, lon: float) -> Any:
        return {"active_alerts": ["Extreme Heat Warning"]}

    runtime = Runtime(session=_FakeSession(rows), probes=_weather_probes(weather))  # type: ignore[arg-type]
    feed = plan("trails near me", (38.5, -78.4), runtime, k=10)
    assert [c.canonical_id for c in feed.cards] == ["alerted"]
    (warning,) = feed.cards[0].warnings
    assert "Extreme Heat Warning" in warning.text
    assert warning.source == "t"
    assert warning.observed_at is not None
    assert feed.set_aside == ()


class _FixedTimeAdapter(LiveAdapter):
    """Like `_FakeAdapter`, but stamps a fixed `fetched_at` instead of
    `datetime.now()` — so two independent `plan_from_origin` calls made moments
    apart in the same test produce byte-for-byte identical `VerifiedFact`s, and a
    real equality check isn't hiding behind two different wall-clock timestamps."""

    def __init__(self, name: str, kind: ConditionKind, fn: Callable[[float, float], Any]) -> None:
        self.name = name
        self.kind = kind
        self._fn = fn

    def capabilities(self) -> LiveCapabilities:
        return LiveCapabilities(True, False, True)

    def probe(self, point: Point, when: datetime | None = None) -> VerifiedFact | None:
        value = self._fn(point.lat, point.lon)
        if value is None:
            return None
        return VerifiedFact(value=value, source="t", fetched_at=_FIXED_NOW)

    def health(self) -> AdapterHealth:
        return AdapterHealth.OK

    @classmethod
    def from_config(cls, settings: Any) -> "LiveAdapter | None":
        return None


_FIXED_NOW = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)


def test_plan_from_origin_is_identical_regardless_of_fan_out_concurrency() -> None:
    """The live-probe fan-out (Verifier) now runs every candidate's probes
    concurrently via `verify_batch` instead of walking candidates one at a time —
    a latency change only (Epic 018 S6 follow-up). This pins that invariant end to
    end: cards, set-aside, warnings, and unavailable-condition disclosures must be
    byte-for-byte identical whether the fan-out is forced fully serial
    (`probe_max_workers=1`) or run at a realistic concurrency, across one batch
    mixing a clear trail, a verified hazard warning, an unverifiable condition, and a
    verified hard set-aside — the same trails, same conditions, same set-aside/
    warning behavior the sequential loop produced."""
    rows = [
        _row("clear", 38.5, -78.4, 100),
        _row("hazard-warning", 39.0, -79.0, 150),  # verified alert -> stays, warns
        _row("unverifiable", 39.5, -79.5, 200),  # failed probe -> stays, discloses
        _row("hazardous-aqi", 40.0, -80.0, 250),  # verified hard block -> set aside
    ]

    def weather(lat: float, lon: float) -> Any:
        if lat == 39.0:
            return {"active_alerts": ["Red Flag Warning"]}
        if lat == 39.5:
            return None  # the P0 case: probed, no source answered
        return {"active_alerts": []}

    def aqi(lat: float, lon: float) -> Any:
        return {"aqi": 300} if lat == 40.0 else {"aqi": 20}

    probes: dict[ConditionKind, list[LiveAdapter]] = {
        ConditionKind.weather: [_FixedTimeAdapter("w", ConditionKind.weather, weather)],
        ConditionKind.air: [_FixedTimeAdapter("a", ConditionKind.air, aqi)],
    }

    serial = plan_from_origin(
        38.5,
        -78.4,
        _FakeSession(rows),
        probes,
        k=10,
        probe_max_workers=1,  # type: ignore[arg-type]
    )
    concurrent = plan_from_origin(
        38.5,
        -78.4,
        _FakeSession(rows),
        probes,
        k=10,
        probe_max_workers=8,  # type: ignore[arg-type]
    )

    assert serial == concurrent
    assert [p.candidate.canonical_id for p in concurrent.trails] == [
        "clear",
        "hazard-warning",
        "unverifiable",
    ]
    assert [s.canonical_id for s in concurrent.set_aside] == ["hazardous-aqi"]
    (warning,) = next(
        p for p in concurrent.trails if p.candidate.canonical_id == "hazard-warning"
    ).verdict.warnings
    assert "Red Flag" in warning.text
    (note,) = next(
        p for p in concurrent.trails if p.candidate.canonical_id == "unverifiable"
    ).verdict.unavailable
    assert note.kind == "weather"


class _FakeJudge:
    name = "fake"

    def __init__(self, text: str) -> None:
        self.text = text

    def complete(self, request: Any) -> LLMResponse:
        return LLMResponse(text=self.text, model=request.model, provider=self.name)


def _planned(cid: str, dist: float) -> PlannedTrail:
    return PlannedTrail(Candidate(cid, cid.upper(), "th", dist), {}, {}, GuardrailVerdict(False))


def test_rank_plan_reorders_by_taste() -> None:
    plan_list = [_planned("a", 10.0), _planned("b", 20.0)]  # distance order: a, b
    out = rank_plan(plan_list, _FakeJudge('["b","a"]'), "m")  # judge prefers b
    assert [p.candidate.canonical_id for p in out] == ["b", "a"]


# ── Intent.filters as soft rank signals (Sonnet lane) ──


def _planned_len(cid: str, length_mi: float | None) -> PlannedTrail:
    candidate = Candidate(cid, cid.upper(), "th", 10.0, length_mi=length_mi)
    return PlannedTrail(candidate, {}, {}, GuardrailVerdict(False))


def test_rank_plan_demotes_over_length_candidates() -> None:
    short = _planned_len("short", 3.0)
    long = _planned_len("long", 12.0)
    out = rank_plan(
        [long, short],
        _FakeJudge('["long","short"]'),  # judge prefers the long one
        "m",
        filters={"max_length_mi": 8},
    )
    # Demotion sinks the over-budget trail below the rest — never dropped.
    assert [p.candidate.canonical_id for p in out] == ["short", "long"]


def test_rank_plan_over_length_never_drops_the_trail() -> None:
    long = _planned_len("long", 12.0)
    out = rank_plan([long], _FakeJudge('["long"]'), "m", filters={"max_length_mi": 8})
    assert [p.candidate.canonical_id for p in out] == ["long"]


def test_rank_plan_no_length_filter_is_a_no_op() -> None:
    plan_list = [_planned_len("a", 12.0), _planned_len("b", 3.0)]
    out = rank_plan(plan_list, _FakeJudge('["a","b"]'), "m", filters=None)
    assert [p.candidate.canonical_id for p in out] == ["a", "b"]


def test_rank_plan_unknown_length_never_demoted() -> None:
    unknown = _planned_len("unknown", None)
    known_short = _planned_len("short", 3.0)
    out = rank_plan(
        [unknown, known_short],
        _FakeJudge('["unknown","short"]'),
        "m",
        filters={"max_length_mi": 8},
    )
    assert [p.candidate.canonical_id for p in out] == ["unknown", "short"]


class _RecordingJudge:
    name = "fake"

    def __init__(self, text: str) -> None:
        self.text = text
        self.last_user_message: str | None = None

    def complete(self, request: Any) -> LLMResponse:
        self.last_user_message = request.messages[-1]["content"]
        return LLMResponse(text=self.text, model=request.model, provider=self.name)


def test_rank_plan_dog_and_difficulty_reach_judge_as_a_hint_not_a_demotion() -> None:
    plan_list = [_planned("a", 10.0), _planned("b", 20.0)]
    judge = _RecordingJudge('["a","b"]')
    out = rank_plan(plan_list, judge, "m", filters={"dog": True, "difficulty": "easy"})
    # Neither trail is dropped or demoted — it's a hint, not a filter.
    assert {p.candidate.canonical_id for p in out} == {"a", "b"}
    assert judge.last_user_message is not None
    assert "dog-friendly" in judge.last_user_message
    assert "preferred difficulty: easy" in judge.last_user_message


def test_rank_plan_malformed_filters_no_op() -> None:
    plan_list = [_planned("a", 10.0), _planned("b", 20.0)]
    out = rank_plan(
        plan_list,
        _FakeJudge('["b","a"]'),
        "m",
        filters={"max_length_mi": "not a number", "dog": "yes", "difficulty": 42},
    )
    assert [p.candidate.canonical_id for p in out] == ["b", "a"]


def test_plan_builds_feed_with_cards() -> None:
    rows = [_row("safe", 38.5, -78.4, 1609.344)]  # 1 mile out

    def weather(lat: float, lon: float) -> Any:
        return {"short_forecast": "Clear", "temperature": 60, "temperature_unit": "F"}

    runtime = Runtime(session=_FakeSession(rows), probes=_weather_probes(weather))  # type: ignore[arg-type]
    feed = plan("trails near me", (38.5, -78.4), runtime, k=5)
    assert feed.query == "trails near me"
    assert len(feed.cards) == 1
    card = feed.cards[0]
    assert card.canonical_id == "safe"
    assert card.distance_mi == 1.0
    assert any(line.kind == "weather" for line in card.lines)


# ── Drive-time integration (Epic 005 S4/S5) ──


class _CountingWeather(LiveAdapter):
    name = "w"
    kind = ConditionKind.weather

    def __init__(self) -> None:
        self.calls = 0

    def capabilities(self) -> LiveCapabilities:
        return LiveCapabilities(True, False, True)

    def probe(self, point: Point, when: datetime | None = None) -> VerifiedFact | None:
        self.calls += 1
        return _fact({"short_forecast": "Sunny"})

    def health(self) -> AdapterHealth:
        return AdapterHealth.OK

    @classmethod
    def from_config(cls, settings: Any) -> "LiveAdapter | None":
        return None


class _PruneComputer:
    """No isochrone → matrix-only; the second target is over budget."""

    def isochrone(self, origin: Any, time_budget_s: float) -> Any:
        return None

    def matrix(self, origin: Any, targets: list[Any]) -> list[VerifiedFact | None]:
        secs = [600, 1800]
        return [_fact({"drive_seconds": secs[i]}) for i in range(len(targets))]

    def health(self) -> Any:
        return None


def test_s4_ac4_pruned_candidate_incurs_no_probe() -> None:
    rows = [_row("near", 38.6, -78.5, 100), _row("far", 38.9, -79.0, 200)]
    weather = _CountingWeather()
    batch = plan_from_origin(
        38.5,
        -78.4,
        _FakeSession(rows),  # type: ignore[arg-type]
        {ConditionKind.weather: [weather]},
        k=10,
        drive_time=_PruneComputer(),  # type: ignore[arg-type]
        budget_s=1000.0,
    )
    kept = [p.candidate.canonical_id for p in batch.trails]
    assert kept == ["near"]  # far pruned by drive budget (1800 > 1000)
    assert weather.calls == 1  # the pruned candidate never reached the Verifier (AC-4.4)
    # The survivor carries a sourced drive-time fact, folded into facts.
    assert ConditionKind.drive_time in batch.trails[0].facts


class _TrailheadAwareComputer:
    """Reports "near" for the known trailhead coordinate and "far" for everything
    else, so a test can prove which coordinate the prefilter actually routed from."""

    def isochrone(self, origin: Any, time_budget_s: float) -> Any:
        return None  # force the matrix-only path

    def matrix(self, origin: Any, targets: list[Any]) -> list[VerifiedFact | None]:
        out = []
        for lat, lon in targets:
            near_trailhead = abs(lat - 38.6) < 0.01 and abs(lon - (-78.5)) < 0.01
            out.append(_fact({"drive_seconds": 600 if near_trailhead else 5000}))
        return out

    def health(self) -> Any:
        return None


def test_h3_drive_prefilter_routes_from_trailhead_not_trail_centroid() -> None:
    # Regression: a trail's own point (centroid) can sit far from its actual access
    # point. The prefilter must measure from the trailhead, not the centroid, or a
    # perfectly reachable trail gets wrongly pruned.
    row = {
        "canonical_id": "reachable",
        "name": "reachable",
        "trailhead_id": "th",
        "distance_m": 100,
        "point": {"latitude": 40.0, "longitude": -80.0},  # centroid: far, would be pruned
        "trailhead_point": {"latitude": 38.6, "longitude": -78.5},  # trailhead: near
    }
    batch = plan_from_origin(
        38.5,
        -78.4,
        _FakeSession([row]),  # type: ignore[arg-type]
        {},
        k=10,
        drive_time=_TrailheadAwareComputer(),  # type: ignore[arg-type]
        budget_s=1000.0,
    )
    kept = [p.candidate.canonical_id for p in batch.trails]
    assert kept == ["reachable"]  # survives because the trailhead, not the centroid, is near


def _planned_drive(cid: str, drive_secs: float) -> PlannedTrail:
    fact = _fact({"drive_seconds": drive_secs})
    return PlannedTrail(
        Candidate(cid, cid.upper(), "th", 0.0),
        {ConditionKind.drive_time: fact},
        {},
        GuardrailVerdict(False),
    )


def test_s5_ac1_closer_by_road_wins_when_judge_indifferent() -> None:
    far = _planned_drive("far", 3000.0)  # 50 min
    near = _planned_drive("near", 1200.0)  # 20 min
    out = rank_plan([far, near], _FakeJudge("[]"), "m")  # judge indifferent → drive pre-order holds
    assert [p.candidate.canonical_id for p in out] == ["near", "far"]


def test_s5_ac3_absent_drive_time_applies_no_penalty() -> None:
    # One candidate has a time, one does not → no deterministic pre-sort, judge order holds.
    timed = _planned_drive("timed", 3000.0)
    untimed = _planned("untimed", 0.0)  # no drive fact
    out = rank_plan([timed, untimed], _FakeJudge('["timed","untimed"]'), "m")
    assert [p.candidate.canonical_id for p in out] == ["timed", "untimed"]


# ── CDP-01 corroboration wiring ──


class _CorrSession:
    """Fake session that answers the SAME_AS corroboration read with real counts and
    returns the scout rows for everything else (other context reads → [])."""

    def __init__(self, rows: list[dict[str, Any]], corr: dict[str, dict[str, Any]]) -> None:
        self.rows = rows
        self.corr = corr

    def run(self, query: tuple[str, dict[str, Any]]) -> list[dict[str, Any]]:
        cypher, params = query
        if "SAME_AS" in cypher:  # the trail_source_corroboration read
            return [
                {"canonical_id": cid, **self.corr[cid]}
                for cid in params["cids"]
                if cid in self.corr
            ]
        if any(k in cypher for k in ("Belief", "PhysicalProfile", "Episode")):
            return []
        return self.rows


def test_corpus_corroboration_counts_distinct_origins_live_facts_stay_one() -> None:
    rows = [_row("multi", 38.5, -78.4, 100)]

    def weather(lat: float, lon: float) -> Any:
        return {"short_forecast": "Clear"}

    session = _CorrSession(rows, {"multi": {"sources": ["OSM", "NPS"], "corroboration": 2}})
    batch = plan_from_origin(38.5, -78.4, session, _weather_probes(weather), k=10)  # type: ignore[arg-type]
    trail = batch.trails[0]
    # corpus identity carries the real distinct-origin count …
    assert trail.corpus_corroboration == 2
    assert trail.corpus_sources == ("OSM", "NPS")
    assert trail.corpus_confidence is not None
    # … the corpus confidence is genuinely lifted by the 2-origin corroboration …
    assert trail.corpus_confidence.score > compute(authority="tier1", freshness="slow").score
    # … while the live weather fact stays an honest single source (count-as-1): its
    # score is the corroboration=1 value, NOT boosted by the trail's 2 corpus origins.
    live = trail.confidences[ConditionKind.weather]
    live_fact = trail.facts[ConditionKind.weather]
    assert live.score == for_fact(live_fact, corroboration=1).score
    assert live.score < for_fact(live_fact, corroboration=2).score


def _clear_weather(lat: float, lon: float) -> Any:
    return {"short_forecast": "Clear"}


def test_corpus_corroboration_floors_at_one_when_row_absent() -> None:
    # Read-miss path: no row returned for the trail → engine's .get(..., 1) default.
    rows = [_row("orphan", 38.5, -78.4, 100)]
    session = _CorrSession(rows, {})  # no SourceRecords for this trail
    batch = plan_from_origin(38.5, -78.4, session, _weather_probes(_clear_weather), k=10)  # type: ignore[arg-type]
    assert batch.trails[0].corpus_corroboration == 1  # honest baseline, never 0


def test_corpus_corroboration_floors_real_returned_zero_to_one() -> None:
    # Production orphan path: the DB DOES return a row, with a real corroboration of 0
    # (SourceRecord-less trail). The engine's max(1, 0) floors it to the honest baseline —
    # the branch test_..._row_absent can't reach. Guards against dropping the max() wrapper.
    rows = [_row("orphan", 38.5, -78.4, 100)]
    session = _CorrSession(rows, {"orphan": {"sources": [], "corroboration": 0}})
    batch = plan_from_origin(38.5, -78.4, session, _weather_probes(_clear_weather), k=10)  # type: ignore[arg-type]
    assert batch.trails[0].corpus_corroboration == 1
    assert batch.trails[0].corpus_sources == ()


class _RaisingCorrSession(_FakeSession):
    """Scout rows for everything, but the SAME_AS corroboration read RAISES — to exercise
    the rule-#6 degrade path (enrichment is never a dependency)."""

    def run(self, query: tuple[str, dict[str, Any]]) -> list[dict[str, Any]]:
        cypher, _ = query
        if "SAME_AS" in cypher:
            raise RuntimeError("graph unavailable")
        return super().run(query)


def test_corpus_corroboration_read_failure_degrades_not_blocks() -> None:
    # Rule #6: a corroboration read failure must NOT block the feed — it degrades to the
    # honest count-as-1 baseline and the cards still build.
    rows = [_row("safe", 38.5, -78.4, 100)]
    session = _RaisingCorrSession(rows)
    batch = plan_from_origin(38.5, -78.4, session, _weather_probes(_clear_weather), k=10)  # type: ignore[arg-type]
    assert [p.candidate.canonical_id for p in batch.trails] == ["safe"]
    assert batch.trails[0].corpus_corroboration == 1  # degraded, not crashed


def test_confidence_never_reorders_candidates() -> None:
    """Rule #2 / module boundary: the Curator taste ranking is BLIND to confidence.
    Two trails — one with a high-corroboration corpus confidence, one flagged/low — must
    keep the judge's order, and that order must NOT change when the confidences swap."""
    high = compute(authority="tier1", freshness="slow", corroboration=4)
    low = compute(authority="low", freshness="stale", corroboration=1)

    def mk(cid: str, conf: Any) -> PlannedTrail:
        return PlannedTrail(
            Candidate(cid, cid.upper(), "th", 0.0),
            {},
            {},
            GuardrailVerdict(False),
            corpus_confidence=conf,
        )

    judge = _FakeJudge('["b","a"]')  # judge prefers b regardless of confidence
    a_high = [mk("a", high), mk("b", low)]
    b_high = [mk("a", low), mk("b", high)]
    assert [p.candidate.canonical_id for p in rank_plan(a_high, judge, "m")] == ["b", "a"]
    assert [p.candidate.canonical_id for p in rank_plan(b_high, judge, "m")] == ["b", "a"]


# ── plan()-level intent.filters threading (Sonnet lane) ──


class _FakeMechanical:
    name = "mech"

    def __init__(self, json_text: str) -> None:
        self.json_text = json_text

    def complete(self, request: Any) -> LLMResponse:
        return LLMResponse(text=self.json_text, model=request.model, provider=self.name)


def _row_with_length(cid: str, dist: float, length_mi: float) -> dict[str, Any]:
    row = _row(cid, 38.5, -78.4, dist)
    row["length_mi"] = length_mi
    return row


def test_plan_threads_max_length_mi_filter_from_parsed_intent() -> None:
    # "long" is nearer (would rank first on distance) but exceeds the parsed
    # max_length_mi — it must sink below "short", never disappear from the feed.
    rows = [_row_with_length("long", 100.0, 12.0), _row_with_length("short", 200.0, 3.0)]
    runtime = Runtime(
        session=_FakeSession(rows),  # type: ignore[arg-type]
        probes={},
        mechanical=(_FakeMechanical('{"filters": {"max_length_mi": 8}}'), "m"),  # type: ignore[arg-type]
        judge=(_FakeJudge('["long","short"]'), "m"),  # type: ignore[arg-type]
    )
    feed = plan("a short loop", (38.5, -78.4), runtime, k=5)
    assert [c.canonical_id for c in feed.cards] == ["short", "long"]


def test_plan_threads_max_length_mi_on_personalized_judge_failure_fallback() -> None:
    """The overlay-privacy fallback path (personalized judge raises) must still apply
    intent.filters — the degrade-and-disclose story (Rule #6) shouldn't silently drop
    the length filter along with personal context."""

    class _RaisingJudge:
        name = "local"

        def complete(self, request: Any) -> LLMResponse:
            raise RuntimeError("no local model available")

    rows = [_row_with_length("long", 100.0, 12.0), _row_with_length("short", 200.0, 3.0)]
    runtime = Runtime(
        session=_FakeSession(rows),  # type: ignore[arg-type]
        probes={},
        mechanical=(_FakeMechanical('{"filters": {"max_length_mi": 8}}'), "m"),  # type: ignore[arg-type]
        judge=(_FakeJudge('["long","short"]'), "m"),  # type: ignore[arg-type]
        personalized_judge=(_RaisingJudge(), "m"),  # type: ignore[arg-type]
    )
    # A non-anonymous viewer forces the personalized (local-forced) judge path — it
    # raises here, exercising the fallback that re-ranks with the plain judge.
    feed = plan("a short loop", (38.5, -78.4), runtime, k=5, viewer_id="mem:josh")
    assert [c.canonical_id for c in feed.cards] == ["short", "long"]


# ── Epic 039 S2: engine-layer anonymous plan cache ──


class _CountingMechanical:
    name = "mech"

    def __init__(self, json_text: str) -> None:
        self.json_text = json_text
        self.calls = 0

    def complete(self, request: Any) -> LLMResponse:
        self.calls += 1
        return LLMResponse(text=self.json_text, model=request.model, provider=self.name)


class _CountingJudge:
    def __init__(self, text: str, name: str = "fake") -> None:
        self.text = text
        self.name = name
        self.calls = 0

    def complete(self, request: Any) -> LLMResponse:
        self.calls += 1
        return LLMResponse(text=self.text, model=request.model, provider=self.name)


class _RaisingJudge:
    name = "fake"

    def complete(self, request: Any) -> LLMResponse:
        raise ConnectionError("judge unavailable")


def _cached_runtime(
    *, feed_cache: FeedCache | None, personalized_judge: Any = None
) -> tuple[Runtime, _CountingMechanical, _CountingJudge]:
    rows = [_row("a", 38.5, -78.4, 100.0), _row("b", 38.6, -78.5, 200.0)]
    mech = _CountingMechanical("{}")
    judge = _CountingJudge('["a","b"]')
    runtime = Runtime(
        session=_FakeSession(rows),  # type: ignore[arg-type]
        probes={},
        mechanical=(mech, "m"),  # type: ignore[arg-type]
        judge=(judge, "m"),  # type: ignore[arg-type]
        personalized_judge=personalized_judge,
        feed_cache=feed_cache,
    )
    return runtime, mech, judge


def test_s2_ac1_second_identical_anonymous_call_is_a_cache_hit_compute_once() -> None:
    fc = FeedCache(ttl_s=300.0, clock=lambda: 0.0)
    runtime, mech, judge = _cached_runtime(feed_cache=fc)

    feed1 = plan("mellow loop", (38.5, -78.4), runtime, k=5)
    feed2 = plan("mellow loop", (38.5, -78.4), runtime, k=5)

    assert mech.calls == 1  # the ~0.3s intent parse ran once, not twice
    assert judge.calls == 1  # the taste-rank LLM call ran once, not twice
    assert fc.stats.hits >= 1
    assert [c.canonical_id for c in feed1.cards] == [c.canonical_id for c in feed2.cards]


def test_s2_ac3_non_anonymous_viewer_never_reads_or_writes_feed_cache() -> None:
    fc = FeedCache(ttl_s=300.0, clock=lambda: 0.0)
    personalized = _CountingJudge('["a","b"]', name="local")
    runtime, mech, judge = _cached_runtime(feed_cache=fc, personalized_judge=(personalized, "m"))

    plan("mellow loop", (38.5, -78.4), runtime, k=5)  # anonymous → populates the cache
    hits_after_anon = fc.stats.hits

    # Same query/origin/k, but a real viewer — must bypass the cache entirely (Rule #5).
    plan("mellow loop", (38.5, -78.4), runtime, k=5, viewer_id="mem:josh")

    assert fc.stats.hits == hits_after_anon  # the non-anonymous call never touched it
    assert personalized.calls == 1  # it genuinely recomputed via the personalized judge
    assert mech.calls == 2  # intent parsed again — not served from cache


def test_s2_ac4_ttl_disabled_feed_cache_is_none_and_plan_always_recomputes() -> None:
    # feed_cache=None (the ADVENTURE_ANON_FEED_CACHE_TTL_S=0 wiring in build_runtime)
    # must be a byte-identical no-op: every call recomputes.
    runtime, mech, judge = _cached_runtime(feed_cache=None)

    plan("mellow loop", (38.5, -78.4), runtime, k=5)
    plan("mellow loop", (38.5, -78.4), runtime, k=5)

    assert mech.calls == 2
    assert judge.calls == 2


def test_s2_ac5_failed_compute_is_never_cached_and_next_call_retries() -> None:
    fc = FeedCache(ttl_s=300.0, clock=lambda: 0.0)
    rows = [_row("a", 38.5, -78.4, 100.0)]
    mech = _CountingMechanical("{}")
    runtime = Runtime(
        session=_FakeSession(rows),  # type: ignore[arg-type]
        probes={},
        mechanical=(mech, "m"),  # type: ignore[arg-type]
        judge=(_RaisingJudge(), "m"),  # type: ignore[arg-type]
        feed_cache=fc,
    )

    for _ in range(2):  # every call must re-raise — nothing was ever stored
        try:
            plan("mellow loop", (38.5, -78.4), runtime, k=5)
            raise AssertionError("expected ConnectionError to propagate")
        except ConnectionError:
            pass

    assert mech.calls == 2  # both calls actually recomputed (no cached failure served)
    assert fc.stats.hits == 0


def test_s2_ac7_cache_hit_feed_matches_fresh_feed_in_structure() -> None:
    fc = FeedCache(ttl_s=300.0, clock=lambda: 0.0)
    runtime, _mech, _judge = _cached_runtime(feed_cache=fc)

    def shape(feed: Any) -> list[tuple]:
        return [(c.canonical_id, c.name, c.distance_mi, len(c.lines)) for c in feed.cards]

    feed1 = plan("mellow loop", (38.5, -78.4), runtime, k=5)  # miss → computes + caches
    feed2 = plan("mellow loop", (38.5, -78.4), runtime, k=5)  # hit → re-rendered from cache

    assert shape(feed1) == shape(feed2)
    assert feed1.notices == feed2.notices
    assert feed1.set_aside == feed2.set_aside


def test_s2_ac2_render_feed_reflects_serve_time_not_capture_time() -> None:
    """The cached path re-renders freshness per serve: a fact captured at t0 and served
    at t0+42m must show "42m ago", never the frozen capture-time age."""
    captured_at = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)
    fact = VerifiedFact(
        value={"short_forecast": "Clear"}, source="NWS test", fetched_at=captured_at
    )
    planned = (
        PlannedTrail(
            Candidate("a", "A", "th", 0.0),
            {ConditionKind.weather: fact},
            {ConditionKind.weather: for_fact(fact)},
            GuardrailVerdict(False),
        ),
    )
    cached = CachedPlan(planned=planned, notices=(), set_aside=())

    serve_time = captured_at + timedelta(minutes=42)
    feed = _render_feed("q", cached, now=serve_time)

    line = feed.cards[0].lines[0]
    assert "42m ago" in line.text


def test_s2_anon_key_rounds_to_3_decimals_matching_probe_cache() -> None:
    # Matches TTLCache._key's own point rounding (registry.py) — same spatial cell.
    assert _anon_key("q", (38.53211, -78.41199), 10) == ("q", 38.532, -78.412, 10)


def test_s2_anon_key_distinguishes_k() -> None:
    assert _anon_key("q", (38.5, -78.4), 5) != _anon_key("q", (38.5, -78.4), 10)


def test_s2_compute_plan_returns_cached_plan_not_feed() -> None:
    runtime, _mech, _judge = _cached_runtime(feed_cache=None)
    cached = _compute_plan("mellow loop", (38.5, -78.4), runtime, k=5)
    assert isinstance(cached, CachedPlan)
    assert [p.candidate.canonical_id for p in cached.planned] == ["a", "b"]


def test_s2_ac1_extends_max_length_mi_test_second_call_is_cache_hit_order_preserved() -> None:
    """Extends test_plan_threads_max_length_mi_filter_from_parsed_intent: a second
    identical anonymous call is served from the feed cache with the ranked order
    (post length-demotion) preserved, and the mechanical/judge tier ran only once."""
    rows = [_row_with_length("long", 100.0, 12.0), _row_with_length("short", 200.0, 3.0)]
    mech = _CountingMechanical('{"filters": {"max_length_mi": 8}}')
    judge = _CountingJudge('["long","short"]')
    fc = FeedCache(ttl_s=300.0, clock=lambda: 0.0)
    runtime = Runtime(
        session=_FakeSession(rows),  # type: ignore[arg-type]
        probes={},
        mechanical=(mech, "m"),  # type: ignore[arg-type]
        judge=(judge, "m"),  # type: ignore[arg-type]
        feed_cache=fc,
    )
    feed1 = plan("a short loop", (38.5, -78.4), runtime, k=5)
    feed2 = plan("a short loop", (38.5, -78.4), runtime, k=5)

    assert [c.canonical_id for c in feed1.cards] == ["short", "long"]
    assert [c.canonical_id for c in feed2.cards] == ["short", "long"]
    assert mech.calls == 1
    assert judge.calls == 1
    assert fc.stats.hits >= 1


def test_s2_runtime_feed_cache_hit_flag_is_request_local_disposition() -> None:
    # api/app.py reads runtime.feed_cache_hit for AC-2.9 metrics honesty. It must be
    # THIS call's disposition — a shared FeedCacheStats counter delta misattributes a
    # concurrent request's hit to a request that computed and spent tokens
    # (adversarial-review finding, 2026-07-08).
    fc = FeedCache(ttl_s=300.0, clock=lambda: 0.0)
    runtime, _mech, _judge = _cached_runtime(feed_cache=fc)

    plan("mellow loop", (38.5, -78.4), runtime, k=5)
    assert runtime.feed_cache_hit is False  # miss: this call ran the pipeline

    plan("mellow loop", (38.5, -78.4), runtime, k=5)
    assert runtime.feed_cache_hit is True  # hit: this call spent nothing


def test_s2_feed_cache_hit_flag_false_for_non_anonymous_and_disabled_cache() -> None:
    personalized = _CountingJudge('["a","b"]', name="local")
    fc = FeedCache(ttl_s=300.0, clock=lambda: 0.0)
    runtime, _mech, _judge = _cached_runtime(feed_cache=fc, personalized_judge=(personalized, "m"))
    plan("mellow loop", (38.5, -78.4), runtime, k=5)  # anonymous → warms the cache
    plan("mellow loop", (38.5, -78.4), runtime, k=5, viewer_id="mem:josh")
    assert runtime.feed_cache_hit is False  # non-anonymous never reads the cache

    runtime2, _mech2, _judge2 = _cached_runtime(feed_cache=None)
    plan("mellow loop", (38.5, -78.4), runtime2, k=5)
    plan("mellow loop", (38.5, -78.4), runtime2, k=5)
    assert runtime2.feed_cache_hit is False  # disabled cache → never reports a hit
