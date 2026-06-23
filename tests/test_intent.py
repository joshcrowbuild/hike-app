"""Intent-parse tests (fake provider; no network)."""

from __future__ import annotations

from typing import Any

from orchestration.intent import Intent, parse_intent
from orchestration.providers.base import LLMResponse


class _FakeProvider:
    name = "fake"

    def __init__(self, text: str) -> None:
        self.text = text

    def complete(self, request: Any) -> LLMResponse:
        return LLMResponse(text=self.text, model=request.model, provider=self.name)


def test_parse_intent_extracts_structured() -> None:
    provider = _FakeProvider(
        '{"radius_m": 20000, "filters": {"dog": true}, "profile": "easy loops"}'
    )
    intent = parse_intent("dog-friendly easy loop", provider, "m")
    assert intent.radius_m == 20000
    assert intent.filters == {"dog": True}
    assert intent.profile == "easy loops"


def test_parse_intent_graceful_on_garbage() -> None:
    assert parse_intent("x", _FakeProvider("not json"), "m") == Intent()
    assert parse_intent("x", _FakeProvider('"a bare string"'), "m") == Intent()


def test_parse_intent_ignores_wrong_types() -> None:
    # radius as a bool/string -> dropped, not coerced
    intent = parse_intent("x", _FakeProvider('{"radius_m": true, "filters": []}'), "m")
    assert intent.radius_m is None
    assert intent.filters == {}
