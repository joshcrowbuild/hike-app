"""Curator guardrail tests — hard blocks vs. soft warnings."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from orchestration.adapters.base import VerifiedFact
from orchestration.curator import evaluate_guardrails


def _fact(value: Any) -> VerifiedFact:
    return VerifiedFact(value=value, source="t", fetched_at=datetime.now(timezone.utc))


def test_blocking_weather_alert_blocks() -> None:
    v = evaluate_guardrails({"weather": _fact({"active_alerts": ["Flash Flood Warning"]})})
    assert v.blocked
    assert any("Flash Flood" in b for b in v.blocks)


def test_non_blocking_alert_is_a_warning() -> None:
    v = evaluate_guardrails({"weather": _fact({"active_alerts": ["Frost Advisory"]})})
    assert not v.blocked
    assert any("Frost Advisory" in w for w in v.warnings)


def test_hazardous_aqi_blocks_elevated_warns() -> None:
    assert evaluate_guardrails({"air": _fact({"aqi": 250})}).blocked
    elevated = evaluate_guardrails({"air": _fact({"aqi": 120})})
    assert not elevated.blocked
    assert elevated.warnings


def test_fire_hotspots_warn_not_block() -> None:
    v = evaluate_guardrails({"fire": _fact({"hotspot_count": 3})})
    assert not v.blocked
    assert any("3 active-fire" in w for w in v.warnings)


def test_clean_conditions_pass() -> None:
    v = evaluate_guardrails({"weather": _fact({"active_alerts": []})})
    assert not v.blocked
    assert not v.blocks
    assert not v.warnings
