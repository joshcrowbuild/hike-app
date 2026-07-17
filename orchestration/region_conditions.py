"""Region-conditions derivation (frame-conditions-wave §5, epic-054 S2-S4).

Turns the RAW region-level NWS fetch (`adapters.nws.fetch_region_raw` — the full
forecast periods list + recent station observations, cached once per plan at the
query origin) into the three wire-facing pieces: the frame-aligned forecast, the
recent-precipitation reveal, and the hedged mud inference. Deliberately split
from the fetch (`orchestration.adapters.nws`) and from render (`engine._render_
feed`): the raw fetch is `when`-independent and TTL-cached: the day-of-week
selection done here is cheap, pure, and re-run on every render against
serve-time `now` (the `feed_card`/`_condition_summary` discipline) — never baked
into what gets cached, so a repeat within the TTL is reused regardless of which
day a later request's frame targets.

Every piece degrades independently and silently on missing data (source-or-
silence, rule #1): a station lookup failing costs `recent_precip`/`mud`, never
`forecast`, and vice versa.
"""

from __future__ import annotations

import logging
import math
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from orchestration.adapters.base import VerifiedFact
from orchestration.when import WEEKDAY_LABELS, TargetWindow, derive_target_window, region_timezone

log = logging.getLogger(__name__)

FORECAST_SOURCE = "NWS"
PRECIP_SOURCE = "NWS observations"

MUD_THRESHOLD_ENV = "ADVENTURE_MUD_PRECIP_48H_IN"
DEFAULT_MUD_THRESHOLD_IN = 0.5

# Display window for the "Past 3 days" reveal (frame-conditions-wave §3.4) —
# distinct from `_TOTAL_WINDOW_HOURS`, the ROLLING 48h sum the mud rule gates on.
_RECENT_PRECIP_DISPLAY_DAYS = 3
_TOTAL_WINDOW_HOURS = 48

# NWS station observations report precip over one of these accumulation windows,
# never all consistently — the field actually populated varies by station. Tried
# in this order (finest first) and, once one is found ANYWHERE in the fetched
# window, used EXCLUSIVELY for every observation (never mixed) so a day's total
# is never double-counted across overlapping accumulation windows.
_PRECIP_FIELDS = ("precipitationLastHour", "precipitationLast3Hours", "precipitationLast6Hours")


@dataclass(frozen=True)
class ForecastDay:
    key: str
    label: str
    high_f: int | None
    precip_pct: int | None
    short: str | None


@dataclass(frozen=True)
class Forecast:
    days: tuple[ForecastDay, ...]
    target_key: str
    source: str
    fetched_at: datetime


@dataclass(frozen=True)
class RecentPrecipDay:
    label: str
    amount_in: float | None


@dataclass(frozen=True)
class RecentPrecip:
    days: tuple[RecentPrecipDay, ...]
    total_48h_in: float | None
    source: str


@dataclass(frozen=True)
class Mud:
    statement: str
    evidence: str
    source: str
    provenance: str = "inferred"


@dataclass(frozen=True)
class RegionConditions:
    forecast: Forecast | None
    recent_precip: RecentPrecip | None
    mud: Mud | None


def mud_threshold_in(env: Mapping[str, str] | None = None) -> float:
    """The rolling-48h rain total (inches) at/above which the mud inference fires
    (default 0.5", env `ADVENTURE_MUD_PRECIP_48H_IN` — S4 AC-4.3). A malformed or
    negative override degrades to the default rather than crashing or disabling
    the rule outright."""
    e = os.environ if env is None else env
    raw = e.get(MUD_THRESHOLD_ENV)
    if raw is None:
        return DEFAULT_MUD_THRESHOLD_IN
    try:
        value = float(raw)
    except ValueError:
        log.warning(
            "%s=%r is not a number; using default %s",
            MUD_THRESHOLD_ENV,
            raw,
            DEFAULT_MUD_THRESHOLD_IN,
        )
        return DEFAULT_MUD_THRESHOLD_IN
    if not math.isfinite(value) or value < 0:
        log.warning(
            "%s=%r is not a finite non-negative number; using default %s",
            MUD_THRESHOLD_ENV,
            raw,
            DEFAULT_MUD_THRESHOLD_IN,
        )
        return DEFAULT_MUD_THRESHOLD_IN
    return value


# ── forecast (S2) ─────────────────────────────────────────────────────────────


