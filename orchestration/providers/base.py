"""Provider seam — base types.

The model is a swappable component, not the moat (Decision Log §2). Two adapters
implement ModelProvider: a local OpenAI-compatible backend (Ollama / vLLM /
LM Studio) as the default, and the Anthropic SDK (Claude) as a hot-swappable
yardstick. Provider-specific optimizations (Claude prompt caching / adaptive
thinking; local quantization) live *inside* the adapters, never in this
interface — no lowest-common-denominator flattening (Stage 4 §2).
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


def _strip_fences(text: str) -> str:
    """Remove markdown code fences that models sometimes add despite instructions."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1])
    return text.strip()


class ModelProvider(ABC):
    """One adapter per backend. Dumb completion only — role/tier routing is the
    registry's job (see registry.py)."""

    name: str

    @abstractmethod
    def complete(self, request: LLMRequest) -> LLMResponse:
        """Run a single completion. Implemented in Stage 4."""
        raise NotImplementedError

    def warm(self) -> None:
        """Construct any lazily-built SDK client — no network call, no token spend.

        The API warm-up (api.app lifespan) calls this before /health reports ready,
        so a misconfigured client (missing key, bad import) fails at boot and is
        disclosed there instead of surfacing as the first /plan's 500. Adapters with
        a lazy client override this to force construction; they must never issue a
        completion from it (warm-up is free by contract). Default: nothing to build.
        """
