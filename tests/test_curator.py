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
    is_corroboration_rescued,
    is_outside_boundary_demoted,
    is_roadlike_demoted,
    rank_ids,
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
    # The card warning mirrors a feed line: cause + the fact's source + observed-at.
    fact = VerifiedFact(
        value={"active_alerts": ["Tornado Warning"]},
        source="NWS api.weather.gov",
        fetched_at=_NOW,
    )
    v = evaluate_guardrails({ConditionKind.weather: fact})
    (warning,) = v.warnings
    assert warning.kind == "weather"
    assert warning.source == "NWS api.weather.gov"
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
