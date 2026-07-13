"""Role -> tier -> provider resolution, with data-sensitivity routing.

Encodes the Stage 4 §2 policy:
  * Two capability tiers: `mechanical` (extract / normalize) and `judgment`
    (judge / curate).
  * Default local; cloud (Anthropic) is opt-in per tier via config.
  * Optional per-role overrides (Epic 040 operator-lever seam) layer on top of
    the tier, field by field, via `Settings.role_overrides` — e.g.
    `ADVENTURE_MODEL_CURATE` pins curate to a cheaper/faster model without
    moving judge off the judgment tier's shared model. Unset roles/fields
    resolve exactly as tier-only resolution always did.
  * Sensitivity routing (mirrors Decision Log §13): any prompt touching the
    private overlay is forced to the local provider so personal data never leaves
    the machine — regardless of the effective (tier-or-override) provider.

This is wiring, not domain logic: it selects an adapter + model id. The actual
prompts/parsing land in Stage 4.
"""

from __future__ import annotations

from dataclasses import dataclass

from orchestration.config import RoleOverride, Settings

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
    """Resolve `role` to a provider adapter + model.

    Per-role env overrides (`ADVENTURE_{PROVIDER,MODEL,LOCAL_MODEL}_<ROLE>`, e.g.
    `ADVENTURE_MODEL_CURATE`) layer on top of the role's tier config, field by
    field: an override wins for the field it sets, an unset field falls through
    to the tier's value — so overriding curate's model never touches judge's
    model even though both share the judgment tier (Epic 040 operator-lever
    seam). This is resolved into a single effective (provider, model,
    local_model) view FIRST; sensitivity routing below then runs against that
    effective view exactly as it always ran against the raw tier — so a role
    override that points at a cloud provider is still forced local when
    `touches_private_overlay=True`, using the effective local_model (role
    override if set, else the tier's). A cloud override can never defeat
    privacy routing.
    """
    if role not in ROLE_TIER:
        raise ValueError(f"unknown role: {role!r}")
    tier = settings.tiers[ROLE_TIER[role]]
    override = settings.role_overrides.get(role, RoleOverride())
    provider_name = override.provider or tier.provider
    model = override.model or tier.model
    local_model = override.local_model or tier.local_model
    if touches_private_overlay and provider_name != "local":
        # Sensitivity routing: keep private-overlay reasoning on-device.
        effective_local = local_model or model  # fall back to cloud model id if local unset
        if not effective_local:
            raise ValueError(
                f"Sensitivity routing forced local for role {role!r} but neither "
                "local_model nor model is configured — set ADVENTURE_LOCAL_MODEL_* in .env"
            )
        return Resolution(_build("local", settings), "local", effective_local, True)
    if touches_private_overlay:
        # Already local — forced_local=True so callers know privacy routing applied.
        return Resolution(_build(provider_name, settings), provider_name, model, True)
    if not model:
        raise ValueError(
            f"No model configured for role {role!r} (tier {ROLE_TIER[role]!r}) — "
            "set ADVENTURE_MODEL_* in .env"
        )
    return Resolution(_build(provider_name, settings), provider_name, model, False)
