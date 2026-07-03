"""Curator — the deterministic guardrail half (Stage 4 §6).

The split (revised 2026-07-02, after a weather-probe outage blanked the feed
everywhere — rule #6: live conditions are enrichment, never a dependency):

  * A VERIFIED hazard — an alert carried by a live fact with source + timestamp —
    SHOWS on the card as a prominent, source-stamped warning. It never hides the
    trail: a safety flag is presentation, and it never feeds ranking (rule #2).
  * An UNVERIFIABLE required condition — a weather probe that failed, or an alerts
    sub-call that failed — STAYS a normal card, carrying a disclosed, source-honest
    "conditions unavailable" note (source-or-silence, rule #1: a failed probe is
    unknown, never "no alerts" — but unknown is disclosed, not hidden; rule #6: an
    outage must never blank the feed).
  * Non-weather hard thresholds (hazardous AQI) keep their block semantics — the
    one class of *verified* hard-block left. Set-aside is reserved for those.

Blocks are hard filters, not soft scores; confidence never penalizes ranking
(rule #2) — guardrails are about safety and legality, not uncertainty.

Thresholds are module constants so they're easy to tune against real conditions.
"""

from __future__ import annotations

import json
import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import datetime

from orchestration.adapters.base import ConditionKind, VerifiedFact
from orchestration.providers.base import LLMRequest, ModelProvider

AQI_BLOCK = 201  # "Very Unhealthy" and above
AQI_WARN = 101  # "Unhealthy for Sensitive Groups" and above


@dataclass(frozen=True)
class BlockReason:
    """A single hard-block cause, source-stamped (Epic 018 S5 AC-5.1). The `reason`
    is the cause on its own ("weather alert: Flash Flood Warning"); `source` is the
    live fact's provenance ("NWS api.weather.gov") so a set-aside trail can be
    disclosed with its cause AND source (AC-5.2), never dropped without a trace. A
    block is a *safety* gate — it carries no confidence/ranking signal (Rule #2)."""

    kind: str  # ConditionKind.value the block came from, e.g. "weather"
    reason: str  # the cause alone, e.g. "air quality hazardous (AQI 250)"
    source: str  # the blocking fact's provenance, e.g. "AirNow"


@dataclass(frozen=True)
class ConditionUnavailable:
    """One condition that could not be verified — the trail STAYS in the feed as a
    normal card carrying this disclosure (decision of 2026-07-02, rule #6: live
    conditions are enrichment, never a dependency; an outage must never blank the
    feed). `reason` is the cause alone ("weather couldn't be verified"); `source` is
    the honest provenance for the gap ("no source responded", or the fact's own
    source when only its alerts sub-call failed). Never reads as "clear" (rule #1) —
    it discloses unknown. Presentation only: never feeds ranking (Rule #2)."""

    kind: str  # ConditionKind.value the gap came from, e.g. "weather"
    reason: str  # the cause alone, e.g. "weather couldn't be verified"
    source: str  # honest provenance for the gap, e.g. "no source responded"


@dataclass(frozen=True)
class CardWarning:
    """One prominent, source-stamped warning a card wears (decision of 2026-07-01):
    a VERIFIED hazard shows on the trail's card, never hides it. Mirrors how a feed
    line carries source/confidence — `text` is the cause, `source` the live fact's
    provenance, `observed_at` the fact's fetch timestamp. Presentation only: a
    warning never feeds ranking or confidence (Rule #2)."""

    kind: str  # ConditionKind.value the warning came from, e.g. "weather"
    text: str  # the cause alone, e.g. "weather alert: Extreme Heat Warning"
    source: str  # the fact's provenance, e.g. "NWS api.weather.gov"
    observed_at: datetime  # when the fact was fetched (the alert's observation time)


@dataclass(frozen=True)
class GuardrailVerdict:
    blocked: bool
    blocks: tuple[BlockReason, ...] = ()
    warnings: tuple[CardWarning, ...] = ()
    # Conditions that couldn't be verified — disclosed on the card, never a reason to
    # set the trail aside (decision of 2026-07-02; rule #6).
    unavailable: tuple[ConditionUnavailable, ...] = ()


def _alerts(fact: VerifiedFact) -> list[str] | None:
    """Active-alert events on a weather fact — or None when the alert state is
    UNKNOWN. The NWS adapter writes `active_alerts: None` when the alerts sub-call
    failed while the forecast succeeded; None means "couldn't verify", never "no
    alerts" (rule #1) — the caller must hold the trail back, not pass it clean.
    A fact that doesn't carry the key at all is silent on alerts (an adapter that
    doesn't probe them) and contributes no alert signal either way."""
    value = fact.value
    if not isinstance(value, dict) or "active_alerts" not in value:
        return []
    alerts = value["active_alerts"]
    if alerts is None:
        return None  # unknown — the alerts sub-call failed
    return [a for a in alerts if isinstance(a, str)]


