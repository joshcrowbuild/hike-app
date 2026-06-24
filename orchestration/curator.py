"""Curator — the deterministic guardrail half (Stage 4 §6).

Constraints are hard filters, not soft scores: a guardrail block removes a trail
from the feed regardless of how good it otherwise is. This is distinct from
confidence, which never penalizes ranking (rule #2) — guardrails are about safety
and legality, not uncertainty. The taste / novelty / party ranking (the
judgment-tier LLM half) is separate and lands later.

Thresholds are module constants so they're easy to tune against real conditions.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass

from orchestration.adapters.base import VerifiedFact
from orchestration.providers.base import LLMRequest, ModelProvider

# Active-alert events that hard-block (substring match, case-insensitive).
BLOCKING_ALERT_KEYWORDS = ("flash flood", "red flag", "tornado", "extreme", "evacuation")
AQI_BLOCK = 201  # "Very Unhealthy" and above
AQI_WARN = 101  # "Unhealthy for Sensitive Groups" and above


@dataclass(frozen=True)
class GuardrailVerdict:
    blocked: bool
    blocks: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def _alerts(fact: VerifiedFact) -> list[str]:
    value = fact.value
    if isinstance(value, dict):
        # active_alerts is None when the NWS alerts sub-call fails (alerts endpoint
        # failure while forecast succeeded). None means "unknown", not "empty list".
        # We must not iterate over None — treat it the same as an absent key.
        alerts = value.get("active_alerts") or []
        return [a for a in alerts if isinstance(a, str)]
    return []


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


def evaluate_guardrails(facts: Mapping[str, VerifiedFact]) -> GuardrailVerdict:
    blocks: list[str] = []
    warnings: list[str] = []

    weather = facts.get("weather")
    if weather is not None:
        for event in _alerts(weather):
            if any(kw in event.lower() for kw in BLOCKING_ALERT_KEYWORDS):
                blocks.append(f"weather alert: {event}")
            else:
                warnings.append(f"weather alert: {event}")

    air = facts.get("air")
    if air is not None:
        aqi = _aqi(air)
        if aqi is not None and aqi >= AQI_BLOCK:
            blocks.append(f"air quality hazardous (AQI {aqi})")
        elif aqi is not None and aqi >= AQI_WARN:
            warnings.append(f"air quality elevated (AQI {aqi})")

    fire = facts.get("fire")
    if fire is not None:
        count = _hotspots(fire)
        if count:
            warnings.append(f"{count} active-fire detection(s) nearby (thermal anomalies)")

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
) -> list[str]:
    """Ask the judgment-tier model to order candidate (canonical_id, name) pairs."""
    if not items:
        return []
    known = [cid for cid, _ in items]
    listing = "\n".join(f"- {cid}: {name}" for cid, name in items)
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
