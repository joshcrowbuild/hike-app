"""Role -> tier -> provider resolution, with data-sensitivity routing.

Encodes the Stage 4 §2 policy:
  * Two capability tiers: `mechanical` (extract / normalize) and `judgment`
    (judge / curate).
  * Default local; cloud (Anthropic) is opt-in per tier via config.
  * Sensitivity routing (mirrors Decision Log §13): any prompt touching the
    private overlay is forced to the local provider so personal data never leaves
    the machine — regardless of the tier's default provider.

This is wiring, not domain logic: it selects an adapter + model id. The actual
prompts/parsing land in Stage 4.
"""

from __future__ import annotations

from dataclasses import dataclass

from orchestration.config import Settings

from .anthropic_claude import AnthropicProvider
from .base import ModelProvider
from .local_openai import LocalOpenAIProvider

# Which capability tier each engine role draws from.
ROLE_TIER: dict[str, str] = {
    "extract": "mechanical",  # Scout: parse free-text intent
    "normalize": "mechanical",  # Verifier: hedge + phrase verified facts
    "judge": "judgment",  # Eval: truthfulness LLM-judge
    "curate": "judgment",  # Curator: taste / novelty / party ranking
}


@dataclass(frozen=True)
class Resolution:
    provider: ModelProvider
    provider_name: str
    model: str
    forced_local: bool


def _build(provider_name: str, settings: Settings) -> ModelProvider:
    if provider_name == "local":
        return LocalOpenAIProvider(base_url=settings.local_openai_base_url)
    if provider_name == "anthropic":
        return AnthropicProvider(api_key=settings.anthropic_api_key)
    raise ValueError(f"unknown provider: {provider_name!r}")


def resolve(role: str, settings: Settings, *, touches_private_overlay: bool = False) -> Resolution:
    if role not in ROLE_TIER:
        raise ValueError(f"unknown role: {role!r}")
    tier = settings.tiers[ROLE_TIER[role]]
    if touches_private_overlay and tier.provider != "local":
        # Sensitivity routing: keep private-overlay reasoning on-device.
        return Resolution(_build("local", settings), "local", tier.local_model, True)
    return Resolution(_build(tier.provider, settings), tier.provider, tier.model, False)
