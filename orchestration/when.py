"""Frame-date derivation (frame-conditions-wave §1 Q18, epic-054 S2 AC-2.1).

Turns the tuning frame's `when` key ("tomorrowMorning" | "weekendMorning" |
"weekendAfternoon" | "fullDay") into the calendar days the region-level weather
forecast should cover, and which one the frame targets. Pure date math over an
injected `now` — this module never reads the wall clock itself, so a caller
(`engine._render_feed`, mirroring `feed_card`'s `render_now` pattern) is what
makes date-dependent behavior deterministic under test.

`region_timezone` mirrors `curator.corroboration_rescue_enabled`'s env-read
idiom (a small, directly-tunable knob, not threaded through `Settings`).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

log = logging.getLogger(__name__)

REGION_TZ_ENV = "ADVENTURE_REGION_TZ"
DEFAULT_REGION_TZ = "America/New_York"

WEEKDAY_LABELS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


@dataclass(frozen=True)
class TargetDay:
    """One day in the forecast window: a stable toggle `key`, a presentation-
    ready `label` ("Today"/"Sat"), and the actual calendar date it resolves to
    (region-local) — used to match an NWS forecast period, never shown raw."""

    key: str
    label: str
    on: date


@dataclass(frozen=True)
class TargetWindow:
    days: tuple[TargetDay, ...]
    target_key: str


def region_timezone(env: Mapping[str, str] | None = None) -> ZoneInfo:
    """The region-local tz for "today"/weekend math (default `America/New_York`,
    per env `ADVENTURE_REGION_TZ`). An unset or unrecognized zone name degrades to
    the default rather than raising — a bad knob must never crash date derivation."""
    e = os.environ if env is None else env
    name = (e.get(REGION_TZ_ENV) or "").strip() or DEFAULT_REGION_TZ
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        log.warning(
            "%s=%r is not a known IANA zone; using default %s",
            REGION_TZ_ENV,
            name,
            DEFAULT_REGION_TZ,
        )
        return ZoneInfo(DEFAULT_REGION_TZ)


def _weekend_dates(today: date) -> tuple[date, date]:
    """The Saturday/Sunday of "the coming weekend": if `today` is already Sat or
    Sun, that weekend (already arrived) — Sunday's Saturday is yesterday, so a
    caller can tell "Saturday has passed" from `sat < today`; otherwise the next
    Sat/Sun ahead."""
    weekday = today.weekday()  # Mon=0 .. Sun=6
    if weekday >= 5:
        sat = today - timedelta(days=weekday - 5)
    else:
        sat = today + timedelta(days=5 - weekday)
    return sat, sat + timedelta(days=1)


def derive_target_window(when: str | None, *, now: datetime, tz: ZoneInfo) -> TargetWindow:
    """The frame's forecast window + which day it targets (epic-054 S2 AC-2.1):

      tomorrowMorning              -> [today, tomorrow], target tomorrow
      weekendMorning/Afternoon     -> [today, sat, sun] of the coming weekend,
                                       target sat (or sun once sat has passed)
      fullDay / absent / unknown   -> [today, sat, sun], target today

    An absent or unrecognized `when` degrades to `fullDay`'s window rather than
    guessing a specific day — a documented default, never a fabricated frame."""
    today = now.astimezone(tz).date()
    days: tuple[TargetDay, ...]
    if when == "tomorrowMorning":
        tomorrow = today + timedelta(days=1)
        days = (
            TargetDay("today", "Today", today),
            TargetDay("tomorrow", "Tomorrow", tomorrow),
        )
        return TargetWindow(days, "tomorrow")

    sat, sun = _weekend_dates(today)
    days = (
        TargetDay("today", "Today", today),
        TargetDay("sat", WEEKDAY_LABELS[5], sat),
        TargetDay("sun", WEEKDAY_LABELS[6], sun),
    )
    if when in ("weekendMorning", "weekendAfternoon"):
        target = "sat" if sat >= today else "sun"
        return TargetWindow(days, target)
    return TargetWindow(days, "today")
