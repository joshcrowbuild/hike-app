"""Templated hedged phrasing — the Verifier's deterministic presentation baseline.

Renders a verified fact into a sourced, confidence-hedged feed line. This is the
templated side of the Stage-4 §9 open question (templated vs. LLM phrasing): cheap,
deterministic, and the comparison point for the bake-off. Honesty over polish —
every line names its source and wears its confidence (stated / hedged / flagged).
Deep presentation / UX is Stage 10.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from orchestration.adapters.base import VerifiedFact
from orchestration.confidence import Confidence

log = logging.getLogger(__name__)

_HEDGE = {"stated": "", "hedged": "Likely: ", "flagged": "Unverified: "}

# A neutral placeholder for a fact shape `_body` cannot honestly render (Epic 046
# S2, B6): an unhandled `kind` or a non-dict value is a shape violation, not
# content to pass through raw — `str(value)` on either can leak a Python dict/list
# repr or the literal word "None" to a user. Logged at the boundary (fail loud,
# CLAUDE.md); never `None`, never a repr (degrade gracefully at the surface).
_PLACEHOLDER = "unavailable"


@dataclass(frozen=True)
class FeedLine:
    kind: str
    # Back-compat / non-Detail rendering (Epic 046 S1 AC-1.1): `body` + the short
    # provider name + `age`, welded into one glanceable string — unchanged in
    # content from before this split, so `RecommendationCard`'s single "Now" line
    # and the metrics token estimate (`api/app.py`) keep reading it verbatim. Never
    # a second composition: always `f"{body} · {provider_short}, {age}"` below.
    text: str
    # The hedge + value alone — no source, no age (Epic 046 S1). This is the fact
    # a per-kind Detail row (or any other structured surface) should render as
    # "the value"; a surface that welds its own source/age onto `body` would
    # regrow the A3 defect this split exists to fix.
    body: str
    source: str
    # Freshness alone, in plain words ("just now", "10m ago") — the same string
    # `_age()` bakes into `text`, exposed separately so a surface can state it
    # once at block scope instead of once per fact (Epic 046 S1 AC-1.4).
    age: str
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


def pluralize(count: int, singular: str, plural: str | None = None) -> str:
    """The grammatically correct noun for `count` — never the degenerate literal
    `(s)` that ships regardless of count (Epic 046 S2, B1/B2/B3). Shared with
    `curator.py` (same import as `provider_short`) so a card warning's
    fire-detection count and a condition line's facility/alert count resolve
    through one pluralization rule, not two."""
    return singular if count == 1 else (plural or f"{singular}s")


def _nonneg_int(raw: Any) -> int:
    """A count-shaped field as a real non-negative int — 0 for anything else
    (missing, `None`, bool, negative, or malformed). Mirrors the `park` guard
    (B3): a key that is *present but null* must not reach an f-string as the
    literal word "None" either."""
    return raw if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 0 else 0


# Qualifiers that separate a USGS station's recognizable stream/river name from its
# locational suffix ("HAWKSBILL CREEK NEAR LURAY, VA" — the part after "NEAR" is
# where, not what). Matched case-insensitively; real station names are ALL CAPS.
_GAUGE_QUALIFIER = re.compile(r"\b(NEAR|AT|ABOVE|BELOW)\b", re.IGNORECASE)


def _gauge_label(raw_name: object) -> str:
    """The recognizable stream/river name from a USGS station's full label (B7) —
    "HAWKSBILL CREEK NEAR LURAY, VA" -> "Hawksbill Creek": title-cased and
    truncated to what a hiker recognizes, never the full ALL-CAPS official string
    (which wraps two lines at phone width — sweep §5) and never a raw station id.
    Empty, missing, or non-string input yields "" — the caller falls back to the
    honest "the nearest gauge", never `None` or a raw repr."""
    if not isinstance(raw_name, str) or not raw_name.strip():
        return ""
    head = raw_name.split(",", 1)[0]
    qualifier = _GAUGE_QUALIFIER.search(head)
    if qualifier:
        head = head[: qualifier.start()]
    head = head.strip()
    return head.title() if head else ""


def _body(kind: str, value: Any) -> str:
    if not isinstance(value, dict):
        # B6: a non-dict fact value is a shape violation (every adapter returns a
        # dict), not content to pass through raw — `str(value)` can render a bare
        # `None`, or a list/tuple repr. Fail loud (logged) + neutral placeholder.
        log.warning(
            "present._body: non-dict fact value for kind=%r (type=%s)", kind, type(value).__name__
        )
        return _PLACEHOLDER
    if kind == "weather":
        temp = value.get("temperature")
        unit = value.get("temperature_unit") or "F"  # B5: default unit, never a bare "°"
        forecast = value.get("short_forecast")
        parts = [forecast] if isinstance(forecast, str) and forecast.strip() else []
        if temp is not None:
            parts.append(f"{temp}°{unit}")
        # B5: never the literal word "forecast" standing in for a missing sky
        # reading. When there is truly nothing to say, disclose that plainly
        # rather than fabricate a placeholder that reads as a value.
        return " ".join(parts) if parts else _PLACEHOLDER
    if kind == "air":
        aqi = value.get("aqi")
        if aqi is None:
            # Real AirNow facts always carry aqi (airnow.py guards it at the
            # source) — guarded here too so a malformed value can never render
            # the literal "AQI None".
            return f"AQI {_PLACEHOLDER}"
        category = value.get("category")
        # B4: drop the parenthetical entirely when category is falsy —
        # "AQI 45", never "AQI 45 (None)".
        return f"AQI {aqi} ({category})" if category else f"AQI {aqi}"
    if kind == "fire":
        count = _nonneg_int(value.get("hotspot_count"))
        return f"{count} active-fire {pluralize(count, 'detection', 'detections')} nearby"
    if kind == "water":
        cfs = value.get("latest_discharge_cfs")
        label = _gauge_label(value.get("monitoring_location"))
        gauge = f"{label} gauge" if label else "the nearest gauge"
        if isinstance(cfs, (int, float)):
            # B7: answer the actual hiker question (how much water is flowing),
            # never the bare ALL-CAPS station name or numeric id.
            return f"~{cfs:.0f} cfs at {gauge}"
        # The reading itself didn't come back (site known or not) — still never
        # the bare name/id and never `None`. The point-to-gauge distance is a
        # separate honest hedge USGS's own adapter already discloses
        # (`fact.disclosures`, relocated onto `ConditionStatus.detail` at
        # engine.py:745 — Rule #1: relocated, not dropped). `_body` only ever
        # sees `value`, which carries no numeric distance field of its own, so
        # re-deriving one here would mean regex-parsing another module's prose
        # sentence rather than rendering a real value — deliberately not done.
        return f"flow reading unavailable at {gauge}"
    if kind == "permits":
        count = _nonneg_int(value.get("count"))
        # B8: RIDB lists nearby facilities only — nothing in this value dict
        # answers "do I need a permit" (the adapter's own disclosure: "Live
        # permit/campsite availability uses a separate unofficial endpoint; not
        # included"). Counting facilities as if that answered the permit
        # question is exactly the leak B8 flagged. The structural fix is
        # engine.py's CDP-02 not_fetched/no_data disposition
        # (`_condition_summary` / `_is_coverage_gap`), which lives outside this
        # story's file scope (present.py/curator.py only) — so the honest
        # option available here is to say plainly what was and wasn't checked,
        # rather than a ✓-sourced line that implies an answer this data can't
        # support (Rule #1: disclose, don't imply; binding decision 4).
        facility_word = pluralize(count, "facility", "facilities")
        return f"Permit info not fetched — {count} nearby {facility_word}"
    if kind == "closures":
        count = _nonneg_int(value.get("count"))
        # B3: `.get("park", default)` only applies when the key is ABSENT; NPS
        # sets `"park": full_name` where `full_name` can be present-but-None —
        # `or` catches that too, never leaking the literal "None".
        park = value.get("park") or "the nearest park"
        alert_word = pluralize(count, "alert", "alerts")
        return f"{count} NPS closure/danger {alert_word} — {park}"
    if kind == "drive_time":
        secs = value.get("drive_seconds")
        km = value.get("distance_km")
        mins = f"~{secs / 60:.0f} min drive" if isinstance(secs, (int, float)) else "drive time"
        return f"{mins} ({km:.0f} km)" if isinstance(km, (int, float)) else mins
    # B6: an unhandled kind with a dict value — `str(value)` here is exactly the
    # raw `{'foo': 'bar'}` repr leak the finding named. Fail loud + placeholder.
    log.warning("present._body: unhandled kind=%r", kind)
    return _PLACEHOLDER


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
    if kind == "closures":
        park_code = value.get("park_code")
        return f"NPS {park_code}" if park_code else ""
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
    # `body` is the hedge + value only — never a source or an age welded on
    # (Epic 046 S1 / A3: that weld is exactly why no downstream surface could
    # relocate or collapse either one). `age` is the same freshness `_age()` has
    # always produced, now also exposed on its own.
    body = f"{hedge}{_body(kind, fact.value)}"
    age = _age(fact.fetched_at, now)
    # The calm line keeps only what a person reads at a glance — the value, a
    # recognizable source name, and its freshness ("Sunny 96°F · NWS, just now").
    # The raw grid/station codes and the single-source honesty descriptor move to
    # `source` (rendered in the detail Sources section), so the feed line stays
    # legible without dropping any provenance (source-or-silence, just relocated).
    # Kept derived from `body`/`age` below (never a second composition) purely for
    # back-compat callers that still want one welded string (see `FeedLine.text`).
    text = f"{body} · {provider_short(fact.source)}, {age}"
    source = f"{fact.source} · {_source_note(kind, fact.value)}"
    return FeedLine(
        kind=kind,
        text=text,
        body=body,
        source=source,
        age=age,
        presentation=confidence.presentation,
        sources=(provider_short(fact.source),),
    )
