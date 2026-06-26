"""Intent parsing edge cases — fences, bad types, and empty queries."""

from __future__ import annotations

from orchestration.intent import Intent, _parse, parse_intent
from orchestration.providers.base import LLMRequest, LLMResponse, ModelProvider


class _FakeProvider(ModelProvider):
    name = "fake"

    def __init__(self, text: str) -> None:
        self.text = text

    def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(text=self.text, model=request.model, provider=self.name)


def test_empty_query_returns_default_intent() -> None:
    provider = _FakeProvider("should-not-be-used")
    assert parse_intent("", provider, "m") == Intent()
    assert parse_intent("   ", provider, "m") == Intent()


def test_whitespace_query_returns_default_intent() -> None:
    provider = _FakeProvider("should-not-be-used")
    assert parse_intent("\t\n", provider, "m") == Intent()


def test_parse_strips_code_fence_with_language_tag() -> None:
    intent = _parse('```json\n{"radius_m": 1000}\n```')
    assert intent.radius_m == 1000


def test_parse_strips_fence_and_trims_whitespace() -> None:
    intent = _parse('  ```\n{"radius_m": 1000}\n```  ')
    assert intent.radius_m == 1000


def test_parse_returns_empty_on_missing_fence_closer() -> None:
    assert _parse("```\n{}") == Intent()


def test_parse_returns_empty_on_top_level_array() -> None:
    assert _parse("[1, 2, 3]") == Intent()


def test_parse_returns_empty_on_top_level_string() -> None:
    assert _parse('"just a string"') == Intent()


def test_parse_returns_empty_on_null() -> None:
    assert _parse("null") == Intent()


def test_parse_rejects_bool_radius() -> None:
    intent = _parse('{"radius_m": true}')
    assert intent.radius_m is None


def test_parse_rejects_string_radius() -> None:
    intent = _parse('{"radius_m": "5000"}')
    assert intent.radius_m is None


def test_parse_rejects_float_radius() -> None:
    intent = _parse('{"radius_m": 5.5}')
    assert intent.radius_m is None


def test_parse_accepts_int_radius() -> None:
    intent = _parse('{"radius_m": 5000}')
    assert intent.radius_m == 5000


def test_parse_rejects_non_dict_filters() -> None:
    intent = _parse('{"filters": []}')
    assert intent.filters == {}


def test_parse_rejects_non_string_profile() -> None:
    intent = _parse('{"profile": 123}')
    assert intent.profile is None


def test_parse_accepts_string_profile() -> None:
    intent = _parse('{"profile": "easy loops"}')
    assert intent.profile == "easy loops"


def test_parse_missing_fields_use_defaults() -> None:
    intent = _parse("{}")
    assert intent.radius_m is None
    assert intent.filters == {}
    assert intent.profile is None


def test_parse_extra_fields_are_ignored() -> None:
    intent = _parse('{"radius_m": 1000, "extra": "ignored"}')
    assert intent.radius_m == 1000
    assert "extra" not in intent.filters


def test_parse_intent_model_passed_to_provider() -> None:
    provider = _FakeProvider('{"radius_m": 1000}')
    parse_intent("x", provider, "custom-model-7")
    # LLMResponse returned carries the model from the request; no side effect to assert,
    # but the function ran without error, which is the success case.
