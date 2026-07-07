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
    # Distinct live-source names backing this fact (Epic 026a). Live conditions are
    # single-source by construction (CDP-01: genuine multi-origin corroboration lives
    # only on the corpus SAME_AS layer, never a live fact — engine.py's
    # `PlannedTrail.corpus_corroboration`), so this is always a 1-tuple today. Carried
    # honestly rather than fabricated so a later UI cue never implies corroboration a
    # live fact doesn't have (Rule #2/#11).
    sources: tuple[str, ...] = ()


def _age(fetched_at: datetime, now: datetime) -> str:
    """Freshness in plain words. Sub-minute reads as "just now" rather than the
    machine-flavored "0m ago" — the line is copy a person reads at a glance."""
    secs = max(0, int((now - fetched_at).total_seconds()))
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86_400:
        return f"{secs // 3600}h ago"
    return f"{secs // 86_400}d ago"


def provider_short(source: str) -> str:
    """The recognizable short name for a source label — the leading token of the
    adapter's own source label ("NWS api.weather.gov" → "NWS", "USGS Water Data
    (…)" → "USGS"). Derived from the real source, never fabricated; the full label
    and origin ids live in `FeedLine.source` (the detail Sources section). Shared
    with `curator.py`/`engine.py` so a card warning or a set-aside reason wears the
    same short provider name a condition line does — one source-shortening rule,
    not two (D3 consistency pass)."""
    parts = source.split()
    return parts[0] if parts else source


def _body(kind: str, value: Any) -> str:
    if not isinstance(value, dict):
        return str(value)
    if kind == "weather":
        temp = value.get("temperature")
        unit = value.get("temperature_unit") or ""
        forecast = value.get("short_forecast") or "forecast"
        return f"{forecast} {temp}°{unit}" if temp is not None else str(forecast)
    if kind == "air":
        return f"AQI {value.get('aqi')} ({value.get('category')})"
    if kind == "fire":
        return f"{value.get('hotspot_count', 0)} active-fire detection(s) nearby"
    if kind == "water":
        return f"nearest gauge: {value.get('monitoring_location') or value.get('site_id')}"
    if kind == "permits":
        return f"{value.get('count', 0)} nearby facilities"
    if kind == "drive_time":
        secs = value.get("drive_seconds")
        km = value.get("distance_km")
        mins = f"~{secs / 60:.0f} min drive" if isinstance(secs, (int, float)) else "drive time"
        return f"{mins} ({km:.0f} km)" if isinstance(km, (int, float)) else mins
    return str(value)


# Kinds whose provider is an *aggregator* of upstream monitors (AirNow pools EPA
# stations) — labeled "aggregated" so we never imply independent corroboration where a
# single feed already merged its inputs (CDP-01 spike: AirNow corroboration = 1).
_AGGREGATOR_KINDS = frozenset({"air"})


def _origin(kind: str, value: Any) -> str:
    """The recoverable distinct-origin id for a live single-source fact (CDP-01 spike
    item 2 / CDP-03 origin-at-boundary). Empty when no id is captured — we name the
    origin where we have it, never fabricate one. These ids are what a future second
    provider for the same kind would be checked against for genuine independence."""
    if not isinstance(value, dict):
        return ""
    if kind == "water":
        sid = value.get("site_id")
        return f"USGS site {sid}" if sid else ""
    if kind == "weather":
        office = value.get("forecast_office")
        gx, gy = value.get("grid_x"), value.get("grid_y")
        if office and gx is not None and gy is not None:
            return f"NWS {office} {gx},{gy}"
        return f"NWS {office}" if office else ""
    if kind == "fire":
        sats = [s for s in (value.get("satellites") or []) if isinstance(s, str)]
        return f"FIRMS {'/'.join(sats)}" if sats else ""
    # permits (RIDB → Recreation.gov) is a single federal origin — corroboration moot
    # (spike). No origin id is emitted: it would only restate the provider already in the
    # source-parens, never serve as an independence key.
    return ""


def _source_note(kind: str, value: Any) -> str:
    """Honest single-source label: live conditions come from exactly one source by
    construction, so we say so (and name the origin) rather than leaving the corroboration
    axis to imply more than one (CDP-01 spike item 2). Corroboration >1 lives only on the
    corpus layer (PlannedTrail.corpus_*), never on a live fact."""
    descriptor = (
        "single aggregated source" if kind in _AGGREGATOR_KINDS else "single authoritative source"
    )
    origin = _origin(kind, value)
    return f"{descriptor} ({origin})" if origin else descriptor


def summarize_fact(
    kind: str, fact: VerifiedFact, confidence: Confidence, *, now: datetime | None = None
) -> FeedLine:
    now = now or datetime.now(timezone.utc)
    hedge = _HEDGE.get(confidence.presentation, "")
    body = _body(kind, fact.value)
    # The calm line keeps only what a person reads at a glance — the value, a
    # recognizable source name, and its freshness ("Sunny 96°F · NWS, just now").
    # The raw grid/station codes and the single-source honesty descriptor move to
    # `source` (rendered in the detail Sources section), so the feed line stays
    # legible without dropping any provenance (source-or-silence, just relocated).
    text = f"{hedge}{body} · {provider_short(fact.source)}, {_age(fact.fetched_at, now)}"
    source = f"{fact.source} · {_source_note(kind, fact.value)}"
    return FeedLine(
        kind=kind,
        text=text,
        source=source,
        presentation=confidence.presentation,
        sources=(_provider_short(fact.source),),
    )
