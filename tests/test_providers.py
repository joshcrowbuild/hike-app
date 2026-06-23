"""Provider-adapter tests (Track C) using injected fake clients — no SDK, no network.

Asserts request mapping and response shaping for both adapters, and that
provider-specific options pass through behind the seam (Stage 4 §2).
"""

from __future__ import annotations

from typing import Any

from orchestration.providers.anthropic_claude import AnthropicProvider
from orchestration.providers.base import LLMRequest
from orchestration.providers.local_openai import LocalOpenAIProvider


class _Obj:
    def __init__(self, **kw: Any) -> None:
        self.__dict__.update(kw)


class _FakeOpenAI:
    """Quacks like openai.OpenAI(): client.chat.completions.create(...)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.chat = _Obj(completions=self)

    def create(self, **kw: Any) -> _Obj:
        self.calls.append(kw)
        return _Obj(
            choices=[_Obj(message=_Obj(content="local-says-hi"))],
            usage=_Obj(prompt_tokens=11, completion_tokens=3),
            model=kw["model"],
        )


class _FakeAnthropic:
    """Quacks like anthropic.Anthropic(): client.messages.create(...)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.messages = self

    def create(self, **kw: Any) -> _Obj:
        self.calls.append(kw)
        return _Obj(
            content=[_Obj(type="text", text="claude-says-hi")],
            model=kw["model"],
            usage=_Obj(input_tokens=12, output_tokens=4),
        )


def _req(**kw: Any) -> LLMRequest:
    base: dict[str, Any] = {
        "system": "sys",
        "messages": [{"role": "user", "content": "hi"}],
        "model": "m",
        "max_tokens": 64,
    }
    base.update(kw)
    return LLMRequest(**base)


def test_local_openai_maps_request_and_response() -> None:
    fake = _FakeOpenAI()
    r = LocalOpenAIProvider("http://x/v1", client=fake).complete(_req())
    assert r.text == "local-says-hi"
    assert r.provider == "local"
    assert r.usage == {"input_tokens": 11, "output_tokens": 3}
    sent = fake.calls[0]
    assert sent["model"] == "m"
    assert sent["messages"][0]["role"] == "system"  # system prepended


def test_anthropic_concats_text_blocks_and_passes_options() -> None:
    fake = _FakeAnthropic()
    r = AnthropicProvider("key", client=fake).complete(
        _req(options={"thinking": {"type": "adaptive"}})
    )
    assert r.text == "claude-says-hi"
    assert r.provider == "anthropic"
    assert r.usage == {"input_tokens": 12, "output_tokens": 4}
    # provider-specific lever passed through behind the seam
    assert fake.calls[0]["thinking"] == {"type": "adaptive"}
