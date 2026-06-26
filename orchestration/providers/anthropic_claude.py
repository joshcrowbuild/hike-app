"""Cloud yardstick provider — the Anthropic SDK (Claude).

Hot-swappable comparison backend, not the default (Decision Log §29). Used only
when configured, and never for prompts that touch the private overlay (sensitivity
routing lives in registry.py). The `anthropic` client is imported lazily; pass
`client=` to inject a fake for testing. Exact model ids live in config (passed on
`request.model`), never hardcoded here. Provider-specific levers (prompt caching,
adaptive thinking, effort) ride in `request.options` and are applied here, behind
the seam — never flattened into the shared contract.
"""

from __future__ import annotations

from typing import Any

from .base import LLMRequest, LLMResponse, ModelProvider


class AnthropicProvider(ModelProvider):
    name = "anthropic"

    def __init__(self, api_key: str | None, *, client: Any = None) -> None:
        self._api_key = api_key  # underscore: keep out of debug repr / exception dumps
        self._client = client

    def _ensure_client(self) -> Any:
        if self._client is None:
            import anthropic  # lazy: only needed for real calls

            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def complete(self, request: LLMRequest) -> LLMResponse:
        client = self._ensure_client()
        resp = client.messages.create(
            model=request.model,
            max_tokens=request.max_tokens,
            system=request.system,
            messages=request.messages,
            **request.options,  # provider-specific levers (thinking, output_config, cache_control)
        )
        text = "".join(
            block.text for block in resp.content if getattr(block, "type", None) == "text"
        )
        usage = getattr(resp, "usage", None)
        return LLMResponse(
            text=text,
            model=getattr(resp, "model", request.model),
            provider=self.name,
            usage=(
                {
                    "input_tokens": getattr(usage, "input_tokens", 0),
                    "output_tokens": getattr(usage, "output_tokens", 0),
                }
                if usage is not None
                else {}
            ),
        )
