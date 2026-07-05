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
    # Calm line: value · short source, freshness — no raw codes, no descriptor.
    assert "Sunny 70°F · NWS, 10m ago" in line.text
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


# ── CDP-01 item 2: honest single-source labeling (never imply >1 for one source) ──
# The descriptor + raw origin ids now live in `line.source` (the detail Sources
# section), keeping them off the calm feed line while dropping no provenance.


def _high() -> Confidence:
    return Confidence(0.9, "high", "stated", True)


def test_water_line_names_single_authoritative_source_with_site_id() -> None:
    line = summarize_fact("water", _fact({"site_id": "01631000"}), _high(), now=NOW)
    assert "single authoritative source (USGS site 01631000)" in line.source
    # the formatted station origin stays OUT of the glanceable line
    assert "USGS site" not in line.text
    # freshness still rides the line, in plain words
    assert "· NWS, 10m ago" in line.text


def test_weather_line_carries_nws_office_and_grid_origin() -> None:
    line = summarize_fact(
        "weather",
        _fact({"short_forecast": "Sunny", "forecast_office": "LWX", "grid_x": 96, "grid_y": 70}),
        _high(),
        now=NOW,
    )
    assert "single authoritative source (NWS LWX 96,70)" in line.source
    # the grid coords never clutter the line
    assert "96,70" not in line.text


def test_fire_line_carries_distinct_satellites() -> None:
    line = summarize_fact(
        "fire", _fact({"hotspot_count": 1, "satellites": ["Aqua", "N"]}), _high(), now=NOW
    )
    assert "single authoritative source (FIRMS Aqua/N)" in line.source


def test_air_is_labeled_aggregated_not_corroborated() -> None:
    # AirNow is an aggregator → "aggregated", never implying independent corroboration.
    line = summarize_fact("air", _fact({"aqi": 42, "category": "Good"}), _high(), now=NOW)
    assert "single aggregated source" in line.source
    assert "authoritative" not in line.source


def test_label_falls_back_to_bare_descriptor_without_origin() -> None:
    # No recoverable origin id (e.g. forecast office absent) → bare honest descriptor.
    line = summarize_fact("weather", _fact({"short_forecast": "Cloudy"}), _high(), now=NOW)
    assert "single authoritative source" in line.source
    assert "single authoritative source (" not in line.source  # no empty parens


def test_full_source_and_short_provider_are_both_present() -> None:
    # The line wears the short provider; the full label lives in `source`.
    line = summarize_fact("weather", _fact({"short_forecast": "Sunny"}), _high(), now=NOW)
    assert "· NWS," in line.text  # short, glanceable
    assert line.source.startswith("NWS ")  # full label, for the Sources section


# ── Epic 026a: honest per-fact `sources` (never fabricated multi-source corroboration) ──


def test_sources_carries_the_real_single_live_provider() -> None:
    # Live facts are single-source by construction (CDP-01) — the field reports that
    # honestly rather than padding it, so a later UI cue never implies corroboration a
    # live fact doesn't have.
    line = summarize_fact("weather", _fact({"short_forecast": "Sunny"}), _high(), now=NOW)
    assert line.sources == ("NWS",)


def test_sources_reflects_the_fact_own_provider_not_a_fixed_name() -> None:
    usgs_fact = VerifiedFact(
        value={"site_id": "01631000"},
        source="USGS Water Data (waterservices.usgs.gov)",
        fetched_at=NOW,
    )
    line = summarize_fact("water", usgs_fact, _high(), now=NOW)
    assert line.sources == ("USGS",)  # the recognizable short name, never the raw source
