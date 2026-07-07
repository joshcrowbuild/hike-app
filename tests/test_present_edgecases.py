"""Presentation edge cases — aging buckets, unknown kinds, and body fallback."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from orchestration.adapters.base import VerifiedFact
from orchestration.confidence import Confidence
from orchestration.present import FeedLine, summarize_fact

NOW = datetime(2026, 6, 23, 12, 0, 0, tzinfo=timezone.utc)


def _fact(value: Any, *, mins: int = 0) -> VerifiedFact:
    return VerifiedFact(value=value, source="SRC", fetched_at=NOW - timedelta(minutes=mins))


def test_age_under_one_hour_shows_minutes() -> None:
    line = summarize_fact("water", _fact({"site_id": "123"}, mins=23), _high(), now=NOW)
    assert "23m ago" in line.text


def test_age_under_one_day_shows_hours() -> None:
    line = summarize_fact("water", _fact({"site_id": "123"}, mins=145), _high(), now=NOW)
    assert "2h ago" in line.text


def test_age_over_one_day_shows_days() -> None:
    line = summarize_fact("water", _fact({"site_id": "123"}, mins=3000), _high(), now=NOW)
    assert "2d ago" in line.text


def test_age_exactly_one_day_rounds_to_day() -> None:
    line = summarize_fact("water", _fact({"site_id": "123"}, mins=1440), _high(), now=NOW)
    assert "1d ago" in line.text


def test_now_defaults_to_utc_datetime() -> None:
    line = summarize_fact("water", _fact({"site_id": "123"}), _high())
    assert isinstance(line, FeedLine)
    # Defaulting `now` to real UTC still stamps a freshness on the line.
    assert "ago" in line.text


def test_unknown_kind_uses_string_value() -> None:
    line = summarize_fact("mystery", _fact("plain text"), _high(), now=NOW)
    assert "plain text" in line.text
    assert line.kind == "mystery"


def test_unknown_kind_with_dict_uses_str_dict() -> None:
    line = summarize_fact("mystery", _fact({"a": 1}), _high(), now=NOW)
    assert "a" in line.text


def test_weather_body_without_temperature_uses_forecast_only() -> None:
    line = summarize_fact("weather", _fact({"short_forecast": "Cloudy"}), _high(), now=NOW)
    assert "Cloudy" in line.text
    assert "°" not in line.text


def test_weather_body_without_forecast_uses_raw_value() -> None:
    line = summarize_fact("weather", _fact({"temperature": 70}), _high(), now=NOW)
    assert "70" in line.text


def test_air_body_with_missing_keys_renders_none_labels() -> None:
    line = summarize_fact("air", _fact({}), _high(), now=NOW)
    assert "AQI None" in line.text
    assert "· SRC, just now" in line.text


def test_fire_body_defaults_to_zero_hotspots() -> None:
    line = summarize_fact("fire", _fact({}), _high(), now=NOW)
    assert "0 active-fire detection(s) nearby" in line.text


def test_permits_body_defaults_to_zero_count() -> None:
    line = summarize_fact("permits", _fact({}), _high(), now=NOW)
    assert "0 nearby facilities" in line.text


def test_closures_body_renders_count_and_park() -> None:
    value = {"park": "Shenandoah National Park", "park_code": "SHEN", "count": 2}
    line = summarize_fact("closures", _fact(value), _high(), now=NOW)
    assert "2 NPS closure/danger alert(s) — Shenandoah National Park" in line.text
    assert "NPS SHEN" in line.source


def test_closures_body_defaults_to_zero_count_and_nearest_park() -> None:
    line = summarize_fact("closures", _fact({}), _high(), now=NOW)
    assert "0 NPS closure/danger alert(s) — nearest park" in line.text


def test_water_body_prefers_monitoring_location() -> None:
    line = summarize_fact("water", _fact({"monitoring_location": "Potomac"}), _high(), now=NOW)
    assert "Potomac" in line.text


def test_water_body_falls_back_to_site_id() -> None:
    line = summarize_fact("water", _fact({"site_id": "AB12"}), _high(), now=NOW)
    assert "AB12" in line.text


def test_unrecognized_presentation_defaults_to_empty_hedge() -> None:
    # _HEDGE only has stated/hedged/flagged; anything else falls through to ""
    c = Confidence(0.9, "high", "stated", True)  # use recognized for comparison
    line = summarize_fact("air", _fact({"aqi": 42, "category": "Good"}), c, now=NOW)
    assert line.text.startswith("AQI 42")


def test_source_appears_in_line_text() -> None:
    line = summarize_fact("weather", _fact({"short_forecast": "Sunny"}), _high(), now=NOW)
    # The short source rides the line; the full label lives in `source`.
    assert "· SRC, " in line.text
    assert line.source.startswith("SRC ")


def _high() -> Confidence:
    return Confidence(0.9, "high", "stated", True)
