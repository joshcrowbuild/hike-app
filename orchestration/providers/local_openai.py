"""Local / self-hosted provider via an OpenAI-compatible endpoint.

Default backend (Decision Log §29: provider-agnostic, local-first). Targets
Ollama / vLLM / LM Studio, which all expose the OpenAI Chat Completions API. The
`openai` client is imported lazily so the base install and the unit tests never
require it; pass `client=` to inject a fake (or a pre-built client) for testing.
"""

from __future__ import annotations

from typing import Any

from .base import LLMRequest, LLMResponse, ModelProvider
from .retry import retry_transient


class LocalOpenAIProvider(ModelProvider):
    name = "local"

    def __init__(self, base_url: str, *, client: Any = None, api_key: str = "not-needed") -> None:
        self.base_url = base_url
        self._api_key = api_key
        self._client = client

    def _ensure_client(self) -> Any:
        if self._client is None:
            import openai  # lazy: only needed for real calls

            # max_retries=0: retry_transient (below) owns the policy; don't stack the SDK's.
            self._client = openai.OpenAI(
                base_url=self.base_url, api_key=self._api_key, max_retries=0
            )
        return self._client

    def complete(self, request: LLMRequest) -> LLMResponse:
        client = self._ensure_client()
        messages = [{"role": "system", "content": request.system}, *request.messages]
        # Symmetric with the Anthropic adapter: retry a transient blip with bounded backoff
        # (the openai SDK shares anthropic's httpx-based error shape, so the same predicate
        # classifies both). A local server rarely 429s, but a connection reset still degrades
        # cleanly instead of 500ing /plan.
        resp = retry_transient(
            lambda: client.chat.completions.create(
                model=request.model,
                messages=messages,
                max_tokens=request.max_tokens,
                **request.options,
            )
        )
        choice = resp.choices[0]
        usage = getattr(resp, "usage", None)
        return LLMResponse(
            text=choice.message.content or "",
            model=getattr(resp, "model", request.model),
            provider=self.name,
            usage=(
                {
                    "input_tokens": getattr(usage, "prompt_tokens", 0),
                    "output_tokens": getattr(usage, "completion_tokens", 0),
                }
                if usage is not None
                else {}
            ),
        )
