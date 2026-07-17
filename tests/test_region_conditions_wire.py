"""Wire-shape tests for region_conditions + warning severity + the `when` request
field (frame-conditions-wave §5, epic-054 S1/S2/S5) — the api.app <-> api.schemas
seam. `_region_conditions_response` is exercised with the REAL
`orchestration.region_conditions` dataclasses (exactly the shape
`engine.Feed.region_conditions`/`two_phase.ConditionsPatch.region_conditions`
carry), never a parallel duck-typed fake.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

import api.app as app_mod
from api.schemas import CardWarningResponse, PlanConditionsRequest, PlanRequest
from orchestration.region_conditions import (
    Forecast,
    ForecastDay,
    Mud,
    RecentPrecip,
    RecentPrecipDay,
    RegionConditions,
)

# ── api.app._region_conditions_response ────────────────────────────────────


def test_region_conditions_response_none_in_none_out() -> None:
    # AC-5.1: "not attempted this phase" stays a bare absent field.
    assert app_mod._region_conditions_response(None) is None


def test_region_conditions_response_all_null_members_round_trip() -> None:
    rc = RegionConditions(forecast=None, recent_precip=None, mud=None)
    out = app_mod._region_conditions_response(rc)
    assert out is not None
    assert out.forecast is None
    assert out.recent_precip is None
    assert out.mud is None


def test_region_conditions_response_forecast_shape() -> None:
    fetched_at = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
    rc = RegionConditions(
        forecast=Forecast(
            days=(
                ForecastDay(key="today", label="Today", high_f=88, precip_pct=0, short="Sunny"),
                ForecastDay(key="sat", label="Sat", high_f=68, precip_pct=20, short="Partly sunny"),
            ),
            target_key="sat",
            source="NWS",
            fetched_at=fetched_at,
        ),
        recent_precip=None,
        mud=None,
    )
    out = app_mod._region_conditions_response(rc)
    assert out is not None
    assert out.forecast is not None
    assert out.forecast.target_key == "sat"
    assert out.forecast.source == "NWS"
    assert out.forecast.fetched_at == fetched_at.isoformat()
    assert [d.key for d in out.forecast.days] == ["today", "sat"]
    assert out.forecast.days[0].high_f == 88
    assert out.forecast.days[1].precip_pct == 20


def test_region_conditions_response_recent_precip_and_mud_shape() -> None:
    rc = RegionConditions(
        forecast=None,
        recent_precip=RecentPrecip(
            days=(
                RecentPrecipDay(label="Thu", amount_in=0.8),
                RecentPrecipDay(label="Today", amount_in=0.0),
            ),
            total_48h_in=1.2,
            source="NWS observations",
        ),
        mud=Mud(
            statement="Trails may be muddy",
            evidence='1.2" of rain in the last 48h',
            source="NWS observations",
            provenance="inferred",
        ),
    )
    out = app_mod._region_conditions_response(rc)
    assert out is not None
    assert out.recent_precip is not None
    assert [d.label for d in out.recent_precip.days] == ["Thu", "Today"]
    assert out.recent_precip.total_48h_in == 1.2
    assert out.mud is not None
    assert out.mud.statement == "Trails may be muddy"
    assert out.mud.provenance == "inferred"


# ── PlanRequest / PlanConditionsRequest.when ────────────────────────────────


@pytest.mark.parametrize(
    "when", ["tomorrowMorning", "weekendMorning", "weekendAfternoon", "fullDay", None]
)
def test_plan_request_accepts_known_when_values(when: str | None) -> None:
    body = PlanRequest(query="q", lat=38.5, lon=-78.4, when=when)
    assert body.when == when


def test_plan_request_when_defaults_to_none() -> None:
    assert PlanRequest(query="q", lat=38.5, lon=-78.4).when is None


def test_plan_request_rejects_unknown_when_value() -> None:
    with pytest.raises(ValidationError):
        PlanRequest(query="q", lat=38.5, lon=-78.4, when="nextTuesday")


def test_plan_conditions_request_accepts_when() -> None:
    body = PlanConditionsRequest(
        query="q", lat=38.5, lon=-78.4, canonical_ids=["ct:a"], when="weekendMorning"
    )
    assert body.when == "weekendMorning"


# ── CardWarningResponse.severity ────────────────────────────────────────────


def test_card_warning_response_severity_defaults_to_heads_up() -> None:
    w = CardWarningResponse(
        text="t", source="s", observed_at="2026-07-15T00:00:00Z", kind="weather"
    )
    assert w.severity == "heads_up"


def test_card_warning_response_accepts_blocked() -> None:
    w = CardWarningResponse(
        text="t",
        source="s",
        observed_at="2026-07-15T00:00:00Z",
        kind="closures",
        severity="blocked",
    )
    assert w.severity == "blocked"
