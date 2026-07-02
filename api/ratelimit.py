"""Per-IP rate limiting for the public API edge (Phase B: defend-and-secure before
intake).

The public `/plan` endpoint fans out to live third-party APIs and an LLM, each with real
per-call cost and quota. Without a per-IP bound a single client can drain budget or trip
upstream limits for everyone (the R5 abuse gap). slowapi gives a conservative
fixed-window limit keyed by remote address; over the limit the caller gets a clean JSON
429 and the expensive fan-out never runs.

Bounds are intentionally low for a single-region personal utility and are read per
request from env (`ADVENTURE_RATELIMIT_PLAN` / `ADVENTURE_RATELIMIT_HEALTH`), so a load
test or a trusted integration can raise them without a code change. Storage is in-process
(per worker) — adequate for the current single-process deploy; a shared store (Redis)
slots in at `Limiter(storage_uri=...)` when we scale horizontally.
"""

from __future__ import annotations

import os

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request
from starlette.responses import JSONResponse

# Conservative defaults. `/plan` is the expensive fan-out path; `/health` is cheap but
# still bounded so it can't be turned into a liveness-probe amplifier. `/trail` is a scoped
# read; the outcome endpoint is a graph WRITE that also spawns background work, so it gets
# the tightest bound of the lot.
DEFAULT_PLAN_LIMIT = "10/minute"
DEFAULT_HEALTH_LIMIT = "60/minute"
DEFAULT_DETAIL_LIMIT = "60/minute"
DEFAULT_OUTCOME_LIMIT = "20/minute"


def plan_limit() -> str:
    """Per-request `/plan` limit (env-overridable). Evaluated by slowapi on every call,
    so `ADVENTURE_RATELIMIT_PLAN` takes effect without a process restart."""
    return os.environ.get("ADVENTURE_RATELIMIT_PLAN", DEFAULT_PLAN_LIMIT)


def health_limit() -> str:
    """Per-request `/health` limit (env-overridable via `ADVENTURE_RATELIMIT_HEALTH`)."""
    return os.environ.get("ADVENTURE_RATELIMIT_HEALTH", DEFAULT_HEALTH_LIMIT)


def detail_limit() -> str:
    """Per-request `/trail/{id}` read limit (env-overridable via `ADVENTURE_RATELIMIT_DETAIL`)."""
    return os.environ.get("ADVENTURE_RATELIMIT_DETAIL", DEFAULT_DETAIL_LIMIT)


def outcome_limit() -> str:
    """Per-request outcome-write limit (env-overridable via `ADVENTURE_RATELIMIT_OUTCOME`)."""
    return os.environ.get("ADVENTURE_RATELIMIT_OUTCOME", DEFAULT_OUTCOME_LIMIT)


# Module-level singleton: counts must accumulate across requests within a worker.
#
# DEPLOY NOTE (per-IP keying behind a proxy): get_remote_address keys on
# request.client.host. Behind Render's proxy the raw TCP peer is the proxy for every
# request, so production runs uvicorn with `--proxy-headers --forwarded-allow-ips='*'`
# (Dockerfile CMD): uvicorn's ProxyHeadersMiddleware rewrites request.client to the first
# X-Forwarded-For entry before slowapi ever sees it, restoring true per-IP buckets.
# Trust-all is safe on Render specifically — Render rewrites X-Forwarded-For so its first
# entry is the real client IP, and the origin is unreachable except through that proxy,
# so end clients cannot spoof their key. If this ever moves to a host where the origin is
# directly reachable or the proxy merely APPENDS to X-Forwarded-For, '*' becomes a
# trivial limiter bypass — narrow --forwarded-allow-ips to the proxy's hop instead.
limiter = Limiter(key_func=get_remote_address)


def _retry_after_seconds(exc: Exception) -> int | None:
    """The window length (seconds) of the tripped limit, for a `Retry-After` hint. Read
    straight off the `RateLimitExceeded.limit` so it never depends on slowapi's optional
    response-header injection (which only fires for endpoints that return a `Response`, not
    FastAPI model returns). `None` if the shape isn't what we expect — degrade, don't 500."""
    try:
        return int(exc.limit.limit.get_expiry())  # type: ignore[attr-defined]
    except Exception:
        return None


def rate_limit_exceeded_handler(request: Request, exc: Exception) -> JSONResponse:
    """Clean JSON 429 that mirrors the API's `{"detail": ...}` shape.

    Typed `exc: Exception` to satisfy Starlette's `add_exception_handler` signature; it is
    only ever registered for and invoked with `RateLimitExceeded`.

    slowapi's built-in handler returns a bare `"Rate limit exceeded"` text body; this keeps
    the error envelope consistent with every other endpoint and adds a `Retry-After` header
    (derived from the tripped limit's window) so a well-behaved client backs off instead of
    hammering. Registered for `RateLimitExceeded` in `app.py`.
    """
    headers = {}
    retry_after = _retry_after_seconds(exc)
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded; please slow down and retry shortly."},
        headers=headers,
    )
