"""Curator — the deterministic guardrail half (Stage 4 §6).

The split (decided by Josh, 2026-07-01, after the Extreme Heat Warning dogfood):

  * A VERIFIED hazard — an alert carried by a live fact with source + timestamp —
    SHOWS on the card as a prominent, source-stamped warning. It never hides the
    trail: a safety flag is presentation, and it never feeds ranking (rule #2).
  * An UNVERIFIABLE required condition — a weather probe that failed, or an alerts
    sub-call that failed — holds the trail back (set aside) WITH disclosure
    (source-or-silence, rule #1: a failed probe is unknown, never "no alerts").
  * Non-weather hard thresholds (hazardous AQI) keep their block semantics.

Blocks are hard filters, not soft scores; confidence never penalizes ranking
(rule #2) — guardrails are about safety and legality, not uncertainty.

Thresholds are module constants so they're easy to tune against real conditions.
"""

from __future__ import annotations

import json
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
    """The verified-vs-unverifiable split (2026-07-01). `probed_kinds` names the
    kinds the Verifier actually attempted, so a weather probe that failed outright
    (probed, no fact) is distinguishable from weather simply not being probed in
    this deployment — only the former is an unverifiable required condition."""
    blocks: list[BlockReason] = []
    warnings: list[CardWarning] = []

    weather = facts.get(ConditionKind.weather)
    if weather is None:
        if ConditionKind.weather in probed_kinds:
            # Weather was probed and no source answered: the alert state is
            # unverifiable, and an unverifiable required condition holds the trail
            # back with disclosure — a failed probe never reads as clear (rule #1).
            blocks.append(
                BlockReason("weather", "weather couldn't be verified", "no source responded")
            )
    else:
        alerts = _alerts(weather)
        if alerts is None:
            # Forecast answered but the alerts sub-call failed → unknown, not clear.
            blocks.append(
                BlockReason("weather", "weather alerts couldn't be verified", weather.source)
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

    return GuardrailVerdict(blocked=bool(blocks), blocks=tuple(blocks), warnings=tuple(warnings))


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


def rank_ids(
    items: list[tuple[str, str]],
    provider: ModelProvider,
    model: str,
    *,
    profile: str | None = None,
    hints: dict[str, str] | None = None,
) -> list[str]:
    """Ask the judgment-tier model to order candidate (canonical_id, name) pairs.
    `hints` surfaces a per-candidate ordering input (e.g. drive minutes) into the
    payload — an explicit, legible ranking term, never a confidence input (rule #2)."""
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
    return _parse_ids(provider.complete(request).text, known)
