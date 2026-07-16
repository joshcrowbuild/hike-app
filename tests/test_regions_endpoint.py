"""GET /regions — the config-driven origin catalog (Phase 2).

Hermetic: no graph, no network — the endpoint is a plain read of `regions/*.geojson`.
Coverage:
  - the real committed region files parse and every named origin survives the trip;
  - a malformed region file is skipped (logged), never a 500 for the whole catalog;
  - over the rate limit → the same clean JSON 429 the rest of the edge serves.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

import api.app as app_mod
from orchestration.config import Settings


@pytest.fixture
def client(monkeypatch: Any) -> Any:
    c = TestClient(app_mod.app)
    c.__enter__()
    monkeypatch.setattr(app_mod, "_settings", Settings.from_env({}))
    try:
        yield c
    finally:
        c.__exit__(None, None, None)


def test_regions_serves_the_committed_catalog(client: Any) -> None:
    resp = client.get("/regions")
    assert resp.status_code == 200
    payload = resp.json()

    by_id = {r["region_id"]: r for r in payload["regions"]}
    # The core regions are always present with their committed origins; more regions
    # may be onboarded purely by adding regions/*.geojson (Phase 2), so assert a
    # superset, not an exact set — a new region must never break the catalog test.
    assert {"shenandoah-gwj", "richmond", "outer-banks"} <= set(by_id)

    shen = by_id["shenandoah-gwj"]
    assert shen["label"] == "Shenandoah"
    assert {o["key"] for o in shen["origins"]} == {"frontRoyal", "luray", "charlottesville"}
    front_royal = next(o for o in shen["origins"] if o["key"] == "frontRoyal")
    assert front_royal == {
        "key": "frontRoyal",
        "label": "Front Royal",
        "lat": 38.918,
        "lon": -78.194,
    }

    richmond = by_id["richmond"]
    assert richmond["label"] == "Richmond"
    assert {o["key"] for o in richmond["origins"]} == {"richmond"}

    obx = by_id["outer-banks"]
    assert obx["label"] == "Outer Banks"
    assert {o["key"] for o in obx["origins"]} == {"duck", "nagsHead", "hatteras", "ocracoke"}

    # sky-meadows: the last CoMaps-program region (config-only until an operator
    # runs the guarded ingest — see regions/README.md and the geojson's own
    # min_fetch_counts comment). Asserted explicitly so a future edit to the file
    # can't silently drop its origins without a test noticing.
    sky_meadows = by_id["sky-meadows"]
    assert sky_meadows["label"] == "Sky Meadows"
    assert {o["key"] for o in sky_meadows["origins"]} == {"skyMeadows", "paris", "delaplane"}


def test_regions_skips_a_malformed_file_without_500ing(
    tmp_path: Any, monkeypatch: Any, client: Any
) -> None:
    (tmp_path / "good.geojson").write_text(
        '{"properties": {"region_id": "good", "region_label": "Good", '
        '"origins": [{"key": "a", "label": "A", "lat": 1.0, "lon": 2.0}]}}'
    )
    (tmp_path / "bad.geojson").write_text("not json at all")

    import orchestration.regions as regions_mod

    monkeypatch.setattr(regions_mod, "REGIONS_DIR", tmp_path)

    resp = client.get("/regions")
    assert resp.status_code == 200
    payload = resp.json()
    assert [r["region_id"] for r in payload["regions"]] == ["good"]


def test_regions_over_limit_returns_clean_429(client: Any, monkeypatch: Any) -> None:
    monkeypatch.setenv("ADVENTURE_RATELIMIT_HEALTH", "2/hour")

    assert client.get("/regions").status_code == 200
    assert client.get("/regions").status_code == 200
    limited = client.get("/regions")

    assert limited.status_code == 429
    assert "retry-after" in {k.lower() for k in limited.headers}


# ── Epic 052 WP-5 — ETag + Cache-Control (design-system-v0.2 Part III.3) ─────


def test_regions_carries_etag_and_public_cache_control(client: Any) -> None:
    resp = client.get("/regions")
    assert resp.status_code == 200
    assert resp.headers["etag"].startswith('"') and resp.headers["etag"].endswith('"')
    assert "public" in resp.headers["cache-control"]
    assert "must-revalidate" in resp.headers["cache-control"]


def test_regions_conditional_get_with_matching_etag_returns_cheap_304(client: Any) -> None:
    first = client.get("/regions")
    etag = first.headers["etag"]

    second = client.get("/regions", headers={"if-none-match": etag})

    assert second.status_code == 304
    assert second.headers["etag"] == etag
    # A 304 carries no body — the whole point of "cheap" revalidation.
    assert second.content == b""


def test_regions_conditional_get_with_stale_etag_serves_the_full_body(client: Any) -> None:
    resp = client.get("/regions", headers={"if-none-match": '"not-the-real-etag"'})
    assert resp.status_code == 200
    assert resp.json()["regions"]  # the real catalog, not an empty 304 body
