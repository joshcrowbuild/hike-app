"""Tests for the `_http` logging-redaction guard (review finding #5, rule #10).

FIRMS uniquely carries its MAP_KEY in the URL *path*, and the new `health()` probe
plus the existing probe/fetch path log the url on a transport error. `_safe_url` must
mask the credential-shaped segment (and drop any query/fragment) before it reaches the
DEBUG log, on both the `probe_status` (health) and `get_text` (probe/fetch) paths.
"""

from __future__ import annotations

import logging

import httpx

from orchestration.adapters import _http, firms
from orchestration.adapters.base import Point

_KEY = "abc123def456abc123def456abc12345"  # 32-char FIRMS-style MAP_KEY


def _raising_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    return httpx.Client(transport=httpx.MockTransport(handler))


# ── _safe_url unit coverage ───────────────────────────────────────────────────


def test_safe_url_redacts_long_token_segment() -> None:
    url = (
        "https://firms.modaps.eosdis.nasa.gov/api/area/csv/"
        f"{_KEY}/VIIRS_SNPP_NRT/-78.9,38.0,-77.9,39.0/1"
    )
    safe = _http._safe_url(url)
    assert _KEY not in safe
    assert "/csv/***/" in safe
    assert "VIIRS_SNPP_NRT" in safe  # non-secret route segments are preserved


def test_safe_url_drops_query_and_fragment() -> None:
    safe = _http._safe_url("https://api.example.com/data?api_key=SECRETVALUE123456#frag")
    assert "SECRETVALUE123456" not in safe
    assert "?" not in safe and "#" not in safe


def test_safe_url_preserves_normal_path() -> None:
    url = "https://api.weather.gov/points/38.5,-78.4"
    assert _http._safe_url(url) == url


# ── adapter-level leak regression (health + probe paths) ──────────────────────


def test_firms_health_does_not_leak_map_key(caplog) -> None:
    adapter = firms.FirmsAdapter(_KEY, client=_raising_client())
    with caplog.at_level(logging.DEBUG):
        adapter.health()  # routes through _http.probe_status
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "health GET" in joined  # the failure WAS logged
    assert _KEY not in joined  # but the key was not
    assert "***" in joined


def test_firms_probe_does_not_leak_map_key(caplog) -> None:
    adapter = firms.FirmsAdapter(_KEY, client=_raising_client())
    with caplog.at_level(logging.DEBUG):
        adapter.probe(Point(lat=38.5, lon=-78.4))  # routes through _http.get_text
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert _KEY not in joined
    assert "***" in joined
