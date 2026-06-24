"""Tiny HTTP helper for live adapters — degrade to None on any failure.

Source-or-silence (rule #1): a non-200, network error, or unparseable body yields
None, never a fabricated fact. All failures are logged at DEBUG so we can distinguish
timeout from 404 from parse error without leaking to the user. Adapters accept an
injected `httpx.Client` for testing (drive it with `httpx.MockTransport`).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)
DEFAULT_TIMEOUT = 8.0


def build_client(headers: dict[str, str] | None = None) -> httpx.Client:
    return httpx.Client(timeout=DEFAULT_TIMEOUT, headers=headers or {}, follow_redirects=True)


def get_json(client: httpx.Client, url: str, params: dict[str, Any] | None = None) -> Any:
    try:
        r = client.get(url, params=params)
    except httpx.HTTPError as exc:
        log.debug("GET %s failed: %s", url, exc)
        return None
    if r.status_code != 200:
        log.debug("GET %s returned HTTP %d", url, r.status_code)
        return None
    try:
        return r.json()
    except ValueError as exc:
        log.debug("GET %s body not JSON: %s", url, exc)
        return None


def get_text(client: httpx.Client, url: str, params: dict[str, Any] | None = None) -> str | None:
    try:
        r = client.get(url, params=params)
    except httpx.HTTPError as exc:
        log.debug("GET %s failed: %s", url, exc)
        return None
    if r.status_code != 200:
        log.debug("GET %s returned HTTP %d", url, r.status_code)
        return None
    return r.text


def post_json(client: httpx.Client, url: str, json: dict[str, Any]) -> Any:
    try:
        r = client.post(url, json=json)
    except httpx.HTTPError as exc:
        log.debug("POST %s failed: %s", url, exc)
        return None
    if r.status_code != 200:
        log.debug("POST %s returned HTTP %d", url, r.status_code)
        return None
    try:
        return r.json()
    except ValueError as exc:
        log.debug("POST %s body not JSON: %s", url, exc)
        return None
