"""Presentation edge cases — aging buckets, unknown kinds, and body fallback."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from orchestration.adapters.base import ConditionKind, VerifiedFact
from orchestration.confidence import Confidence
from orchestration.curator import evaluate_guardrails
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


def test_unknown_kind_falls_back_to_a_neutral_placeholder() -> None:
    # Epic 046 S2 B6: a non-dict fact value is a shape violation, not content to
    # pass through raw — never leaked verbatim, never rendered as a bare `None`.
    line = summarize_fact("mystery", _fact("plain text"), _high(), now=NOW)
    assert "plain text" not in line.text
    assert "unavailable" in line.text
    assert line.kind == "mystery"


def test_unknown_kind_with_dict_never_leaks_a_dict_repr() -> None:
    # B6: an unhandled kind whose value IS a dict used to fall through to
    # `str(value)` — the exact `{'foo': 'bar'}` repr leak the finding named.
    line = summarize_fact("mystery", _fact({"a": 1}), _high(), now=NOW)
    assert "{" not in line.text
    assert "'a'" not in line.text
    assert "unavailable" in line.text


def test_weather_body_without_temperature_uses_forecast_only() -> None:
    line = summarize_fact("weather", _fact({"short_forecast": "Cloudy"}), _high(), now=NOW)
    assert "Cloudy" in line.text
    assert "°" not in line.text


def test_weather_body_without_forecast_defaults_unit_and_drops_placeholder() -> None:
    # B5: a missing `short_forecast` must never fall back to the literal word
    # "forecast" standing in as if it were a sky reading; the unit defaults to F.
    line = summarize_fact("weather", _fact({"temperature": 70}), _high(), now=NOW)
    assert "70°F" in line.text
    assert "forecast" not in line.text.lower()


def test_weather_body_with_neither_temp_nor_forecast_is_honest_not_fabricated() -> None:
    # Neither sub-field present: no fabricated reading, no crash, no `None`.
    line = summarize_fact("weather", _fact({}), _high(), now=NOW)
    assert "None" not in line.text
    assert "unavailable" in line.text


def test_air_body_with_missing_keys_avoids_none_leak() -> None:
    # Epic 046 S2 B4 (+ the aqi-null guard AC-2.4 asks for): neither a missing
    # `category` nor a missing `aqi` may render the literal word "None".
    line = summarize_fact("air", _fact({}), _high(), now=NOW)
    assert "None" not in line.text
    assert "AQI" in line.text
    assert "· SRC, just now" in line.text


def test_air_body_drops_parenthetical_when_category_is_falsy() -> None:
    line = summarize_fact("air", _fact({"aqi": 45}), _high(), now=NOW)
    assert "AQI 45" in line.text
    assert "(" not in line.text
    assert "None" not in line.text


def test_fire_body_defaults_to_zero_hotspots() -> None:
    line = summarize_fact("fire", _fact({}), _high(), now=NOW)
    assert "0 active-fire detections nearby" in line.text
    assert "(s)" not in line.text


def test_permits_body_defaults_to_zero_count() -> None:
    line = summarize_fact("permits", _fact({}), _high(), now=NOW)
    # B8: a facility count alone never answers "do I need a permit" — the line
    # says plainly that permit requirements were not fetched.
    assert "not fetched" in line.text
    assert "0 nearby facilities" in line.text


def test_closures_body_renders_count_and_park() -> None:
    value = {"park": "Shenandoah National Park", "park_code": "SHEN", "count": 2}
    line = summarize_fact("closures", _fact(value), _high(), now=NOW)
    assert "2 NPS closure/danger alerts — Shenandoah National Park" in line.text
    assert "(s)" not in line.text
    assert "NPS SHEN" in line.source


def test_closures_body_defaults_to_zero_count_and_nearest_park() -> None:
    line = summarize_fact("closures", _fact({}), _high(), now=NOW)
    # B3: `park` present-but-None (or entirely absent, as here) must never leak
    # the literal "None" — `the nearest park`, never a bare `dict.get` default.
    assert "0 NPS closure/danger alerts — the nearest park" in line.text


def test_closures_body_with_null_park_value_never_leaks_none() -> None:
    # B3's exact shape: the key IS present, its value is None (nps_alerts.py sets
    # `"park": full_name` where `fullName` can be null) — `dict.get(k, default)`
    # does NOT catch this; only an `or` guard does.
    line = summarize_fact("closures", _fact({"park": None, "count": 1}), _high(), now=NOW)
    assert "None" not in line.text
    assert "the nearest park" in line.text
    assert "1 NPS closure/danger alert —" in line.text  # singular, count == 1


def test_water_body_prefers_monitoring_location() -> None:
    line = summarize_fact("water", _fact({"monitoring_location": "Potomac"}), _high(), now=NOW)
    assert "Potomac" in line.text


def test_water_body_never_shows_the_raw_site_id() -> None:
    # B7: a bare station id is not a name a hiker recognizes — never surfaced as
    # if it were one. The honest fallback names the gap instead.
    line = summarize_fact("water", _fact({"site_id": "AB12"}), _high(), now=NOW)
    assert "AB12" not in line.text
    assert "the nearest gauge" in line.text
    assert "None" not in line.text


def test_water_body_renders_the_fetched_discharge_not_the_gauge_address() -> None:
    # B7, the "answers" half: the discharge reading is the actual hiker question
    # ("how much water is flowing"), not the ALL-CAPS station address.
    value = {"monitoring_location": "HAWKSBILL CREEK NEAR LURAY, VA", "latest_discharge_cfs": 12.4}
    line = summarize_fact("water", _fact(value), _high(), now=NOW)
    assert "~12 cfs at Hawksbill Creek gauge" in line.text
    assert "HAWKSBILL" not in line.text  # never the raw ALL-CAPS official name
    assert "NEAR LURAY" not in line.text  # truncated to the recognizable part


def test_water_body_missing_discharge_at_a_named_gauge_is_disclosed_not_none() -> None:
    # The site is known but no reading came back — still never `None`, still
    # never the bare id, and the gauge name still renders (title-cased).
    line = summarize_fact(
        "water", _fact({"monitoring_location": "SOUTH RIVER NEAR WAYNESBORO, VA"}), _high(), now=NOW
    )
    assert "None" not in line.text
    assert "South River gauge" in line.text
    assert "unavailable" in line.text


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


# ── Epic 046 S2 AC-2.4: the process-net guard (sweep §6) ─────────────────────
# Falsifying by construction: each assertion below targets a literal degenerate
# token that used to reach the wire (`(s)`, a bare `None`, a dict-repr brace).
# If any B1/B2/B3/B6 guard in `present.py::_body` or `curator.py`'s warning
# twins is reverted, the matching case here goes red — this is the guard
# `make check` wires in (sweep §6 item 3 / Epic 046 AC-6.2).

_DEGENERATE_TOKENS = ("(s)", "None", "{", "}")


def _assert_no_degenerate_tokens(text: str) -> None:
    for token in _DEGENERATE_TOKENS:
        assert token not in text, f"degenerate token {token!r} leaked into {text!r}"


@pytest.mark.parametrize("count", [0, 1, 2])
def test_fire_body_never_leaks_across_the_count_range(count: int) -> None:
    line = summarize_fact("fire", _fact({"hotspot_count": count}), _high(), now=NOW)
    _assert_no_degenerate_tokens(line.text)
    # Exact grammar, not just "no (s) leaked" — a regression that always emitted
    # the plural (or always the singular) would slip past a looser substring
    # check; pinning the word per count catches that too.
    word = "detection" if count == 1 else "detections"
    assert f"{count} active-fire {word} nearby" in line.text


@pytest.mark.parametrize("count", [0, 1, 2])
def test_permits_body_never_leaks_across_the_count_range(count: int) -> None:
    line = summarize_fact("permits", _fact({"count": count}), _high(), now=NOW)
    _assert_no_degenerate_tokens(line.text)
    word = "facility" if count == 1 else "facilities"
    assert f"not fetched — {count} nearby {word}" in line.text


@pytest.mark.parametrize("park", [None, "Denali National Park"])
@pytest.mark.parametrize("count", [0, 1, 2])
def test_closures_body_never_leaks_across_count_and_null_park(count: int, park: str | None) -> None:
    line = summarize_fact("closures", _fact({"count": count, "park": park}), _high(), now=NOW)
    _assert_no_degenerate_tokens(line.text)
    word = "alert" if count == 1 else "alerts"
    assert f"{count} NPS closure/danger {word} —" in line.text


@pytest.mark.parametrize("aqi", [0, 45, 250])
def test_air_body_never_leaks_with_null_category(aqi: int) -> None:
    line = summarize_fact("air", _fact({"aqi": aqi}), _high(), now=NOW)
    _assert_no_degenerate_tokens(line.text)
    assert f"AQI {aqi}" in line.text


@pytest.mark.parametrize("count", [1, 2])
def test_curator_fire_warning_never_leaks_across_the_count_range(count: int) -> None:
    # The `curator.py:229` twin of B2 — the same count sweep, through the
    # warning builder this time, not `present.py`'s body. (count=0 never warns —
    # `evaluate_guardrails` gates the fire branch on a truthy count.)
    fact = VerifiedFact(value={"hotspot_count": count}, source="NASA FIRMS", fetched_at=NOW)
    v = evaluate_guardrails({ConditionKind.fire: fact})
    assert len(v.warnings) == 1
    _assert_no_degenerate_tokens(v.warnings[0].text)
    word = "detection" if count == 1 else "detections"
    assert f"{count} active-fire {word} nearby" in v.warnings[0].text


def test_curator_closure_warning_null_title_never_leaks_none() -> None:
    # B3 sibling (curator.py:254), re-verified in place: `_closure_alerts`'s
    # existing title guard already degrades a null title to a generic pointer —
    # this locks that in as a falsifying test rather than leaving it implicit.
    fact = VerifiedFact(
        value={"alerts": [{"title": None, "category": "Closure"}], "count": 1, "park": None},
        source="NPS api.nps.gov",
        fetched_at=NOW,
    )
    v = evaluate_guardrails({ConditionKind.closures: fact})
    assert len(v.warnings) == 1
    _assert_no_degenerate_tokens(v.warnings[0].text)
    assert "see park alerts" in v.warnings[0].text


def _high() -> Confidence:
    return Confidence(0.9, "high", "stated", True)
