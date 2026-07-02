"""Curator guardrail tests — the verified-vs-unverifiable split (2026-07-01).

A VERIFIED hazard (an alert with source + timestamp) becomes a prominent card
warning, never a block; an UNVERIFIABLE required condition (failed weather probe
or failed alerts sub-call) blocks (set aside with disclosure, rule #1); hard
non-weather thresholds (hazardous AQI) keep their block semantics.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from orchestration.adapters.base import ConditionKind, VerifiedFact
from orchestration.curator import evaluate_guardrails, rank_ids
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


def test_failed_alerts_subcall_blocks_as_unverifiable() -> None:
    # active_alerts=None means the NWS alerts sub-call failed: the alert state is
    # UNKNOWN, and unknown never reads as "no alerts" (rule #1). Held back, source-stamped.
    fact = VerifiedFact(
        value={"short_forecast": "Sunny", "active_alerts": None},
        source="NWS api.weather.gov",
        fetched_at=_NOW,
    )
    v = evaluate_guardrails({ConditionKind.weather: fact})
    assert v.blocked
    (block,) = v.blocks
    assert block.kind == "weather"
    assert "couldn't be verified" in block.reason
    assert block.source == "NWS api.weather.gov"


def test_failed_weather_probe_blocks_when_weather_was_probed() -> None:
    # Weather probed, no source answered → unverifiable required condition → block.
    v = evaluate_guardrails({}, probed_kinds={ConditionKind.weather})
    assert v.blocked
    (block,) = v.blocks
    assert block.kind == "weather"
    assert "couldn't be verified" in block.reason


def test_absent_weather_passes_when_weather_not_probed() -> None:
    # No weather adapter configured in this deployment → no signal either way.
    v = evaluate_guardrails({})
    assert not v.blocked
    assert not v.warnings


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