def _parse_iso(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _period_date(period: Mapping[str, Any], tz: ZoneInfo) -> date | None:
    dt = _parse_iso(period.get("startTime"))
    return dt.astimezone(tz).date() if dt is not None else None


def _match_period(periods: list[Any], target: date, tz: ZoneInfo) -> Mapping[str, Any] | None:
    for period in periods:
        if not isinstance(period, dict):
            continue
        if period.get("isDaytime") is not True:
            continue
        if _period_date(period, tz) == target:
            return period
    return None


def _temperature_f(period: Mapping[str, Any]) -> int | None:
    temp = period.get("temperature")
    if (
        isinstance(temp, (int, float))
        and not isinstance(temp, bool)
        and period.get("temperatureUnit") == "F"
    ):
        return int(temp)
    return None


def _precip_pct(period: Mapping[str, Any]) -> int | None:
    entry = period.get("probabilityOfPrecipitation")
    if isinstance(entry, dict):
        value = entry.get("value")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return int(value)
    return None


def _short_forecast(period: Mapping[str, Any]) -> str | None:
    short = period.get("shortForecast")
    return short if isinstance(short, str) and short.strip() else None


def derive_forecast(
    raw: VerifiedFact | None, window: TargetWindow, *, tz: ZoneInfo
) -> Forecast | None:
    """S2 AC-2.2/2.3: select the daytime period matching each target day from the
    ALREADY-FETCHED periods list — no new NWS calls. The whole doc unavailable
    (`raw` is None, or carries no periods) -> `None`; a single day with no
    matching period is silently omitted, never fabricated."""
    if raw is None or not isinstance(raw.value, dict):
        return None
    periods = raw.value.get("periods")
    if not isinstance(periods, list) or not periods:
        return None
    days = tuple(
        ForecastDay(
            key=td.key,
            label=td.label,
            high_f=_temperature_f(period),
            precip_pct=_precip_pct(period),
            short=_short_forecast(period),
        )
        for td in window.days
        if (period := _match_period(periods, td.on, tz)) is not None
    )
    if not days:
        return None
    return Forecast(
        days=days, target_key=window.target_key, source=FORECAST_SOURCE, fetched_at=raw.fetched_at
    )


# ── recent precipitation (S3) ─────────────────────────────────────────────────


def _to_inches(value: float, unit_code: object) -> float | None:
    """NWS precip observations arrive in SI units (`wmoUnit:mm` typically, `wmoUnit:m`
    on some stations); an unrecognized unit is skipped rather than guessed at
    (source-or-silence — a wrong conversion is worse than a missing reading)."""
    if unit_code in ("wmoUnit:mm", "mm"):
        return value / 25.4
    if unit_code in ("wmoUnit:m", "m"):
        return (value * 1000) / 25.4
    return None


def _obs_amount(obs: Mapping[str, Any], field: str) -> float | None:
    entry = obs.get(field)
    if not isinstance(entry, dict):
        return None
    value = entry.get("value")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    return _to_inches(value, entry.get("unitCode"))


def _station_precip_field(observations: Sequence[Mapping[str, Any]]) -> str | None:
    """The one accumulation field this station's fetched observations actually
    populate, finest-first — `None` when NONE of them ever carry ANY of the
    three (S3 AC-3.1: "the station reports no precip fields" -> null, never
    zero-filled)."""
    for field in _PRECIP_FIELDS:
        if any(_obs_amount(obs, field) is not None for obs in observations):
            return field
    return None


def derive_recent_precip(
    raw: VerifiedFact | None, *, now: datetime, tz: ZoneInfo
) -> RecentPrecip | None:
    """S3: per-day rain for the display window (oldest -> Today) + the rolling
    48h total the mud rule (S4) gates on. `None` when there's no station, the
    fetch failed, or the station never reports a precip field at all — the
    per-day/total split still degrades together (both come from the same
    observation set) since a station that reports nothing has nothing honest
    to show either way."""
    if raw is None or not isinstance(raw.value, dict):
        return None
    observations = raw.value.get("observations")
    if not isinstance(observations, list):
        return None
    valid = [o for o in observations if isinstance(o, dict)]
    if not valid:
        return None
    field = _station_precip_field(valid)
    if field is None:
        return None

    today = now.astimezone(tz).date()
    display_dates = [
        today - timedelta(days=offset) for offset in range(_RECENT_PRECIP_DISPLAY_DAYS - 1, -1, -1)
    ]
    buckets: dict[date, float] = dict.fromkeys(display_dates, 0.0)
    cutoff = now - timedelta(hours=_TOTAL_WINDOW_HOURS)
    total_48h = 0.0
    for obs in valid:
        observed_at = _parse_iso(obs.get("timestamp"))
        if observed_at is None:
            continue
        amount = _obs_amount(obs, field)
        if amount is None:
            continue
        local_date = observed_at.astimezone(tz).date()
        if local_date in buckets:
            buckets[local_date] += amount
        if cutoff <= observed_at <= now:
            total_48h += amount

    days = tuple(
        RecentPrecipDay(
            label="Today" if d == today else WEEKDAY_LABELS[d.weekday()],
            amount_in=round(buckets[d], 1),
        )
        for d in display_dates
    )
    return RecentPrecip(days=days, total_48h_in=round(total_48h, 1), source=PRECIP_SOURCE)


# ── mud inference (S4) ─────────────────────────────────────────────────────────


def derive_mud(recent_precip: RecentPrecip | None, *, threshold_in: float) -> Mud | None:
    """S4: a hedged, quantified, `inferred`-tagged mud read when the rolling 48h
    total clears the threshold. AC-4.2: missing precip data -> no mud block — an
    inference from absent data is fabrication, never a guess."""
    if recent_precip is None or recent_precip.total_48h_in is None:
        return None
    if recent_precip.total_48h_in < threshold_in:
        return None
    return Mud(
        statement="Trails may be muddy",
        evidence=f'{recent_precip.total_48h_in:.1f}" of rain in the last 48h',
        source=PRECIP_SOURCE,
        provenance="inferred",
    )


# ── composition ─────────────────────────────────────────────────────────────


def derive_region_conditions(
    raw: VerifiedFact | None,
    *,
    when: str | None,
    now: datetime,
    env: Mapping[str, str] | None = None,
) -> RegionConditions:
    """The full region-conditions triple for one render. Each piece is
    independently nullable (S2/S3/S4); the caller (`engine._render_feed`,
    `two_phase._patch_from_plan`/`_patch_from_graph`) decides whether to emit
    this object at all — `None` at the TOP level means "not attempted this
    phase" (e.g. a phase-1 shell), distinct from "attempted, degraded", which
    is this object with one or more null members."""
    tz = region_timezone(env)
    window: TargetWindow = derive_target_window(when, now=now, tz=tz)
    forecast = derive_forecast(raw, window, tz=tz)
    recent_precip = derive_recent_precip(raw, now=now, tz=tz)
    mud = derive_mud(recent_precip, threshold_in=mud_threshold_in(env))
    return RegionConditions(forecast=forecast, recent_precip=recent_precip, mud=mud)
