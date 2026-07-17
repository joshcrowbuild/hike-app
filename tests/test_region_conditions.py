"""Region-conditions derivation tests (frame-conditions-wave §5, epic-054 S2-S4).

Pure-function tests over the raw NWS fetch shape (`adapters.nws.fetch_region_raw`'s
`VerifiedFact.value`), never a live call. S4's mud calibration is exercised over the
four named fixture scenarios the epic specifies: dry, trace (0.2"), soaking (1.2"),
and missing-data.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from orchestration.adapters.base import VerifiedFact
from orchestration.region_conditions import (
    DEFAULT_MUD_THRESHOLD_IN,
    derive_forecast,
    derive_mud,
    derive_recent_precip,
    derive_region_conditions,
    mud_threshold_in,
)
from orchestration.when import TargetDay, TargetWindow, derive_target_window

_UTC = timezone.utc
_NOW = datetime(2026, 7, 15, 18, 0, tzinfo=_UTC)  # Wednesday
_NY = ZoneInfo("America/New_York")


def _raw(
    periods: object = None, observations: object = None, *, fetched_at: datetime = _NOW
) -> VerifiedFact:
    return VerifiedFact(
        value={"periods": periods, "observations": observations},
        source="NWS api.weather.gov",
        fetched_at=fetched_at,
    )


def _period(
    name: str,
    start: str,
    *,
    is_daytime: bool = True,
    temp: int | None = 70,
    unit: str | None = "F",
    pop: int | None = None,
    short: str | None = "Sunny",
) -> dict:
    d: dict = {"name": name, "startTime": start, "isDaytime": is_daytime}
    if temp is not None:
        d["temperature"] = temp
    if unit is not None:
        d["temperatureUnit"] = unit
    if pop is not None:
        d["probabilityOfPrecipitation"] = {"value": pop, "unitCode": "wmoUnit:percent"}
    if short is not None:
        d["shortForecast"] = short
    return d


_WINDOW = derive_target_window("weekendMorning", now=_NOW, tz=_UTC)  # today/sat/sun


# ── S2: forecast ────────────────────────────────────────────────────────────


def test_derive_forecast_none_when_raw_is_none() -> None:
    assert derive_forecast(None, _WINDOW, tz=_UTC) is None


def test_derive_forecast_none_when_periods_missing_or_empty() -> None:
    assert derive_forecast(_raw(periods=None), _WINDOW, tz=_UTC) is None
    assert derive_forecast(_raw(periods=[]), _WINDOW, tz=_UTC) is None


def test_derive_forecast_selects_daytime_period_matching_each_target_date() -> None:
    today, sat, sun = (d.on for d in _WINDOW.days)
    periods = [
        _period("Today", f"{today.isoformat()}T06:00:00-04:00", temp=88, pop=0, short="Sunny"),
        _period("Tonight", f"{today.isoformat()}T18:00:00-04:00", is_daytime=False, temp=60),
        _period(
            "Saturday", f"{sat.isoformat()}T06:00:00-04:00", temp=68, pop=20, short="Partly sunny"
        ),
        _period(
            "Sunday", f"{sun.isoformat()}T06:00:00-04:00", temp=71, pop=10, short="Mostly sunny"
        ),
    ]
    forecast = derive_forecast(_raw(periods=periods), _WINDOW, tz=_NY)
    assert forecast is not None
    assert forecast.target_key == "sat"
    assert forecast.source == "NWS"
    assert [(d.key, d.label, d.high_f, d.precip_pct, d.short) for d in forecast.days] == [
        ("today", "Today", 88, 0, "Sunny"),
        ("sat", "Sat", 68, 20, "Partly sunny"),
        ("sun", "Sun", 71, 10, "Mostly sunny"),
    ]


def test_derive_forecast_never_selects_a_night_period_even_on_a_date_match() -> None:
    today = _WINDOW.days[0].on
    periods = [_period("Tonight", f"{today.isoformat()}T18:00:00-04:00", is_daytime=False)]
    forecast = derive_forecast(_raw(periods=periods), _WINDOW, tz=_NY)
    assert forecast is None  # no daytime match for ANY target day


def test_derive_forecast_omits_a_day_with_no_matching_period_keeps_the_rest() -> None:
    # AC-2.3: a missing single day is silently omitted, never fabricated — the
    # doc still yields a Forecast for whichever days DID match.
    today = _WINDOW.days[0].on
    periods = [_period("Today", f"{today.isoformat()}T06:00:00-04:00")]
    forecast = derive_forecast(_raw(periods=periods), _WINDOW, tz=_NY)
    assert forecast is not None
    assert [d.key for d in forecast.days] == ["today"]
    assert forecast.target_key == "sat"  # target_key is unaffected by omission


def test_derive_forecast_non_fahrenheit_unit_yields_null_high() -> None:
    today = _WINDOW.days[0].on
    periods = [_period("Today", f"{today.isoformat()}T06:00:00-04:00", temp=21, unit="C")]
    forecast = derive_forecast(
        _raw(periods=periods), TargetWindow((TargetDay("today", "Today", today),), "today"), tz=_NY
    )
    assert forecast is not None
    assert forecast.days[0].high_f is None


def test_derive_forecast_missing_precip_probability_is_null_not_zero() -> None:
    today = _WINDOW.days[0].on
    periods = [_period("Today", f"{today.isoformat()}T06:00:00-04:00", pop=None)]
    forecast = derive_forecast(
        _raw(periods=periods), TargetWindow((TargetDay("today", "Today", today),), "today"), tz=_NY
    )
    assert forecast is not None
    assert forecast.days[0].precip_pct is None


# ── S3: recent precipitation ──────────────────────────────────────────────────


def _obs(hours_ago: float, mm: float | None, *, field: str = "precipitationLastHour") -> dict:
    ts = (_NOW - timedelta(hours=hours_ago)).isoformat()
    props: dict = {"timestamp": ts}
    if mm is not None:
        props[field] = {"value": mm, "unitCode": "wmoUnit:mm"}
    return props


def test_derive_recent_precip_none_when_raw_is_none_or_no_observations() -> None:
    assert derive_recent_precip(None, now=_NOW, tz=_UTC) is None
    assert derive_recent_precip(_raw(observations=None), now=_NOW, tz=_UTC) is None
    assert derive_recent_precip(_raw(observations=[]), now=_NOW, tz=_UTC) is None


def test_derive_recent_precip_no_precip_fields_at_all_is_null_never_zero_filled() -> None:
    # AC-3.1: the station answered but reports NONE of the three precip fields —
    # null, not a fabricated 0.
    observations = [{"timestamp": _NOW.isoformat()}, {"timestamp": _NOW.isoformat()}]
    assert derive_recent_precip(_raw(observations=observations), now=_NOW, tz=_UTC) is None


def test_derive_recent_precip_sums_into_the_48h_rolling_total() -> None:
    observations = [_obs(2, 12.7), _obs(50, 100.0)]  # 0.5in within 48h, the rest outside
    rp = derive_recent_precip(_raw(observations=observations), now=_NOW, tz=_UTC)
    assert rp is not None
    assert rp.total_48h_in == 0.5
    assert rp.source == "NWS observations"


def test_derive_recent_precip_display_days_are_oldest_to_today() -> None:
    rp = derive_recent_precip(_raw(observations=[_obs(1, 5.0)]), now=_NOW, tz=_UTC)
    assert rp is not None
    assert [d.label for d in rp.days] == ["Mon", "Tue", "Today"]


def test_derive_recent_precip_uses_one_consistent_field_never_mixed() -> None:
    # One observation reports precipitationLastHour, another only Last3Hours — the
    # station's Last3Hours entries are never summed alongside LastHour (double-
    # count avoidance): one field wins EXCLUSIVELY (majority-populated, finest
    # on a tie — here 1:1, so the finer LastHour).
    observations = [
        _obs(1, 25.4, field="precipitationLastHour"),  # 1.0in — counted
        _obs(2, 999.0, field="precipitationLast3Hours"),  # ignored: wrong field
    ]
    rp = derive_recent_precip(_raw(observations=observations), now=_NOW, tz=_UTC)
    assert rp is not None
    assert rp.total_48h_in == 1.0


def test_derive_recent_precip_majority_field_wins_over_a_stray_finer_reading() -> None:
    # Review finding: a single stray fine-grained reading must not discard the
    # station's DOMINANT signal — 3 of 4 observations report Last6Hours, so
    # Last6Hours wins and the real rain is counted, not the lone 0.1" LastHour.
    observations = [
        _obs(2, 12.7, field="precipitationLast6Hours"),  # 0.5in — counted
        _obs(8, 12.7, field="precipitationLast6Hours"),  # 0.5in — counted
        _obs(14, 12.7, field="precipitationLast6Hours"),  # 0.5in — counted
        _obs(1, 2.54, field="precipitationLastHour"),  # stray: ignored
    ]
    rp = derive_recent_precip(_raw(observations=observations), now=_NOW, tz=_UTC)
    assert rp is not None
    assert rp.total_48h_in == 1.5


def test_derive_recent_precip_gap_day_is_null_never_confirmed_dry() -> None:
    # Review finding: a display day with ZERO qualifying observations (station
    # outage) must read as disclosed-missing (None), never a stated "0.0 —
    # confirmed dry". Here the middle day has no observation at all.
    observations = [
        _obs(1, 12.7),  # Today: 0.5in
        _obs(50, 12.7),  # the oldest display day: 0.5in
    ]
    rp = derive_recent_precip(_raw(observations=observations), now=_NOW, tz=_UTC)
    assert rp is not None
    assert [d.amount_in for d in rp.days] == [0.5, None, 0.5]


def test_derive_recent_precip_falls_back_to_a_coarser_field_when_thats_all_the_station_has() -> (
    None
):
    observations = [_obs(1, 25.4, field="precipitationLast6Hours")]
    rp = derive_recent_precip(_raw(observations=observations), now=_NOW, tz=_UTC)
    assert rp is not None
    assert rp.total_48h_in == 1.0


def test_derive_recent_precip_unrecognized_unit_is_skipped_not_guessed() -> None:
    observations = [
        _obs(1, 25.4, field="precipitationLastHour"),  # 1.0in, a recognized unit
        {
            "timestamp": (_NOW - timedelta(hours=2)).isoformat(),
            "precipitationLastHour": {"value": 5.0, "unitCode": "wmoUnit:in"},
        },
    ]
    rp = derive_recent_precip(_raw(observations=observations), now=_NOW, tz=_UTC)
    # The field IS present (so this isn't the "no precip fields" null case, which
    # the other observation's recognized mm reading establishes) but THIS one
    # reading's unrecognized unit is skipped rather than guessed at — only the
    # 1.0in mm-unit reading counts.
    assert rp is not None
    assert rp.total_48h_in == 1.0


# ── S4: mud inference (the four named fixture scenarios) ─────────────────────


def test_mud_dry_scenario_no_block() -> None:
    rp = derive_recent_precip(_raw(observations=[_obs(1, 0.0)]), now=_NOW, tz=_UTC)
    assert rp is not None and rp.total_48h_in == 0.0
    assert derive_mud(rp, threshold_in=DEFAULT_MUD_THRESHOLD_IN) is None


def test_mud_trace_0_2in_scenario_no_block() -> None:
    rp = derive_recent_precip(_raw(observations=[_obs(1, 5.08)]), now=_NOW, tz=_UTC)  # 0.2in
    assert rp is not None and rp.total_48h_in == 0.2
    assert derive_mud(rp, threshold_in=DEFAULT_MUD_THRESHOLD_IN) is None


def test_mud_soaking_1_2in_scenario_fires_hedged_and_quantified() -> None:
    rp = derive_recent_precip(_raw(observations=[_obs(1, 30.48)]), now=_NOW, tz=_UTC)  # 1.2in
    assert rp is not None and rp.total_48h_in == 1.2
    mud = derive_mud(rp, threshold_in=DEFAULT_MUD_THRESHOLD_IN)
    assert mud is not None
    assert mud.statement == "Trails may be muddy"
    assert "may" in mud.statement.lower()
    assert mud.evidence == '1.2" of rain in the last 48h'
    assert mud.source == "NWS observations"
    assert mud.provenance == "inferred"


def test_mud_missing_data_scenario_no_block() -> None:
    # AC-4.2: an inference from ABSENT data is fabrication — missing precip data
    # (no station / no precip fields) means no mud block, never a guess.
    assert derive_mud(None, threshold_in=DEFAULT_MUD_THRESHOLD_IN) is None


def test_mud_fires_exactly_at_the_threshold_boundary() -> None:
    rp = derive_recent_precip(_raw(observations=[_obs(1, 12.7)]), now=_NOW, tz=_UTC)  # 0.5in
    assert rp is not None and rp.total_48h_in == 0.5
    assert derive_mud(rp, threshold_in=0.5) is not None  # "at/above" fires


def test_mud_threshold_is_env_tunable() -> None:
    rp = derive_recent_precip(_raw(observations=[_obs(1, 5.08)]), now=_NOW, tz=_UTC)  # 0.2in
    assert derive_mud(rp, threshold_in=0.1) is not None  # a lower operator threshold fires


def test_mud_threshold_in_env_override_and_malformed_fallback() -> None:
    assert mud_threshold_in({}) == DEFAULT_MUD_THRESHOLD_IN
    assert mud_threshold_in({"ADVENTURE_MUD_PRECIP_48H_IN": "0.75"}) == 0.75
    assert (
        mud_threshold_in({"ADVENTURE_MUD_PRECIP_48H_IN": "not-a-number"})
        == DEFAULT_MUD_THRESHOLD_IN
    )
    assert mud_threshold_in({"ADVENTURE_MUD_PRECIP_48H_IN": "-1"}) == DEFAULT_MUD_THRESHOLD_IN


# ── composition ─────────────────────────────────────────────────────────────


def test_derive_region_conditions_composes_all_three_independently() -> None:
    today = _WINDOW.days[0].on
    periods = [_period("Today", f"{today.isoformat()}T06:00:00-04:00")]
    raw = _raw(periods=periods, observations=[_obs(1, 30.48)])
    rc = derive_region_conditions(raw, when="fullDay", now=_NOW, env={})
    assert rc.forecast is not None
    assert rc.recent_precip is not None
    assert rc.mud is not None


def test_derive_region_conditions_all_null_when_raw_fetch_totally_failed() -> None:
    rc = derive_region_conditions(None, when="fullDay", now=_NOW, env={})
    assert rc.forecast is None
    assert rc.recent_precip is None
    assert rc.mud is None
