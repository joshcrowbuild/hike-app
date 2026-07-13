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


# ── build_client follows redirects by default; opt out for config-driven URLs ──


def test_build_client_follows_redirects_by_default() -> None:
    # Fixed-host government adapters (NWS, AirNow, FIRMS, RIDB, USGS) are hardcoded
    # constant URLs, not an SSRF vector, and NWS relies on redirects to reach the
    # canonical forecast URL — so the shared default follows them.
    client = _http.build_client()
    assert client.follow_redirects is True


def test_build_client_can_disable_redirects() -> None:
    # A config-driven URL (e.g. Valhalla's self-hosted base_url) that 302s to an
    # internal address must surface as a 3xx, never be silently followed — the
    # Valhalla adapter opts out explicitly.
    client = _http.build_client(follow_redirects=False)
    assert client.follow_redirects is False


def test_get_json_degrades_to_none_on_redirect() -> None:
    # source-or-silence (rule #1): an unfollowed 3xx is a non-200, so get_json returns
    # None rather than raising or fabricating a body.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "http://internal.invalid/"})

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    assert _http.get_json(client, "https://example.invalid/") is None


# ── shared transport (2026-07-13 cold-/plan latency root cause) ────────────────


def test_build_client_shares_one_transport() -> None:
    # Adapters build a fresh Client per probe; the expensive parts (SSLContext +
    # keep-alive connection pool) must be paid once per process, not per probe —
    # every built client rides the same transport singleton.
    a = _http.build_client()
    b = _http.build_client(headers={"X-Api-Key": "k"}, follow_redirects=False)
    assert a._transport is b._transport
    assert a._transport is _http._get_shared_transport()


def test_build_client_keeps_per_client_seams() -> None:
    # Sharing the transport must not share what is per-adapter: headers and the
    # redirect mode stay on the individual client.
    a = _http.build_client(headers={"User-Agent": "nws-contact"})
    b = _http.build_client(headers={"X-Api-Key": "nps-key"}, follow_redirects=False)
    assert a.headers["User-Agent"] == "nws-contact"
    assert "X-Api-Key" not in a.headers
    assert b.headers["X-Api-Key"] == "nps-key"
    assert a.follow_redirects is True and b.follow_redirects is False


def test_closing_one_client_never_closes_the_shared_pool(monkeypatch) -> None:
    # One client's close()/context-exit must not tear down the pool every other
    # client shares — the shared transport's close() override must never reach
    # the real HTTPTransport.close(). Proven directly: record any call to the
    # parent close, then close a built client.
    calls: list[bool] = []
    monkeypatch.setattr(httpx.HTTPTransport, "close", lambda self: calls.append(True), raising=True)
    victim = _http.build_client()
    victim.close()
    assert calls == []  # the override swallowed it; the shared pool survives