def _aqi(fact: VerifiedFact) -> int | None:
    value = fact.value
    aqi = value.get("aqi") if isinstance(value, dict) else None
    # AirNow sometimes returns AQI as float; int() is safe and preferred for comparison.
    if isinstance(aqi, (int, float)) and not isinstance(aqi, bool):
        return int(aqi)
    return None


def _hotspots(fact: VerifiedFact) -> int:
    value = fact.value
    count = value.get("hotspot_count") if isinstance(value, dict) else None
    return count if isinstance(count, int) else 0


def evaluate_guardrails(
    facts: Mapping[ConditionKind, VerifiedFact],
    *,
    probed_kinds: Collection[ConditionKind] = (),
) -> GuardrailVerdict:
    """The verified-vs-unverifiable split (revised 2026-07-02). `probed_kinds` names
    the kinds the Verifier actually attempted, so a weather probe that failed
    outright (probed, no fact) is distinguishable from weather simply not being
    probed in this deployment — only the former is an unverifiable required
    condition, and it now STAYS a card with disclosure rather than blocking
    (rule #6: enrichment, never a dependency — an outage must never blank the
    feed)."""
    blocks: list[BlockReason] = []
    warnings: list[CardWarning] = []
    unavailable: list[ConditionUnavailable] = []

    weather = facts.get(ConditionKind.weather)
    if weather is None:
        if ConditionKind.weather in probed_kinds:
            # Weather was probed and no source answered: the alert state is
            # unverifiable. Disclosed on the card, never set aside — a failed probe
            # never reads as clear (rule #1), but unknown is not a hard block (#6).
            unavailable.append(
                ConditionUnavailable(
                    "weather", "weather couldn't be verified", "no source responded"
                )
            )
    else:
        alerts = _alerts(weather)
        if alerts is None:
            # Forecast answered but the alerts sub-call failed → unknown, not clear —
            # disclosed, not blocked (same rationale as the failed-probe case above).
            unavailable.append(
                ConditionUnavailable(
                    "weather", "weather alerts couldn't be verified", weather.source
                )
            )
        else:
            # NWS returns overlapping issuances of the same event as separate
            # features (seen live 2026-07-02: the Extreme Heat Warning twice per
            # point) — dedupe so a card never wears the same warning twice.
            for event in dict.fromkeys(alerts):
                # A VERIFIED active alert shows ON the card, prominently — it never
                # hides the trail (decision of 2026-07-01; safety is presentation,
                # never a ranking penalty — rule #2).
                warnings.append(
                    CardWarning(
                        "weather", f"weather alert: {event}", weather.source, weather.fetched_at
                    )
                )

    air = facts.get(ConditionKind.air)
    if air is not None:
        aqi = _aqi(air)
        if aqi is not None and aqi >= AQI_BLOCK:
            blocks.append(BlockReason("air", f"air quality hazardous (AQI {aqi})", air.source))
        elif aqi is not None and aqi >= AQI_WARN:
            warnings.append(
                CardWarning("air", f"air quality elevated (AQI {aqi})", air.source, air.fetched_at)
            )

    fire = facts.get(ConditionKind.fire)
    if fire is not None:
        count = _hotspots(fire)
        if count:
            warnings.append(
                CardWarning(
                    "fire",
                    f"{count} active-fire detection(s) nearby (thermal anomalies)",
                    fire.source,
                    fire.fetched_at,
                )
            )

    return GuardrailVerdict(
        blocked=bool(blocks),
        blocks=tuple(blocks),
        warnings=tuple(warnings),
        unavailable=tuple(unavailable),
    )


# ── Way-type de-rank (feed quality — persisted OSM way-type) ─────────────────
# The Overpass spine query pulls path|footway|track|bridleway|steps, and the
# fetch-time `trail_filter` already HARD-DROPS clear non-trails (sidewalks, private
# drives, numbered TIGER routes, coastal residential street-suffixes). What still
# leaks into the feed is the ambiguous middle: an access/service/maintenance road
# tagged `highway=track` that poses as a hike. This is a SOFT, reversible demotion
# in ranking (never a drop — the trail stays in the feed, just below real trails),
# so it can't silently hide a mis-classified real trail the way a hard filter would.
#
# Same care as #56 / #75: it fires ONLY on roadlike way-types and ONLY when the name
# carries a positive access/service signal, and it explicitly KEEPS fire / dike /
# forest roads (legit hikes that happen to be `track`s). A genuine footpath
# (`path`/`footway`/`bridleway`/`steps`) is never demoted on this signal, whatever
# its name.

# Way-types that are ROADS, not foot trails. Only these are eligible for the name-
# keyed access demotion (a `service`/`residential`/`unclassified` value can't arrive
# from today's Overpass query, but keeping them here makes the rule forward-safe if
# the fetch filter widens).
_ROADLIKE_WAY_TYPES = frozenset(
    {"track", "service", "road", "residential", "unclassified", "service_road"}
)

