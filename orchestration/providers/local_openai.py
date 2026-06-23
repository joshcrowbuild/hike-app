"""Local / self-hosted provider via an OpenAI-compatible endpoint.

Default backend (Decision Log §29: provider-agnostic, local-first). Targets
Ollama / vLLM / LM Studio, which all expose the OpenAI Chat Completions API. The
`openai` client is imported lazily so the base install and the smoke tests never
require it.

Stage 0: constructor only; `complete()` is implemented in Stage 4.
"""

from __future__ import annotations

from .base import LLMRequest, LLMResponse, ModelProvider


class LocalOpenAIProvider(ModelProvider):
    name = "local"

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url

    def complete(self, request: LLMRequest) -> LLMResponse:
        # Stage 4: lazy `import openai`; client = openai.OpenAI(base_url=self.base_url,
        # api_key="not-needed"); client.chat.completions.create(...).
        raise NotImplementedError("LocalOpenAIProvider.complete is implemented in Stage 4")
