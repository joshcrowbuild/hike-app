"""Provider transient-retry (reliability lane) — hermetic, no SDK network, no keys.

A transient model-provider blip (429 / 5xx / 529 overloaded / connection reset) must be
retried with bounded backoff so it never surfaces as a /plan 500; a client error
(400 / 401 / 403 / 422) must NOT be retried. Covered at two levels:

  * the pure `retry_transient` helper + its `is_transient_api_error` predicate, and
  * both adapters (`AnthropicProvider`, `LocalOpenAIProvider`) driving a flaky injected
    client so the seam's wiring is exercised end to end.

The Anthropic error classes are constructed faithfully (real SDK exceptions over an httpx
Response, so `.status_code` is real); the OpenAI SDK isn't installed, so its transient is a
duck-typed status carrier — which is exactly what the SDK-agnostic predicate keys on.
"""

from __future__ import annotations

import time
from typing import Any

import anthropic
import httpx
import pytest

from orchestration.providers.anthropic_claude import AnthropicProvider
from orchestration.providers.base import LLMRequest
from orchestration.providers.local_openai import LocalOpenAIProvider
from orchestration.providers.retry import is_transient_api_error, retry_transient

_REQ = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def _anthropic_status_error(code: int, cls: type[anthropic.APIStatusError]) -> Exception:
    return cls("simulated", response=httpx.Response(code, request=_REQ), body=None)


