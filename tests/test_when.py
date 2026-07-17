"""Frame-date derivation tests (frame-conditions-wave §1 Q18, epic-054 S2 AC-2.1).

Reference dates (2026, verified by weekday below): Mon 2026-07-13, Wed
2026-07-15, Sat 2026-07-18, Sun 2026-07-19 — one calendar week spanning both
weekday and weekend `now` anchors.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from orchestration.when import (
    DEFAULT_REGION_TZ,
    derive_target_window,
    region_timezone,
)

_UTC = timezone.utc
_MON = date(2026, 7, 13)
_WED = date(2026, 7, 15)
_SAT = date(2026, 7, 18)
_SUN = date(2026, 7, 19)
_NY = ZoneInfo("America/New_York")


def test_reference_dates_are_the_expected_weekdays() -> None:
    assert _MON.weekday() == 0
    assert _WED.weekday() == 2
    assert _SAT.weekday() == 5
    assert _SUN.weekday() == 6


def _now(d: date, hour: int = 12) -> datetime:
    return datetime(d.year, d.month, d.day, hour, tzinfo=_UTC)


def test_tomorrow_morning_targets_tomorrow() -> None:
    w = derive_target_window("tomorrowMorning", now=_now(_WED), tz=_UTC)
    assert w.target_key == "tomorrow"
    assert [(d.key, d.on) for d in w.days] == [
        ("today", _WED),
        ("tomorrow", date(2026, 7, 16)),
    ]


def test_weekend_morning_from_a_weekday_targets_the_coming_saturday() -> None:
    w = derive_target_window("weekendMorning", now=_now(_MON), tz=_UTC)
    assert w.target_key == "sat"
    assert [(d.key, d.on) for d in w.days] == [
        ("today", _MON),
        ("sat", _SAT),
        ("sun", _SUN),
    ]


def test_weekend_afternoon_behaves_identically_to_weekend_morning() -> None:
    w = derive_target_window("weekendAfternoon", now=_now(_MON), tz=_UTC)
    assert w.target_key == "sat"
    assert [d.on for d in w.days] == [_MON, _SAT, _SUN]


def test_weekend_morning_from_saturday_targets_this_saturday() -> None:
    # "if today is Sat, this weekend; target sat" — the coming weekend collapses
    # to today's own weekend rather than jumping a week ahead.
    w = derive_target_window("weekendMorning", now=_now(_SAT), tz=_UTC)
    assert w.target_key == "sat"
    assert [(d.key, d.on) for d in w.days] == [
        ("today", _SAT),
        ("sat", _SAT),
        ("sun", _SUN),
    ]


def test_weekend_morning_from_sunday_targets_sunday_once_saturday_has_passed() -> None:
    w = derive_target_window("weekendMorning", now=_now(_SUN), tz=_UTC)
    assert w.target_key == "sun"
    assert [(d.key, d.on) for d in w.days] == [
        ("today", _SUN),
        ("sat", _SAT),  # yesterday — already passed
        ("sun", _SUN),
    ]


def test_full_day_targets_today_over_the_same_weekend_window() -> None:
    w = derive_target_window("fullDay", now=_now(_MON), tz=_UTC)
    assert w.target_key == "today"
    assert [(d.key, d.on) for d in w.days] == [
        ("today", _MON),
        ("sat", _SAT),
        ("sun", _SUN),
    ]


def test_missing_when_degrades_to_full_days_window() -> None:
    assert derive_target_window(None, now=_now(_MON), tz=_UTC) == derive_target_window(
        "fullDay", now=_now(_MON), tz=_UTC
    )


def test_unrecognized_when_degrades_to_full_days_window_never_a_crash() -> None:
    assert derive_target_window("nonsense", now=_now(_MON), tz=_UTC) == derive_target_window(
        "fullDay", now=_now(_MON), tz=_UTC
    )


def test_day_labels_are_presentation_ready() -> None:
    w = derive_target_window("weekendMorning", now=_now(_MON), tz=_UTC)
    assert [d.label for d in w.days] == ["Today", "Sat", "Sun"]


def test_target_window_respects_region_local_tz_not_utc_date() -> None:
    # 2026-07-15 02:00 UTC is still 2026-07-14 22:00 EDT (UTC-4 in July) — "today"
    # must be the REGION-local calendar day, not the UTC one.
    now = datetime(2026, 7, 15, 2, 0, tzinfo=_UTC)
    w = derive_target_window("tomorrowMorning", now=now, tz=_NY)
    assert w.days[0].on == date(2026, 7, 14)
    assert w.days[1].on == date(2026, 7, 15)


def test_region_timezone_defaults_to_america_new_york() -> None:
    assert region_timezone({}) == ZoneInfo(DEFAULT_REGION_TZ)


def test_region_timezone_honors_env_override() -> None:
    assert region_timezone({"ADVENTURE_REGION_TZ": "America/Los_Angeles"}) == ZoneInfo(
        "America/Los_Angeles"
    )


def test_region_timezone_blank_env_degrades_to_default() -> None:
    assert region_timezone({"ADVENTURE_REGION_TZ": "  "}) == ZoneInfo(DEFAULT_REGION_TZ)


def test_region_timezone_unknown_zone_degrades_to_default_never_raises() -> None:
    assert region_timezone({"ADVENTURE_REGION_TZ": "Not/AZone"}) == ZoneInfo(DEFAULT_REGION_TZ)
