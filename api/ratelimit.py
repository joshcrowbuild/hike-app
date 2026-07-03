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


def real_client_ip(request: Request) -> str:
    """Rate-limit key: the true client IP, immune to a client-injected X-Forwarded-For.

    VERIFIED FINDING (2026-07-02, closes AH2): production runs uvicorn (>=0.30; installed
    0.49.0 at verification time) with `--proxy-headers --forwarded-allow-ips='*'`
    (Dockerfile CMD) so `request.client.host` isn't the proxy's IP for every request.
    Reading uvicorn's `ProxyHeadersMiddleware`/`_TrustedHosts.get_trusted_client_address`
    source showed the trust-all ('*') branch unconditionally takes the FIRST (leftmost)
    X-Forwarded-For entry with **no hop-count check at all** — it does not verify the
    header actually came from N trusted proxies; it just reads index 0. That branch is
    only as safe as "the leftmost entry is always proxy-asserted," which turned out to be
    an unverified, second-hand claim (a single 2021 Render-staff forum comment, not
    reproduced in Render's current docs) — and empirically the deployed edge in front of
    Render's own origin (confirmed via DNS/BGP to be Render's own AS397273, not a
    separate bypassable CDN hop) could not be proven, within a live black-box test budget,
    to always overwrite rather than append to a client-supplied X-Forwarded-For. A live
    /health probe (fixed spoofed XFF / none / rotating spoofed XFF, interleaved) was
    inconclusive at safe request volumes — the 60/min window can't be boundary-tested
    without hammering production — so per the safe-default policy this closes the gap in
    code instead of trusting network topology alone.

    Fix: never trust `request.client.host` (which uvicorn's middleware may have already
    rewritten to an attacker-chosen leftmost value) for the rate-limit key. Instead read
    the raw X-Forwarded-For header directly and take the LAST (rightmost) entry. Render's
    own docs confirm the container port "is not directly reachable via the public
    internet" — every request's actual TCP peer is Render's edge, exactly one hop away —
    so the rightmost entry is always the one that hop appended/set, no matter how many
    bogus entries a client prepends before it. This is correct whether Render overwrites
    the header (single entry; rightmost == only entry) or appends to it (rightmost ==
    Render's own observed IP, client prefix ignored) — safe under either hypothesis,
    which is exactly the ambiguity the live test couldn't resolve.

    Falls back to `get_remote_address` (the raw ASGI `request.client.host`) when no
    X-Forwarded-For is present — local/dev/direct connections.
    """
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        candidate = forwarded_for.split(",")[-1].strip()
        if candidate:
            return candidate
    return get_remote_address(request)


# Module-level singleton: counts must accumulate across requests within a worker.
# Keyed by `real_client_ip`, not slowapi's default `get_remote_address` — see its
# docstring for the verified reasoning (AH2).
limiter = Limiter(key_func=real_client_ip)


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
