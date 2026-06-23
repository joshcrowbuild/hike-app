"""Tiny HTTP helper for live adapters — degrade to None on any failure.

Source-or-silence (rule #1): a non-200, network error, or unparseable body yields
None, never a fabricated fact. Adapters accept an injected `httpx.Client` for
testing (drive it with `httpx.MockTransport`); otherwise a default client is built
lazily via `build_client`.
"""

from __future__ import annotations

from typing import Any

import httpx

DEFAULT_TIMEOUT = 8.0


def build_client(headers: dict[str, str] | None = None) -> httpx.Client:
    return httpx.Client(timeout=DEFAULT_TIMEOUT, headers=headers or {}, follow_redirects=True)


def get_json(client: httpx.Client, url: str, params: dict[str, Any] | None = None) -> Any:
    try:
        r = client.get(url, params=params)
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except ValueError:
        return None


def get_text(client: httpx.Client, url: str, params: dict[str, Any] | None = None) -> str | None:
    try:
        r = client.get(url, params=params)
    except httpx.HTTPError:
        return None
    return r.text if r.status_code == 200 else None


def post_json(client: httpx.Client, url: str, json: dict[str, Any]) -> Any:
    try:
        r = client.post(url, json=json)
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except ValueError:
        return None
