"""Templated hedged-phrasing tests (deterministic via injected `now`)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from orchestration.adapters.base import VerifiedFact
from orchestration.confidence import Confidence
from orchestration.present import summarize_fact

NOW = datetime(2026, 6, 23, 12, 0, 0, tzinfo=timezone.utc)


def _fact(value: Any, *, mins: int = 10) -> VerifiedFact:
    return VerifiedFact(value=value, source="NWS", fetched_at=NOW - timedelta(minutes=mins))


def test_stated_line_has_source_and_no_hedge() -> None:
    c = Confidence(0.9, "high", "stated", True)
    line = summarize_fact(
        "weather",
        _fact({"short_forecast": "Sunny", "temperature": 70, "temperature_unit": "F"}),
        c,
        now=NOW,
    )
    assert "Sunny, 70°F" in line.text
    assert "(NWS, 10m ago)" in line.text
    assert not line.text.startswith(("Likely", "Unverified"))
    assert line.presentation == "stated"


def test_flagged_line_marked_unverified() -> None:
    c = Confidence(0.2, "low", "flagged", False)
    line = summarize_fact("air", _fact({"aqi": 120, "category": "USG"}), c, now=NOW)
    assert line.text.startswith("Unverified: ")
    assert "AQI 120" in line.text


def test_hedged_line_prefix() -> None:
    c = Confidence(0.6, "medium", "hedged", True)
    line = summarize_fact("fire", _fact({"hotspot_count": 2}), c, now=NOW)
    assert line.text.startswith("Likely: ")
    assert "2 active-fire" in line.text
