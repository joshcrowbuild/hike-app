"""Intent parsing — mechanical-tier free-text -> structured query (Stage 4 §3).

Turns "a chill dog-friendly loop near me this weekend" into structured filters + a
profile string for the taste ranker. Mechanical tier (cheap/local). Robust: any
malformed model output yields an empty Intent (the engine falls back to defaults),
never a crash. Real prompt tuning is the Stage-4 build.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from orchestration.providers.base import LLMRequest, ModelProvider

PARSE_SYSTEM = (
    "Extract a hiking query into a JSON object with optional keys: "
    '"radius_m" (int drive radius in metres), "filters" (object, e.g. '
    '{"dog": true, "max_length_mi": 8, "difficulty": "easy"}), and "profile" '
    "(a short string of preferences for ranking). Return ONLY the JSON object."
)


@dataclass(frozen=True)
class Intent:
    radius_m: int | None = None
    filters: dict[str, object] = field(default_factory=dict)
    profile: str | None = None


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1])
    return text.strip()


def _parse(text: str) -> Intent:
    try:
        data = json.loads(_strip_fences(text))
    except (ValueError, TypeError):
        return Intent()
    if not isinstance(data, dict):
        return Intent()
    radius = data.get("radius_m")
    filters = data.get("filters")
    profile = data.get("profile")
    return Intent(
        radius_m=radius if isinstance(radius, int) and not isinstance(radius, bool) else None,
        filters=filters if isinstance(filters, dict) else {},
        profile=profile if isinstance(profile, str) else None,
    )


def parse_intent(query: str, provider: ModelProvider, model: str) -> Intent:
    if not query or not query.strip():
        return Intent()  # empty query → default intent; don't waste an LLM call
    request = LLMRequest(
        system=PARSE_SYSTEM,
        messages=[{"role": "user", "content": query}],
        model=model,
        max_tokens=256,
    )
    return _parse(provider.complete(request).text)
