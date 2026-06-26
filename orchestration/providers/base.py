"""Provider seam — base types.

The model is a swappable component, not the moat (Decision Log §2). Two adapters
implement ModelProvider: a local OpenAI-compatible backend (Ollama / vLLM /
LM Studio) as the default, and the Anthropic SDK (Claude) as a hot-swappable
yardstick. Provider-specific optimizations (Claude prompt caching / adaptive
thinking; local quantization) live *inside* the adapters, never in this
interface — no lowest-common-denominator flattening (Stage 4 §2).

Stage 0 ships the contract only; adapters raise NotImplementedError until Stage 4.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class LLMRequest:
    system: str
    messages: list[dict[str, str]]
    model: str
    max_tokens: int = 1024
    # Provider-specific knobs (caching, thinking, effort) passed opaquely and
    # interpreted by the adapter — kept out of the shared contract.
    options: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    provider: str
    usage: dict[str, int] = field(default_factory=dict)


class ModelProvider(ABC):
    """One adapter per backend. Dumb completion only — role/tier routing is the
    registry's job (see registry.py)."""

    name: str

    @abstractmethod
    def complete(self, request: LLMRequest) -> LLMResponse:
        """Run a single completion. Implemented in Stage 4."""
        raise NotImplementedError
