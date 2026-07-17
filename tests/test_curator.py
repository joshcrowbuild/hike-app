"""Curator guardrail tests — the verified-vs-unverifiable split (revised 2026-07-02).

A VERIFIED hazard (an alert with source + timestamp) becomes a prominent card
warning, never a block; an UNVERIFIABLE required condition (failed weather probe
or failed alerts sub-call) STAYS a card carrying a disclosed "conditions
unavailable" note, never a block (rule #6: an outage must never blank the feed);
hard non-weather thresholds (hazardous AQI) keep their block semantics.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from orchestration.adapters.base import ConditionKind, VerifiedFact
from orchestration.curator import (
    apply_corroboration_rescue,
    corroboration_rescue_enabled,
    evaluate_guardrails,
    filter_preference_hints,
    is_corroboration_rescued,
    is_outside_boundary_demoted,
    is_over_length_demoted,
    is_roadlike_demoted,
    rank_ids,
    valid_max_length_mi,
)
from orchestration.providers.base import LLMResponse

_NOW = datetime.now(timezone.utc)


def _fact(value: Any) -> VerifiedFact:
    return VerifiedFact(value=value, source="t", fetched_at=_NOW)


def test_verified_alert_warns_instead_of_blocking() -> None:
    # Decision of 2026-07-01: a verified hazard SHOWS with a warning, never hides —
    # even the alert classes that used to hard-block (extreme / flash flood / tornado).
    v = evaluate_guardrails(
        {ConditionKind.weather: _fact({"active_alerts": ["Extreme Heat Warning"]})}
    )
    assert not v.blocked
    assert not v.blocks
    assert any("Extreme Heat Warning" in w.text for w in v.warnings)


def test_warning_is_source_and_timestamp_stamped() -> None:
    # The card warning mirrors a feed line: cause + the fact's SHORT provider name
    # (D3 consistency pass — never the raw domain-suffixed source) + observed-at.
    fact = VerifiedFact(
        value={"active_alerts": ["Tornado Warning"]},
        source="NWS api.weather.gov",
        fetched_at=_NOW,
    )
    v = evaluate_guardrails({ConditionKind.weather: fact})
    (warning,) = v.warnings
    assert warning.kind == "weather"
    assert warning.source == "NWS"
    assert warning.observed_at == _NOW
    assert "Tornado" in warning.text


def test_advisory_alert_is_a_warning() -> None:
    v = evaluate_guardrails({ConditionKind.weather: _fact({"active_alerts": ["Frost Advisory"]})})
    assert not v.blocked
    assert any("Frost Advisory" in w.text for w in v.warnings)


def test_duplicate_alert_features_collapse_to_one_warning() -> None:
    # NWS returns overlapping issuances of one event as separate features (seen
    # live 2026-07-02: the Extreme Heat Warning twice per point) — one warning each.
    v = evaluate_guardrails(
        {
            ConditionKind.weather: _fact(
                {"active_alerts": ["Extreme Heat Warning", "Extreme Heat Warning"]}
            )
        }
    )
    assert [w.text for w in v.warnings] == ["weather alert: Extreme Heat Warning"]


def test_failed_alerts_subcall_discloses_unavailable_not_blocked() -> None:
    # active_alerts=None means the NWS alerts sub-call failed: the alert state is
    # UNKNOWN, and unknown never reads as "no alerts" (rule #1) — but as of
    # 2026-07-02 unknown STAYS a card with a disclosure, never a block (rule #6: an
    # outage must never blank the feed).
    fact = VerifiedFact(
        value={"short_forecast": "Sunny", "active_alerts": None},
        source="NWS api.weather.gov",
        fetched_at=_NOW,
    )
    v = evaluate_guardrails({ConditionKind.weather: fact})
    assert not v.blocked
    assert not v.blocks
    (note,) = v.unavailable
    assert note.kind == "weather"
    assert "couldn't be verified" in note.reason
    assert note.source == "NWS api.weather.gov"


def test_failed_weather_probe_discloses_unavailable_when_weather_was_probed() -> None:
    # Weather probed, no source answered → unverifiable required condition → the
    # trail stays in the feed carrying a disclosed "conditions unavailable" note.
    v = evaluate_guardrails({}, probed_kinds={ConditionKind.weather})
    assert not v.blocked
    assert not v.blocks
    (note,) = v.unavailable
    assert note.kind == "weather"
    assert "couldn't be verified" in note.reason
    assert note.source == "no source responded"


def test_absent_weather_passes_when_weather_not_probed() -> None:
    # No weather adapter configured in this deployment → no signal either way.
    v = evaluate_guardrails({})
    assert not v.blocked
    assert not v.warnings
    assert not v.unavailable


def test_hazardous_aqi_blocks_elevated_warns() -> None:
    assert evaluate_guardrails({ConditionKind.air: _fact({"aqi": 250})}).blocked
    elevated = evaluate_guardrails({ConditionKind.air: _fact({"aqi": 120})})
    assert not elevated.blocked
    assert elevated.warnings
    assert elevated.warnings[0].source == "t"


def test_fire_hotspots_warn_not_block() -> None:
    v = evaluate_guardrails({ConditionKind.fire: _fact({"hotspot_count": 3})})
    assert not v.blocked
    assert any("3 active-fire" in w.text for w in v.warnings)


def _closure_fact(alerts: list[Any], *, park: str | None = "Shenandoah National Park") -> Any:
    value: dict[str, Any] = {"alerts": alerts, "count": len(alerts)}
    if park is not None:
        value["park"] = park
        value["park_code"] = "shen"
    return VerifiedFact(value=value, source="NPS api.nps.gov", fetched_at=_NOW)


def test_closure_alert_warns_instead_of_blocking() -> None:
    # GLM red-team F1 (HIGH): a verified NPS Closure alert must become a prominent
    # CardWarning — never a block, never a ranking penalty (2026-07-01 decision,
    # rule #2). Before this branch existed the closure rode only as a condition
    # line while the verdict said "Good to go" beside it.
    fact = _closure_fact([{"title": "Old Rag Area Closure", "category": "Closure"}])
    v = evaluate_guardrails({ConditionKind.closures: fact})
    assert not v.blocked
    assert not v.blocks
    assert any("closure alert: Old Rag Area Closure" in w.text for w in v.warnings)


def test_closure_warning_is_source_stamped_and_park_scoped() -> None:
    # Mirrors the weather-warning contract: cause + SHORT provider name + observed-at.
    # The NPS fact is park-level (nearest unit within 50 mi, not trail-specific), so
    # the park name rides the text — the scope stays legible on the card itself.
    fact = _closure_fact([{"title": "Old Rag Area Closure", "category": "Closure"}])
    v = evaluate_guardrails({ConditionKind.closures: fact})
    (warning,) = v.warnings
    assert warning.kind == "closures"
    assert warning.source == "NPS"
    assert warning.observed_at == _NOW
    assert "Shenandoah National Park" in warning.text


def test_danger_alert_warns_with_its_category() -> None:
    # The adapter keeps only the Closure/Danger categories; both classes warn, each
    # naming its own category so a danger alert never masquerades as a closure.
    fact = _closure_fact([{"title": "Bear Activity", "category": "Danger"}])
    v = evaluate_guardrails({ConditionKind.closures: fact})
    assert any("danger alert: Bear Activity" in w.text for w in v.warnings)


def test_zero_closure_alerts_stay_silent() -> None:
    # A checked-clear closures fact (count 0) is the CDP-02 no_hazard state — calm
    # silence, never a warning.
    v = evaluate_guardrails({ConditionKind.closures: _closure_fact([])})
    assert not v.blocked
    assert not v.warnings


def test_no_park_in_range_closures_fact_stays_silent() -> None:
    # The sourced "no NPS unit within the radius" answer (no_data) carries no alerts
    # key at all — no warning, no block.
    fact = VerifiedFact(
        value={"in_range": False, "radius_miles": 50.0},
        source="NPS api.nps.gov",
        fetched_at=_NOW,
    )
    v = evaluate_guardrails({ConditionKind.closures: fact})
    assert not v.blocked
    assert not v.warnings


def test_duplicate_closure_alerts_collapse_to_one_warning() -> None:
    # Same discipline as the NWS dedupe: a card never wears the same warning twice.
    fact = _closure_fact(
        [
            {"title": "Old Rag Area Closure", "category": "Closure"},
            {"title": "Old Rag Area Closure", "category": "Closure"},
        ]
    )
    v = evaluate_guardrails({ConditionKind.closures: fact})
    assert len(v.warnings) == 1


def test_untitled_closure_alert_still_warns() -> None:
    # A count>0 fact must never quietly produce zero warnings — a missing/blank
    # title degrades to a generic pointer, never to silence (rule #1's spirit).
    fact = _closure_fact([{"title": None, "category": "Closure"}])
    v = evaluate_guardrails({ConditionKind.closures: fact})
    assert len(v.warnings) == 1
    assert "closure alert" in v.warnings[0].text


def test_malformed_closure_alerts_never_crash() -> None:
    # Defensive at the boundary: non-dict entries and a non-list alerts value no-op.
    v = evaluate_guardrails({ConditionKind.closures: _closure_fact(["junk", 42])})
    assert not v.blocked
    bad = VerifiedFact(value={"alerts": "junk", "count": 1}, source="NPS", fetched_at=_NOW)
    assert not evaluate_guardrails({ConditionKind.closures: bad}).blocked


def test_clean_conditions_pass() -> None:
    v = evaluate_guardrails({ConditionKind.weather: _fact({"active_alerts": []})})
    assert not v.blocked
    assert not v.blocks
    assert not v.warnings
    assert not v.unavailable


def test_weather_outage_never_blocks_even_with_other_kinds_probed() -> None:
    # The P0 regression: every weather probe failing must never blank the feed
    # (rule #6). Air/fire simply weren't probed either — no signal, no block.
    v = evaluate_guardrails({}, probed_kinds={ConditionKind.weather})
    assert not v.blocked
    assert v.blocks == ()
    assert len(v.unavailable) == 1
    assert v.unavailable[0].kind == "weather"


# ── S1: graded warning severity (frame-conditions-wave Q7 / epic-054) ─────────


def _weather_fact(event: str, severity: str | None) -> VerifiedFact:
    severities = {} if severity is None else {event: severity}
    return VerifiedFact(
        value={"active_alerts": [event], "alert_severities": severities},
        source="NWS api.weather.gov",
        fetched_at=_NOW,
    )


def test_nws_extreme_alert_grades_blocked() -> None:
    v = evaluate_guardrails(
        {ConditionKind.weather: _weather_fact("Extreme Heat Warning", "Extreme")}
    )
    assert v.warnings[0].severity == "blocked"


def test_nws_severe_alert_grades_blocked() -> None:
    v = evaluate_guardrails({ConditionKind.weather: _weather_fact("Tornado Warning", "Severe")})
    assert v.warnings[0].severity == "blocked"


def test_nws_moderate_and_minor_alerts_grade_heads_up() -> None:
    moderate = evaluate_guardrails(
        {ConditionKind.weather: _weather_fact("Flood Watch", "Moderate")}
    )
    minor = evaluate_guardrails({ConditionKind.weather: _weather_fact("Frost Advisory", "Minor")})
    assert moderate.warnings[0].severity == "heads_up"
    assert minor.warnings[0].severity == "heads_up"


def test_nws_unknown_or_missing_severity_grades_heads_up() -> None:
    # Never louder than graded (AC-1.3): a real event whose severity map says
    # "Unknown", or a fact that carries no severity map at all, both degrade to
    # the ungraded floor rather than guessing "blocked".
    unknown = evaluate_guardrails(
        {ConditionKind.weather: _weather_fact("Small Craft Advisory", "Unknown")}
    )
    absent_map = evaluate_guardrails(
        {ConditionKind.weather: _weather_fact("Small Craft Advisory", None)}
    )
    no_alert_severities_key = evaluate_guardrails(
        {
            ConditionKind.weather: VerifiedFact(
                value={"active_alerts": ["Small Craft Advisory"]},
                source="NWS api.weather.gov",
                fetched_at=_NOW,
            )
        }
    )
    assert unknown.warnings[0].severity == "heads_up"
    assert absent_map.warnings[0].severity == "heads_up"
    assert no_alert_severities_key.warnings[0].severity == "heads_up"


def test_nws_severity_grade_is_case_insensitive() -> None:
    v = evaluate_guardrails(
        {ConditionKind.weather: _weather_fact("Flash Flood Warning", "extreme")}
    )
    assert v.warnings[0].severity == "blocked"


def test_air_quality_warn_tier_grades_heads_up() -> None:
    v = evaluate_guardrails({ConditionKind.air: _fact({"aqi": 120})})
    assert v.warnings[0].severity == "heads_up"


def test_air_quality_block_tier_stays_a_hard_block_not_a_graded_warning() -> None:
    # AC-1.2 "existing thresholds unchanged": AQI >= AQI_BLOCK is still a hard
    # set-aside (never a CardWarning), so there is nothing to grade "blocked" —
    # the removal itself is the qualitative "blocked" reading.
    v = evaluate_guardrails({ConditionKind.air: _fact({"aqi": 250})})
    assert v.blocked
    assert v.warnings == ()


def test_fire_warning_grades_heads_up() -> None:
    v = evaluate_guardrails({ConditionKind.fire: _fact({"hotspot_count": 2})})
    assert v.warnings[0].severity == "heads_up"


def test_closure_warning_always_grades_blocked() -> None:
    v = evaluate_guardrails(
        {ConditionKind.closures: _closure_fact([{"title": "T", "category": "Closure"}])}
    )
    assert v.warnings[0].severity == "blocked"


def test_danger_alert_also_grades_blocked() -> None:
    v = evaluate_guardrails(
        {ConditionKind.closures: _closure_fact([{"title": "Bear Activity", "category": "Danger"}])}
    )
    assert v.warnings[0].severity == "blocked"


def test_card_warning_default_severity_is_heads_up() -> None:
    # A CardWarning built without an explicit severity (the dataclass default) —
    # the safety-net "never louder than graded" floor.
    from orchestration.curator import CardWarning

    w = CardWarning("weather", "text", "src", _NOW)
    assert w.severity == "heads_up"


class _FakeJudge:
    name = "fake"

    def __init__(self, text: str) -> None:
        self.text = text

    def complete(self, request: Any) -> LLMResponse:
        return LLMResponse(text=self.text, model=request.model, provider=self.name)


def test_rank_ids_reorders_by_judge() -> None:
    items = [("a", "A"), ("b", "B"), ("c", "C")]
    assert rank_ids(items, _FakeJudge('["c","a","b"]'), "m") == ["c", "a", "b"]


def test_rank_ids_appends_dropped_and_survives_garbage() -> None:
    items = [("a", "A"), ("b", "B")]
    assert rank_ids(items, _FakeJudge('["b"]'), "m") == ["b", "a"]  # dropped 'a' appended
    assert rank_ids(items, _FakeJudge("not json"), "m") == ["a", "b"]  # fallback to input order


# ── Way-type de-rank (roadlike/access ways sink; fire roads kept) ───────────


def test_is_roadlike_demoted_access_track_demoted() -> None:
    # A `track` named like a service/access road → demoted.
    assert is_roadlike_demoted("track", "Reservoir Access Road") is False  # ends in Road → kept
    assert is_roadlike_demoted("track", "Utility Access") is True
    assert is_roadlike_demoted("service", "Maintenance Drive") is True
    assert is_roadlike_demoted("track", "Powerline Cut") is True


def test_is_roadlike_demoted_keeps_fire_and_dike_roads() -> None:
    # Same care as #56/#75: legit fire/dike/forest roads stay in normal position even
    # though they're `track`s.
    for name in ("Compton Gap Road", "Mathews Arm Fire Road", "Salt Pond Road", "Big Meadows Dike"):
        assert is_roadlike_demoted("track", name) is False


def test_is_roadlike_demoted_never_touches_footpaths() -> None:
    # A genuine foot-trail type is never demoted on this signal, whatever the name.
    assert is_roadlike_demoted("path", "Utility Access Trail") is False
    assert is_roadlike_demoted("footway", "Service Loop") is False
    assert is_roadlike_demoted("bridleway", "Maintenance Spur") is False
    assert is_roadlike_demoted(None, "Access Road Trail") is False


def test_is_roadlike_demoted_plain_track_not_demoted_without_access_signal() -> None:
    # Precision over recall: a bare-named track (no access signal) is NOT demoted — a
    # false demote is worse than leaving an ambiguous track in place.
    assert is_roadlike_demoted("track", "Whiteoak Canyon") is False


def test_is_outside_boundary_demoted_ambiguous_way_outside() -> None:
    # The whole point: an ambiguous track/footway OUTSIDE the park boundary → demoted,
    # whatever its (even "Trail"-suffixed) name. This is the "Andreae" wellness-path case.
    assert is_outside_boundary_demoted("footway", "Andreae Family Wellness Trail", True) is True
    assert is_outside_boundary_demoted("track", "Some Access Way", True) is True


def test_is_outside_boundary_demoted_inside_or_unknown_kept() -> None:
    # Inside the boundary (False) or no boundary / no classification (None) → never
    # demoted. None is the degrade path: a region with no real boundary polygon.
    assert is_outside_boundary_demoted("footway", "Andreae Family Wellness Trail", False) is False
    assert is_outside_boundary_demoted("footway", "Andreae Family Wellness Trail", None) is False
    assert is_outside_boundary_demoted("track", "Anything", None) is False


def test_is_outside_boundary_demoted_keeps_fire_roads_even_outside() -> None:
    # A fire/dike/forest road mapped just outside the buffered boundary is still a hike.
    for name in ("Compton Gap Road", "Salt Pond Road", "Mathews Arm Fire Road", "River Dike"):
        assert is_outside_boundary_demoted("track", name, True) is False


def test_is_outside_boundary_demoted_never_touches_strong_foot_types() -> None:
    # path/bridleway/steps are strong trail signals — never demoted on position alone,
    # even outside the boundary. Only the ambiguous track/footway middle is eligible.
    assert is_outside_boundary_demoted("path", "Ridge Trail", True) is False
    assert is_outside_boundary_demoted("bridleway", "Horse Loop", True) is False
    assert is_outside_boundary_demoted("steps", "Overlook Steps", True) is False
    assert is_outside_boundary_demoted(None, "Mystery", True) is False


def test_is_over_length_demoted_over_ceiling() -> None:
    assert is_over_length_demoted(9.5, 8.0) is True


def test_is_over_length_demoted_under_or_at_ceiling_kept() -> None:
    assert is_over_length_demoted(7.9, 8.0) is False
    assert is_over_length_demoted(8.0, 8.0) is False  # exactly at ceiling → kept


def test_is_over_length_demoted_missing_data_never_demoted() -> None:
    # A candidate with no known length_mi isn't "too long" — never demoted.
    assert is_over_length_demoted(None, 8.0) is False
    # No filter requested → nothing is demoted, however long.
    assert is_over_length_demoted(20.0, None) is False
    assert is_over_length_demoted(None, None) is False


def test_valid_max_length_mi_accepts_positive_numbers() -> None:
    assert valid_max_length_mi(8) == 8.0
    assert valid_max_length_mi(8.5) == 8.5


def test_valid_max_length_mi_rejects_malformed_values() -> None:
    # A malformed LLM-parsed value must no-op the filter, never crash it.
    assert valid_max_length_mi(None) is None
    assert valid_max_length_mi(True) is None  # bool is an int in Python — excluded
    assert valid_max_length_mi(False) is None
    assert valid_max_length_mi("8") is None
    assert valid_max_length_mi([8]) is None
    assert valid_max_length_mi(0) is None
    assert valid_max_length_mi(-3) is None


def test_rank_ids_demotes_roadlike_below_real_trails() -> None:
    # The judge orders the roadlike way first; demotion still sinks it below the trails,
    # keeping the trails' relative taste order. Never dropped (still in the result).
    items = [("svc", "Utility Access"), ("t1", "Old Rag"), ("t2", "Whiteoak Canyon")]
    order = rank_ids(items, _FakeJudge('["svc","t1","t2"]'), "m", demote_ids={"svc"})
    assert order == ["t1", "t2", "svc"]


def test_rank_ids_no_demotion_when_empty() -> None:
    items = [("a", "A"), ("b", "B")]
    assert rank_ids(items, _FakeJudge('["b","a"]'), "m", demote_ids=set()) == ["b", "a"]


# ── Corroboration rescue (Lane C, default-off) ───────────────────────────────


def test_corroboration_rescue_enabled_default_off() -> None:
    # Unset, garbage, and explicit "off" all resolve to disabled — the mechanism
    # never silently switches on.
    assert corroboration_rescue_enabled({}) is False
    assert corroboration_rescue_enabled({"ADVENTURE_CORROBORATION_RESCUE": "nonsense"}) is False
    assert corroboration_rescue_enabled({"ADVENTURE_CORROBORATION_RESCUE": "0"}) is False
    assert corroboration_rescue_enabled({"ADVENTURE_CORROBORATION_RESCUE": "true"}) is True


def test_is_corroboration_rescued_lifts_osm_only_demote_with_authoritative_corroboration() -> None:
    # The demote signal is an OSM-tag heuristic (an access-y name); an authoritative
    # agency source (NPS) independently agreeing the way exists is real corroborating
    # evidence the heuristic didn't have — rescued.
    assert (
        is_corroboration_rescued("Utility Access", sources=["osm", "nps"], corroboration=2) is True
    )


def test_is_corroboration_rescued_single_source_never_rescued() -> None:
    # corroboration == 1 (or every source is OSM-only) → no second opinion exists to
    # override the original demote heuristic with — never rescued by this mechanism.
    assert is_corroboration_rescued("Utility Access", sources=["osm"], corroboration=1) is False
    assert is_corroboration_rescued("Utility Access", sources=[], corroboration=1) is False


def test_is_corroboration_rescued_requires_an_authoritative_source() -> None:
    # Two distinct origins, neither authoritative — an OSM-only cluster (or an echo
    # source) never clears the "authoritative coverage present" gate.
    assert (
        is_corroboration_rescued("Utility Access", sources=["osm", "echo"], corroboration=2)
        is False
    )


def test_apply_corroboration_rescue_disabled_by_default_leaves_demote_set_untouched() -> None:
    demote_ids = {"svc"}
    names = {"svc": "Utility Access"}
    rescued = apply_corroboration_rescue(
        demote_ids,
        names,
        corroboration={"svc": 5},
        sources={"svc": ["osm", "nps"]},
        enabled=False,
    )
    assert rescued == demote_ids


def test_apply_corroboration_rescue_lifts_only_the_corroborated_member() -> None:
    # Two ways in the demote set: one corroborated by an authoritative source (rescued
    # out), one single-source (stays demoted) — this mechanism only ever removes, and
    # only the ones with real corroborating evidence.
    demote_ids = {"svc", "solo"}
    names = {"svc": "Utility Access", "solo": "Powerline Cut"}
    rescued = apply_corroboration_rescue(
        demote_ids,
        names,
        corroboration={"svc": 2, "solo": 1},
        sources={"svc": ["osm", "usfs"], "solo": ["osm"]},
        enabled=True,
    )
    assert rescued == {"solo"}


def test_apply_corroboration_rescue_never_adds_a_demotion() -> None:
    # "clean" was never in demote_ids — however well (or poorly) it corroborates, it
    # can never appear in the output. This mechanism only ever removes members of an
    # existing demote set, never adds one (Rule #2).
    rescued = apply_corroboration_rescue(
        {"svc"},
        {"svc": "Utility Access", "clean": "Old Rag"},
        corroboration={"svc": 2, "clean": 1},
        sources={"svc": ["osm", "usfs"], "clean": ["osm"]},
        enabled=True,
    )
    assert rescued == set()  # "svc" rescued (real corroboration); "clean" never entered


def test_rank_ids_corroboration_rescue_lifts_way_back_to_normal_order(monkeypatch: Any) -> None:
    monkeypatch.setenv("ADVENTURE_CORROBORATION_RESCUE", "true")
    items = [("svc", "Utility Access"), ("t1", "Old Rag"), ("t2", "Whiteoak Canyon")]
    order = rank_ids(
        items,
        _FakeJudge('["svc","t1","t2"]'),
        "m",
        demote_ids={"svc"},
        corroboration={"svc": 2},
        corroboration_sources={"svc": ["osm", "nps"]},
    )
    assert order == ["svc", "t1", "t2"]  # rescued — judge's order stands, un-demoted


def test_rank_ids_corroboration_rescue_off_by_default_still_demotes() -> None:
    # Same inputs as above but the env flag is unset — the default-off path still
    # demotes exactly as before this feature existed.
    items = [("svc", "Utility Access"), ("t1", "Old Rag"), ("t2", "Whiteoak Canyon")]
    order = rank_ids(
        items,
        _FakeJudge('["svc","t1","t2"]'),
        "m",
        demote_ids={"svc"},
        corroboration={"svc": 2},
        corroboration_sources={"svc": ["osm", "nps"]},
    )
    assert order == ["t1", "t2", "svc"]


def test_is_over_length_demoted_over_budget() -> None:
    assert is_over_length_demoted(9.0, 8.0) is True


def test_is_over_length_demoted_under_or_equal_budget_kept() -> None:
    assert is_over_length_demoted(8.0, 8.0) is False
    assert is_over_length_demoted(5.0, 8.0) is False


def test_is_over_length_demoted_null_safe() -> None:
    # No filter set, or unknown candidate length (pre-backfill corpus) — never demoted.
    assert is_over_length_demoted(9.0, None) is False
    assert is_over_length_demoted(None, 8.0) is False
    assert is_over_length_demoted(None, None) is False


def test_filter_preference_hints_dog_and_difficulty() -> None:
    hint = filter_preference_hints({"dog": True, "difficulty": "Easy"})
    assert hint is not None
    assert "dog-friendly trail preferred" in hint
    assert "preferred difficulty: easy" in hint


def test_filter_preference_hints_dog_false() -> None:
    hint = filter_preference_hints({"dog": False})
    assert hint is not None
    assert "not bringing a dog" in hint


def test_filter_preference_hints_ignores_malformed_and_unknown_values() -> None:
    assert filter_preference_hints({"dog": "yes", "difficulty": "extreme"}) is None
    assert filter_preference_hints({}) is None


def test_rank_ids_demotes_over_length_below_real_trails() -> None:
    items = [("long", "Long Trail"), ("t1", "Old Rag"), ("t2", "Whiteoak Canyon")]
    order = rank_ids(items, _FakeJudge('["long","t1","t2"]'), "m", demote_ids={"long"})
    assert order == ["t1", "t2", "long"]
