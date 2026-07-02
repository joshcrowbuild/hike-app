"""Tiny HTTP helper for live adapters — degrade to None on any failure.

Source-or-silence (rule #1): a non-200, network error, or unparseable body yields
None, never a fabricated fact. All failures are logged at DEBUG so we can distinguish
timeout from 404 from parse error without leaking to the user. Adapters accept an
injected `httpx.Client` for testing (drive it with `httpx.MockTransport`).

Secrets never reach the logs (rule #10): FIRMS uniquely carries its MAP_KEY in the
URL *path*, so every log site routes the url through `_safe_url`, which masks
credential-shaped path segments and drops any query/fragment before logging.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

log = logging.getLogger(__name__)
DEFAULT_TIMEOUT = 8.0

# A path segment that is a long opaque token (>=20 chars, no separators) is almost
# certainly a credential, not a route — FIRMS carries its 32-char MAP_KEY as exactly
# such a segment (firms.py URL). Redact it before logging (rule #10).
_SECRET_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._-]{20,}$")


def _safe_url(url: str) -> str:
    """Mask credential-shaped path segments and drop any query/fragment before logging
    (rule #10). FIRMS routes its MAP_KEY through the URL path; other adapters keep
    secrets in params/headers, which never enter the `url` string logged here."""
    parts = urlsplit(url)
    safe_path = "/".join(
        "***" if _SECRET_SEGMENT_RE.match(seg) else seg for seg in parts.path.split("/")
    )
    return urlunsplit((parts.scheme, parts.netloc, safe_path, "", ""))


def build_client(headers: dict[str, str] | None = None) -> httpx.Client:
    # AH1/AL1: never auto-follow redirects. Every fixed-host adapter (NWS, AirNow,
    # FIRMS, RIDB, USGS) answers 200 directly with no redirect hop; the one
    # config-driven URL (Valhalla's self-hosted base_url) is the SSRF risk this
    # closes — a misconfigured or compromised upstream could otherwise 302 a
    # request to an internal address. A response that returns a 3xx now degrades
    # to None via the normal non-200 path (source-or-silence, rule #1) instead of
    # being followed blindly.
    return httpx.Client(timeout=DEFAULT_TIMEOUT, headers=headers or {}, follow_redirects=False)


def get_json(client: httpx.Client, url: str, params: dict[str, Any] | None = None) -> Any:
    try:
        r = client.get(url, params=params)
    except httpx.HTTPError as exc:
        log.debug("GET %s failed: %s", _safe_url(url), exc)
        return None
    if r.status_code != 200:
        log.debug("GET %s returned HTTP %d", _safe_url(url), r.status_code)
        return None
    try:
        return r.json()
    except ValueError as exc:
        log.debug("GET %s body not JSON: %s", _safe_url(url), exc)
        return None


def get_text(client: httpx.Client, url: str, params: dict[str, Any] | None = None) -> str | None:
    try:
        r = client.get(url, params=params)
    except httpx.HTTPError as exc:
        log.debug("GET %s failed: %s", _safe_url(url), exc)
        return None
    if r.status_code != 200:
        log.debug("GET %s returned HTTP %d", _safe_url(url), r.status_code)
        return None
    return r.text


def probe_status(
    client: httpx.Client, url: str, params: dict[str, Any] | None = None
) -> int | None:
    """Return the HTTP status of a lightweight liveness GET, or None on a connection
    error — fed to `health_from_status` so an adapter's `health()` never raises."""
    try:
        r = client.get(url, params=params)
    except httpx.HTTPError as exc:
        log.debug("health GET %s failed: %s", _safe_url(url), exc)
        return None
    return r.status_code


def post_json(client: httpx.Client, url: str, json: dict[str, Any]) -> Any:
    try:
        r = client.post(url, json=json)
    except httpx.HTTPError as exc:
        log.debug("POST %s failed: %s", _safe_url(url), exc)
        return None
    if r.status_code != 200:
        log.debug("POST %s returned HTTP %d", _safe_url(url), r.status_code)
        return None
    try:
        return r.json()
    except ValueError as exc:
        log.debug("POST %s body not JSON: %s", _safe_url(url), exc)
        return None
