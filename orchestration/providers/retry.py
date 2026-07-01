"""Bounded transient-error retry for the provider seam (reliability lane).

A transient model-provider error (429 rate-limit, 500/502/503/504, 529 overloaded, a
connection reset or read timeout) is a blip, not a verdict — retrying a moment later
usually succeeds. Left unhandled it propagates out of `complete()` and 500s /plan. This
helper wraps a single provider call in a **bounded** exponential-backoff-with-jitter
retry over ONLY the transient classes; a client error (400 / 401 / 403 / 404 / 422) is
never retried (a retry can't fix a bad request) and surfaces immediately.

Applied once in the seam so BOTH tiers (mechanical intent-parse + judgment ranking) and
BOTH adapters (Anthropic, local OpenAI-compatible) inherit it. The caps keep the worst-
case added latency far under /plan's 60s budget: 3 attempts = at most 2 backoffs, base
0.5s, ×2, capped 2.0s, plus < 0.5s jitter ⇒ under ~2s added.

`is_transient_api_error` classifies by the SDK's public error shape (`.status_code` for
HTTP errors; class name for connection/timeout errors) so this module imports neither the
anthropic nor the openai SDK — the same predicate serves both httpx-based clients.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

# Transient HTTP statuses worth retrying. Deliberately EXCLUDES 400/401/403/404/413/422
# (client errors — a retry never helps and only spends the latency budget).
RETRYABLE_STATUS: frozenset[int] = frozenset({408, 409, 429, 500, 502, 503, 504, 529})

# Connection / read-timeout error class names. Both the anthropic and openai SDKs (both
# httpx-based) name these identically and neither carries a `.status_code`, so matching by
# class-MRO name lets this module stay SDK-import-free.
_CONNECTION_ERROR_NAMES: frozenset[str] = frozenset({"APIConnectionError", "APITimeoutError"})

# Defaults sized to stay well under the /plan 60s budget (see module docstring).
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BASE_DELAY_S = 0.5
DEFAULT_MAX_DELAY_S = 2.0


def _retry_after_seconds(exc: BaseException) -> float | None:
    """The server-requested cooldown from a 429/503's `Retry-After` header, if present.
    Read off the SDK error's `.response.headers` (both anthropic and openai expose it as
    httpx.Headers) so no SDK import is needed; `retry-after-ms` is milliseconds, `retry-after`
    integer seconds. Returns None when absent, on a connection error (no response), or on the
    rarely-used HTTP-date form (we fall back to computed backoff rather than mis-parse)."""
    headers = getattr(getattr(exc, "response", None), "headers", None)
    if headers is None:
        return None
    try:
        ra_ms = headers.get("retry-after-ms")
        if ra_ms is not None:
            return max(0.0, float(ra_ms) / 1000.0)
        ra = headers.get("retry-after")
        if ra is not None:
            return max(0.0, float(ra))
    except (TypeError, ValueError):
        return None
    return None


def is_transient_api_error(exc: BaseException) -> bool:
    """True for a retryable transport/server blip; False for a client error or anything
    unrecognized. Keyed on `.status_code` (present on every APIStatusError subclass —
    RateLimitError=429, OverloadedError=529, InternalServerError=5xx, and the non-retryable
    BadRequestError=400 / AuthenticationError=401 / PermissionDeniedError=403 / …) and, when
    there is no status, on the connection/timeout error class name."""
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        # A concrete HTTP status decides it outright — retryable set or not.
        return status in RETRYABLE_STATUS
    # No status → maybe a connection/timeout error (APIConnectionError / APITimeoutError).
    names = {klass.__name__ for klass in type(exc).__mro__}
    return bool(names & _CONNECTION_ERROR_NAMES)


def retry_transient(
    call: Callable[[], T],
    *,
    is_transient: Callable[[BaseException], bool] = is_transient_api_error,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay_s: float = DEFAULT_BASE_DELAY_S,
    max_delay_s: float = DEFAULT_MAX_DELAY_S,
    sleep: Callable[[float], None] | None = None,
    jitter: Callable[[], float] | None = None,
) -> T:
    """Call `call()`, retrying on a transient error up to `max_attempts` total. A
    non-transient error, or the final attempt's error, is re-raised unchanged (the
    caller's degrade-and-disclose / typed-5xx handling still applies).

    `sleep`/`jitter` resolve to `time.sleep`/`random.random` at call time (not def time)
    so a test can monkeypatch them on the module without threading an argument through the
    provider seam."""
    do_sleep = time.sleep if sleep is None else sleep
    do_jitter = random.random if jitter is None else jitter
    attempt = 0
    while True:
        try:
            return call()
        except Exception as exc:  # noqa: BLE001 — re-raised unless classified transient
            attempt += 1
            if attempt >= max_attempts or not is_transient(exc):
                raise
            # Respect a server `Retry-After` when it fits our per-attempt cap (retrying a
            # rate-limit before the server's cooldown just burns an attempt); otherwise back
            # off exponentially with jitter. Either way the delay is capped at max_delay_s so
            # total added latency stays well under /plan's 60s budget.
            retry_after = _retry_after_seconds(exc)
            if retry_after is not None:
                delay = min(max_delay_s, retry_after)
            else:
                delay = (
                    min(max_delay_s, base_delay_s * (2 ** (attempt - 1)))
                    + do_jitter() * base_delay_s
                )
            do_sleep(delay)