class _DuckStatusError(Exception):
    """A minimal exception carrying `.status_code`, like every httpx-based SDK error."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code


# ── is_transient_api_error ──────────────────────────────────────────────────────


@pytest.mark.parametrize("code", [408, 409, 429, 500, 502, 503, 504, 529])
def test_transient_statuses_are_retryable(code: int) -> None:
    assert is_transient_api_error(_DuckStatusError(code)) is True


@pytest.mark.parametrize("code", [400, 401, 403, 404, 413, 422])
def test_client_error_statuses_are_not_retryable(code: int) -> None:
    assert is_transient_api_error(_DuckStatusError(code)) is False


def test_real_anthropic_errors_classified() -> None:
    # Faithful: real SDK exceptions over a real httpx Response.
    assert is_transient_api_error(
        _anthropic_status_error(529, anthropic.APIStatusError)
    )  # overloaded
    assert is_transient_api_error(_anthropic_status_error(429, anthropic.RateLimitError))
    assert is_transient_api_error(_anthropic_status_error(503, anthropic.InternalServerError))
    assert is_transient_api_error(anthropic.APIConnectionError(request=_REQ))  # reset
    assert is_transient_api_error(anthropic.APITimeoutError(request=_REQ))  # read timeout
    assert not is_transient_api_error(_anthropic_status_error(400, anthropic.BadRequestError))
    assert not is_transient_api_error(_anthropic_status_error(401, anthropic.AuthenticationError))
    assert not is_transient_api_error(_anthropic_status_error(403, anthropic.PermissionDeniedError))


def test_unknown_exception_is_not_transient() -> None:
    # A bare error with no status and no connection-error name is not blindly retried.
    assert is_transient_api_error(ValueError("nope")) is False


# ── retry_transient ─────────────────────────────────────────────────────────────


def _counter() -> Any:
    class _C:
        n = 0

    return _C()


def test_retry_recovers_after_transient_then_success() -> None:
    c = _counter()
    delays: list[float] = []

    def call() -> str:
        c.n += 1
        if c.n == 1:
            raise _DuckStatusError(529)
        return "ok"

    result = retry_transient(call, sleep=delays.append, jitter=lambda: 0.0)
    assert result == "ok"
    assert c.n == 2  # one failure, one success
    assert len(delays) == 1  # backed off exactly once


def test_retry_gives_up_after_max_attempts_and_raises_last() -> None:
    c = _counter()

    def call() -> str:
        c.n += 1
        raise _DuckStatusError(503)

    with pytest.raises(_DuckStatusError):
        retry_transient(call, sleep=lambda _: None, jitter=lambda: 0.0)
    assert c.n == 3  # DEFAULT_MAX_ATTEMPTS — no unbounded retrying


def test_retry_does_not_retry_non_transient() -> None:
    c = _counter()

    def call() -> str:
        c.n += 1
        raise _DuckStatusError(400)

    with pytest.raises(_DuckStatusError):
        retry_transient(call, sleep=lambda _: None, jitter=lambda: 0.0)
    assert c.n == 1  # a client error is surfaced immediately


def test_retry_backoff_is_bounded() -> None:
    delays: list[float] = []

    def call() -> str:
        raise _DuckStatusError(500)

    with pytest.raises(_DuckStatusError):
        retry_transient(
            call,
            sleep=delays.append,
            jitter=lambda: 1.0,
            max_attempts=6,
            base_delay_s=0.5,
            max_delay_s=2.0,
        )
    # Every backoff is capped: min(max_delay, base*2**n) + jitter*base ≤ 2.0 + 0.5.
    assert delays and all(d <= 2.5 for d in delays)


class _RetryAfterError(Exception):
    """A 429/503-shaped error carrying a Retry-After header, like the real SDK errors."""

    def __init__(self, status_code: int, retry_after: str, *, ms: bool = False) -> None:
        super().__init__("rate limited")
        self.status_code = status_code
        key = "retry-after-ms" if ms else "retry-after"
        self.response = type("_R", (), {"headers": {key: retry_after}})()


def test_retry_honors_bounded_retry_after() -> None:
    delays: list[float] = []
    c = _counter()

    def call() -> str:
        c.n += 1
        if c.n == 1:
            raise _RetryAfterError(429, "1")  # server asks for a 1s cooldown
        return "ok"

    result = retry_transient(call, sleep=delays.append, jitter=lambda: 0.0, max_delay_s=2.0)
    assert result == "ok"
    assert delays == [1.0]  # honored the server's cooldown exactly (within the cap)


def test_retry_honors_retry_after_ms() -> None:
    delays: list[float] = []
    c = _counter()

    def call() -> str:
        c.n += 1
        if c.n == 1:
            raise _RetryAfterError(429, "500", ms=True)  # 500ms
        return "ok"

    retry_transient(call, sleep=delays.append, jitter=lambda: 0.0, max_delay_s=2.0)
    assert delays == [0.5]


def test_retry_after_is_capped_to_budget() -> None:
    delays: list[float] = []

    def call() -> str:
        raise _RetryAfterError(429, "30")  # server asks 30s — must be clamped

    with pytest.raises(_RetryAfterError):
        retry_transient(call, sleep=delays.append, jitter=lambda: 0.0, max_delay_s=2.0)
    # Clamped to the per-attempt cap so a long server cooldown can't blow /plan's budget.
    assert delays and all(d == 2.0 for d in delays)


# ── AnthropicProvider through the seam ──────────────────────────────────────────


class _Obj:
    def __init__(self, **kw: Any) -> None:
        self.__dict__.update(kw)


class _FlakyAnthropic:
    """client.messages.create(...) raises each queued error once, then succeeds."""

    def __init__(self, errors: list[Exception]) -> None:
        self._errors = list(errors)
        self.calls = 0
        self.messages = self

    def create(self, **kw: Any) -> _Obj:
        self.calls += 1
        if self._errors:
            raise self._errors.pop(0)
        return _Obj(
            content=[_Obj(type="text", text="claude-ok")],
            model=kw["model"],
            usage=_Obj(input_tokens=5, output_tokens=2),
        )


def _req() -> LLMRequest:
    return LLMRequest(system="s", messages=[{"role": "user", "content": "hi"}], model="m")


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch: Any) -> None:
    # Provider-level calls use retry_transient's default sleep; keep the suite fast.
    monkeypatch.setattr(time, "sleep", lambda _s: None)


def test_anthropic_retries_transient_529_then_succeeds() -> None:
    overloaded = _anthropic_status_error(529, anthropic.APIStatusError)
    fake = _FlakyAnthropic([overloaded])
    resp = AnthropicProvider("key", client=fake).complete(_req())
    assert resp.text == "claude-ok"  # recovered
    assert fake.calls == 2  # retried once


def test_anthropic_does_not_retry_client_error() -> None:
    bad = _anthropic_status_error(400, anthropic.BadRequestError)
    fake = _FlakyAnthropic([bad])
    with pytest.raises(anthropic.BadRequestError):
        AnthropicProvider("key", client=fake).complete(_req())
    assert fake.calls == 1  # single call — a bad request is never retried


def test_anthropic_exhausts_and_raises_on_persistent_transient() -> None:
    errors = [_anthropic_status_error(503, anthropic.InternalServerError) for _ in range(3)]
    fake = _FlakyAnthropic(errors)
    with pytest.raises(anthropic.InternalServerError):
        AnthropicProvider("key", client=fake).complete(_req())
    assert fake.calls == 3  # bounded attempts, then the real cause propagates (→ typed 5xx)


# ── LocalOpenAIProvider through the seam (symmetric) ────────────────────────────


class _FlakyOpenAI:
    def __init__(self, errors: list[Exception]) -> None:
        self._errors = list(errors)
        self.calls = 0
        self.chat = _Obj(completions=self)

    def create(self, **kw: Any) -> _Obj:
        self.calls += 1
        if self._errors:
            raise self._errors.pop(0)
        return _Obj(
            choices=[_Obj(message=_Obj(content="local-ok"))],
            usage=_Obj(prompt_tokens=4, completion_tokens=1),
            model=kw["model"],
        )


def test_local_openai_retries_transient_then_succeeds() -> None:
    fake = _FlakyOpenAI([_DuckStatusError(503)])
    resp = LocalOpenAIProvider("http://x/v1", client=fake).complete(_req())
    assert resp.text == "local-ok"
    assert fake.calls == 2


def test_local_openai_does_not_retry_client_error() -> None:
    fake = _FlakyOpenAI([_DuckStatusError(400)])
    with pytest.raises(_DuckStatusError):
        LocalOpenAIProvider("http://x/v1", client=fake).complete(_req())
    assert fake.calls == 1