# Positive access/service/connector name signals — a roadlike way named this way is
# infrastructure, not a hike. Kept tight (precision over recall, like trail_filter):
# a false demote only sinks a real trail a few slots, but we still don't want it.
_ACCESS_NAME = re.compile(
    r"\b(access|service|maintenance|utility|utilities|connector|"
    r"parking|driveway|gate|pipeline|powerline|substation|reservoir access)\b",
    re.I,
)

# Fire / dike / forest / gravel roads ARE legit hikes — keep them even though they
# are `track`s and even if they'd otherwise match an access word. Explicit markers
# win; a bare "…Road"/"…Rd" ending also keeps (matches the #75 "keep fire roads"
# stance: "Salt Pond Road", "Compton Gap Road", "Mathews Arm Road" are real).
_FIRE_ROAD_KEEP = re.compile(
    r"\b(fire\s?road|fire\s?rd|dike|levee|forest\s?(road|route|service\s?road)|"
    r"fs\s?rd|f\.?r\.?\s?\d)\b|\b(road|rd)\s*$",
    re.I,
)


def is_roadlike_demoted(way_type: str | None, name: str) -> bool:
    """True if a candidate should be SOFT-demoted in the feed as a roadlike/access
    way (never dropped). Fires only for roadlike `way_type`s carrying an access/
    service name signal, and never for a recognized fire/dike/forest road. Pure and
    side-effect-free so it's unit-testable against real names."""
    if not way_type or way_type.lower() not in _ROADLIKE_WAY_TYPES:
        return False
    text = name or ""
    if _FIRE_ROAD_KEEP.search(text):
        return False  # legit fire/dike/forest road — keep it in normal position
    return bool(_ACCESS_NAME.search(text))


# ── Taste ranking (judgment tier, via the provider seam) ────────────────────
# The soft half of the Curator. Confidence is deliberately NOT an input here —
# uncertainty must never penalize ranking (rule #2). Works on (id, name) pairs so
# it doesn't import the engine (no cycle). Prompt is a thin v0; real tuning is the
# Stage-4 build / bake-off.

RANK_SYSTEM = (
    "You are a calm hiking concierge. Given candidate trails, return ONLY a JSON "
    "array of their canonical_id strings, ordered best-first for this hiker. "
    "No prose, no markdown — just the JSON array."
)


def _strip_fences(text: str) -> str:
    """Remove markdown code fences that models sometimes add despite instructions."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1])
    return text.strip()


def _parse_ids(text: str, known: list[str]) -> list[str]:
    """Parse the judge's JSON ordering; keep known ids, append any it dropped,
    fall back to input order on any malformed output (graceful degradation)."""
    try:
        data = json.loads(_strip_fences(text))
    except (ValueError, TypeError):
        return list(known)
    if not isinstance(data, list):
        return list(known)
    ordered = [x for x in data if isinstance(x, str) and x in known]
    seen = dict.fromkeys(ordered)  # de-dupe, preserve order
    for cid in known:
        seen.setdefault(cid, None)  # append ids the judge dropped
    return list(seen)


def _apply_demotion(ordered: list[str], demote_ids: Collection[str]) -> list[str]:
    """Stable-partition a ranked id list so demoted ids sink below the rest while
    both groups keep their relative taste order. A soft, reversible move — nothing
    is dropped (the demoted trail still rides the feed, just lower)."""
    if not demote_ids:
        return ordered
    demote = set(demote_ids)
    kept = [cid for cid in ordered if cid not in demote]
    sunk = [cid for cid in ordered if cid in demote]
    return kept + sunk


def rank_ids(
    items: list[tuple[str, str]],
    provider: ModelProvider,
    model: str,
    *,
    profile: str | None = None,
    hints: dict[str, str] | None = None,
    demote_ids: Collection[str] = (),
) -> list[str]:
    """Ask the judgment-tier model to order candidate (canonical_id, name) pairs.
    `hints` surfaces a per-candidate ordering input (e.g. drive minutes) into the
    payload — an explicit, legible ranking term, never a confidence input (rule #2).
    `demote_ids` (roadlike/access ways — see `is_roadlike_demoted`) are stably sunk
    below the rest of the order afterward: a transparent, reversible feed-quality
    demotion, never a drop."""
    if not items:
        return []
    known = [cid for cid, _ in items]
    hints = hints or {}
    listing = "\n".join(
        f"- {cid}: {name}" + (f" ({hints[cid]})" if cid in hints else "") for cid, name in items
    )
    user = f"Candidates:\n{listing}"
    if profile:
        user += f"\n\nHiker preferences: {profile}"
    request = LLMRequest(
        system=RANK_SYSTEM,
        messages=[{"role": "user", "content": user}],
        model=model,
        max_tokens=512,
    )
    ordered = _parse_ids(provider.complete(request).text, known)
    return _apply_demotion(ordered, demote_ids)
