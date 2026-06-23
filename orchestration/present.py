"""Templated hedged phrasing — the Verifier's deterministic presentation baseline.

Renders a verified fact into a sourced, confidence-hedged feed line. This is the
templated side of the Stage-4 §9 open question (templated vs. LLM phrasing): cheap,
deterministic, and the comparison point for the bake-off. Honesty over polish —
every line names its source and wears its confidence (stated / hedged / flagged).
Deep presentation / UX is Stage 10.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from orchestration.adapters.base import VerifiedFact
from orchestration.confidence import Confidence

_HEDGE = {"stated": "", "hedged": "Likely: ", "flagged": "Unverified: "}


@dataclass(frozen=True)
class FeedLine:
    kind: str
    text: str
    source: str
    presentation: str


def _age(fetched_at: datetime, now: datetime) -> str:
    secs = max(0, int((now - fetched_at).total_seconds()))
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86_400:
        return f"{secs // 3600}h ago"
    return f"{secs // 86_400}d ago"


def _body(kind: str, value: Any) -> str:
    if not isinstance(value, dict):
        return str(value)
    if kind == "weather":
        temp = value.get("temperature")
        unit = value.get("temperature_unit") or ""
        forecast = value.get("short_forecast") or "forecast"
        return f"{forecast}, {temp}°{unit}" if temp is not None else str(forecast)
    if kind == "air":
        return f"AQI {value.get('aqi')} ({value.get('category')})"
    if kind == "fire":
        return f"{value.get('hotspot_count', 0)} active-fire detection(s) nearby"
    if kind == "water":
        return f"nearest gauge: {value.get('monitoring_location') or value.get('site_id')}"
    if kind == "permits":
        return f"{value.get('count', 0)} nearby facilities"
    return str(value)


def summarize_fact(
    kind: str, fact: VerifiedFact, confidence: Confidence, *, now: datetime | None = None
) -> FeedLine:
    now = now or datetime.now(timezone.utc)
    hedge = _HEDGE.get(confidence.presentation, "")
    text = f"{hedge}{_body(kind, fact.value)} ({fact.source}, {_age(fact.fetched_at, now)})"
    return FeedLine(kind=kind, text=text, source=fact.source, presentation=confidence.presentation)
