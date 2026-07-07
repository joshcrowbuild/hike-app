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
import os
import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import datetime

from orchestration.adapters.base import ConditionKind, VerifiedFact
from orchestration.present import provider_short
from orchestration.providers.base import LLMRequest, ModelProvider, _strip_fences

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
    line carries source/confidence — `text` is the cause, `source` the fact's short
    provider name (`present.provider_short`, D3 consistency pass — a warning wears
    the same calm "NWS"/"USGS" label a condition line does, never the raw
    domain-suffixed source), `observed_at` the fact's fetch timestamp. Presentation
    only: a warning never feeds ranking or confidence (Rule #2)."""

    kind: str  # ConditionKind.value the warning came from, e.g. "weather"
    text: str  # the cause alone, e.g. "weather alert: Extreme Heat Warning"
    source: str  # the fact's short provider name, e.g. "NWS"
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
                        "weather",
                        f"weather alert: {event}",
                        provider_short(weather.source),
                        weather.fetched_at,
                    )
                )

    air = facts.get(ConditionKind.air)
    if air is not None:
        aqi = _aqi(air)
        if aqi is not None and aqi >= AQI_BLOCK:
            blocks.append(BlockReason("air", f"air quality hazardous (AQI {aqi})", air.source))
        elif aqi is not None and aqi >= AQI_WARN:
            warnings.append(
                CardWarning(
                    "air",
                    f"air quality elevated (AQI {aqi})",
                    provider_short(air.source),
                    air.fetched_at,
                )
            )

    fire = facts.get(ConditionKind.fire)
    if fire is not None:
        count = _hotspots(fire)
        if count:
            warnings.append(
                CardWarning(
                    "fire",
                    f"{count} active-fire detection(s) nearby (thermal anomalies)",
                    provider_short(fire.source),
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


# ── Spatial park-boundary de-rank (Phase 2 — the durable discriminator) ──────
# The name denylist in `trail_filter` was *approximating* one question: is this way
# inside the region's protected-area boundary? Phase 2 answers it directly. A way
# whose point sits OUTSIDE the NPS/USFS polygon that defines the region, and that is
# an ambiguous foot/track way-type with no other trail signal (the "Andreae" wellness
# path, a coastal residential street posing as a footway), is likely access/
# institutional infrastructure — SOFT-demoted here, never dropped.
#
# Same #56/#75 stance as the roadlike de-rank: soft + reversible (a real trail just
# outside a boundary sinks a few slots, it does not vanish), fires only on ambiguous
# way-types, and explicitly KEEPS fire/dike/forest roads (a fire road mapped just
# outside the buffer is still a hike). The inside/outside call is the persisted
# ingest-time `outside_boundary` flag (None → unknown / no boundary → never demoted),
# so a region with no real boundary polygon degrades to today's name-only behaviour.

# Ambiguous foot/track way-types eligible for the boundary demotion. A `path` /
# `bridleway` / `steps` is a strong recreational-trail signal on its own, so it is
# never demoted on position alone — only the ambiguous `track`/`footway` middle is.
_SPATIAL_AMBIGUOUS_WAY_TYPES = frozenset({"track", "footway"})


def is_outside_boundary_demoted(
    way_type: str | None, name: str, outside_boundary: bool | None
) -> bool:
    """True if a candidate should be SOFT-demoted (never dropped) as an ambiguous way
    sitting OUTSIDE the region's protected-area boundary. `outside_boundary` is the
    persisted ingest-time classification: None (unknown / no boundary) → never demoted
    (degrade). Fires only for ambiguous `track`/`footway` way-types and never for a
    recognized fire/dike/forest road. Pure and side-effect-free."""
    if not outside_boundary:  # None or False → inside / unknown → keep
        return False
    if not way_type or way_type.lower() not in _SPATIAL_AMBIGUOUS_WAY_TYPES:
        return False
    if _FIRE_ROAD_KEEP.search(name or ""):
        return False  # fire/dike/forest road just outside the buffer — still a hike
    return True


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


# ── Corroboration rescue (Lane C — data-quality demote, default-off) ────────
# The roadlike/access and outside-boundary demotions above are OSM-tag heuristics
# (a name pattern, a boundary flag) — cheap, but occasionally wrong about a real
# trail that just happens to carry an access-y name or sit near a boundary. CDP-01
# (`graph.queries.trail_source_corroboration`) is the one place genuine multi-
# origin agreement lives: when an authoritative agency inventory (NPS/USFS/
# USGS_NTD/RIDB — a government source, not another echo of the same OSM tags)
# independently agrees the way exists, that is real corroborating evidence the
# name/boundary heuristic doesn't have.
#
# RESCUE-ONLY (Rule #2: confidence/corroboration never penalizes ranking — so it
# must never *manufacture* a demotion either): this can only LIFT a way OUT of a
# demote set some other signal already put it in. A way that isn't demoted is
# never touched here, and a single-source way (corroboration == 1, or every
# distinct source is non-authoritative) is never rescued — the original heuristic
# stands because there's no independent evidence to override it with.
#
# Default OFF (`ADVENTURE_CORROBORATION_RESCUE`) — first cut from the 2026-07
# spike, not yet bake-off validated.

CORROBORATION_RESCUE_ENV = "ADVENTURE_CORROBORATION_RESCUE"

# Government/agency inventories — genuine independent agreement. OSM (and any
# non-agency echo) doesn't count: two OSM-derived records agreeing is still one
# origin's tagging, not cross-source corroboration (the "authoritative coverage
# present" gate — a region with no agency ingest at all can never clear this,
# however many times a way is counted).
_AUTHORITATIVE_SOURCES = frozenset({"nps", "usfs", "usgs_ntd", "usgs-ntd", "ridb"})

# Below this distinct-origin count, there's no second opinion to rescue with —
# corroboration == 1 means the demoted way's own OSM tags are the only evidence
# either way, so the heuristic that demoted it stands.
_MIN_RESCUE_CORROBORATION = 2


def corroboration_rescue_enabled(env: Mapping[str, str] | None = None) -> bool:
    """True when the corroboration-rescue mechanism is switched on. Default OFF —
    an unset or unrecognized value degrades to off, never silently on (a bad knob
    must never turn on an unvalidated rescue path)."""
    e = os.environ if env is None else env
    raw = (e.get(CORROBORATION_RESCUE_ENV) or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def is_corroboration_rescued(
    name: str,
    *,
    sources: Collection[str] = (),
    corroboration: int = 1,
) -> bool:
    """True if a way already in a demote set should be RESCUED back to normal
    position. Never a reason to demote on its own (Rule #2) — this predicate only
    answers "does this one need rescuing", for a caller to apply against an
    existing demote set. Carries the same fire/dike/forest-road guard as the
    demote checks above (belt-and-suspenders: those already never reach the
    demote set, but a rescue predicate must never treat a legit fire road as
    needing a corroboration gate either). Requires BOTH real multi-origin
    agreement (>= `_MIN_RESCUE_CORROBORATION` distinct origins) AND at least one
    of them authoritative — a cluster of OSM-only echoes never clears this."""
    if _FIRE_ROAD_KEEP.search(name or ""):
        return True  # fire/dike/forest road — never gated on corroboration
    if corroboration < _MIN_RESCUE_CORROBORATION:
        return False
    normalized = {s.strip().lower() for s in sources if isinstance(s, str)}
    return bool(normalized & _AUTHORITATIVE_SOURCES)


def apply_corroboration_rescue(
    demote_ids: Collection[str],
    names: Mapping[str, str],
    *,
    corroboration: Mapping[str, int] | None = None,
    sources: Mapping[str, Collection[str]] | None = None,
    enabled: bool,
) -> set[str]:
    """Rescue-only pass over an already-computed demote set. Can only REMOVE ids
    from `demote_ids`; never adds one — a way no other signal demoted is never
    touched (Rule #2). A no-op (returns `demote_ids` unchanged) when `enabled` is
    False, so the default-off flag is a single, obvious branch rather than
    threaded through every call site."""
    demoted = set(demote_ids)
    if not enabled or not demoted:
        return demoted
    corroboration = corroboration or {}
    sources = sources or {}
    return {
        cid
        for cid in demoted
        if not is_corroboration_rescued(
            names.get(cid, ""),
            sources=sources.get(cid, ()),
            corroboration=corroboration.get(cid, 1),
        )
    }


# ── Length de-rank (intent.filters.max_length_mi) ────────────────────────────
# The mechanical-tier parser (orchestration/intent.py) extracts a hiker's requested
# max trail length from free text ("something under 8 miles"), but the engine used
# to discard `Intent.filters` entirely after parsing. Same soft-demotion discipline
# as the roadlike/boundary de-ranks above (Rule #2 — demote, never hard-drop): a
# trail over budget sinks below the rest, it is never dropped — still worth
# showing, just not first.


def valid_max_length_mi(value: object) -> float | None:
    """Validate an intent-filter max_length_mi value: a positive real number, not a
    bool (JSON booleans are also ints in Python — `isinstance(True, int)` is True).
    Any other shape (missing, string, negative, zero, list) degrades to None — no
    filter applied — rather than raising, since this reads a mechanical-tier LLM's
    parsed JSON (a malformed model output must no-op, never crash)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if value > 0 else None


def is_over_length_demoted(length_mi: float | None, max_length_mi: float | None) -> bool:
    """True if a candidate should be SOFT-demoted (never dropped) for exceeding the
    hiker's requested max_length_mi. No filter set, or an unknown candidate
    `length_mi` (a corpus that hasn't backfilled the field yet), never demotes —
    absence of data is not evidence a trail is too long (mirrors AC-5.3's "absence
    of a drive time is never treated as far")."""
    if max_length_mi is None or length_mi is None:
        return False
    return length_mi > max_length_mi


# ── Preference hints (dog / difficulty) — soft, until real graph props exist ──
# Neither `dog` (dog-friendliness) nor `difficulty` is a persisted corpus property
# yet — no ingest source populates them — so there is nothing to filter or demote
# per-candidate against. Until that lands, both ride as a documented hint in the
# judge's free-text profile: a soft nudge the judgment-tier ranker can weigh,
# never a hard drop (Rule #2) and never dressed up as a verified fact (Rule #1 in
# spirit — the hint is honest about being an unverified preference).

_KNOWN_DIFFICULTIES = frozenset({"easy", "moderate", "hard", "strenuous"})


def filter_preference_hints(filters: Mapping[str, object]) -> str | None:
    """Build a hint string from `intent.filters` (dog / difficulty) for the judge's
    profile text. Validates each value (dog: bool; difficulty: one of
    `_KNOWN_DIFFICULTIES`, case-insensitive) and silently omits anything malformed
    — a bad LLM-parsed filter value no-ops rather than crashing or misleading the
    judge. Returns None when neither filter is present/valid."""
    parts: list[str] = []
    dog = filters.get("dog")
    if isinstance(dog, bool):
        parts.append("dog-friendly trail preferred" if dog else "hiker is not bringing a dog")
    difficulty = filters.get("difficulty")
    if isinstance(difficulty, str) and difficulty.strip().lower() in _KNOWN_DIFFICULTIES:
        parts.append(f"preferred difficulty: {difficulty.strip().lower()}")
    if not parts:
        return None
    return (
        "Soft preference (not yet a verified corpus property — weigh gently, "
        "never as a hard requirement): " + "; ".join(parts)
    )


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
    corroboration: Mapping[str, int] | None = None,
    corroboration_sources: Mapping[str, Collection[str]] | None = None,
) -> list[str]:
    """Ask the judgment-tier model to order candidate (canonical_id, name) pairs.
    `hints` surfaces a per-candidate ordering input (e.g. drive minutes) into the
    payload — an explicit, legible ranking term, never a confidence input (rule #2).
    `demote_ids` (roadlike/access ways — see `is_roadlike_demoted`) are stably sunk
    below the rest of the order afterward: a transparent, reversible feed-quality
    demotion, never a drop. `corroboration`/`corroboration_sources` (CDP-01
    distinct-origin counts + names, keyed by canonical_id) feed the rescue-only
    pass (`apply_corroboration_rescue`, default OFF) that can lift a demoted way
    back out when it's genuinely corroborated by an authoritative source — it
    never adds a demotion of its own."""
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
    rescued_demote_ids = apply_corroboration_rescue(
        demote_ids,
        dict(items),
        corroboration=corroboration,
        sources=corroboration_sources,
        enabled=corroboration_rescue_enabled(),
    )
    return _apply_demotion(ordered, rescued_demote_ids)
