"""Cloud yardstick provider — the Anthropic SDK (Claude).

Hot-swappable comparison backend, not the default (Decision Log §29). Used only
when configured, and never for prompts that touch the private overlay (sensitivity
routing lives in registry.py). The `anthropic` client is imported lazily. Exact
model ids live in config, never hardcoded here.

Stage 0: constructor only; `complete()` is implemented in Stage 4.
"""

from __future__ import annotations

from .base import LLMRequest, LLMResponse, ModelProvider


class AnthropicProvider(ModelProvider):
    name = "anthropic"

    def __init__(self, api_key: str | None) -> None:
        self.api_key = api_key

    def complete(self, request: LLMRequest) -> LLMResponse:
        # Stage 4: lazy `import anthropic`; client = anthropic.Anthropic(api_key=...);
        # client.messages.create(...). Provider-specific levers (prompt caching,
        # adaptive thinking) are applied here, behind the seam.
        raise NotImplementedError("AnthropicProvider.complete is implemented in Stage 4")
