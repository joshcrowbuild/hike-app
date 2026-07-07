"""DEM acquisition helpers — pure tile math, URL/checksum, manifest parsing.

Hermetic (stdlib only): no rasterio, no network, no download. Guards the reproducible
half of the elevation durability fix — the tile-coverage math the manifest is built on
and the checksum honesty (never fabricate one) the fetch depends on.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ingestion import dem

_REPO_ROOT = Path(__file__).resolve().parent.parent


# ── tiles_for_bbox ──────────────────────────────────────────────────────────


def test_tiles_for_bbox_shenandoah() -> None:
    # [-79.4, 37.8, -78.0, 39.1] → lat cells 38/39/40 × lon cells w079/w080.
    tiles = dem.tiles_for_bbox(-79.4, 37.8, -78.0, 39.1)
    assert tiles == [
        "n38w079",
        "n38w080",
        "n39w079",
        "n39w080",
        "n40w079",
        "n40w080",
    ]


def test_tiles_for_bbox_single_cell() -> None:
    # Richmond [-78.0, 37.2, -77.0, 37.9] sits inside one NW-corner cell.
    assert dem.tiles_for_bbox(-78.0, 37.2, -77.0, 37.9) == ["n38w078"]


def test_tiles_for_bbox_excludes_zero_area_boundary_touch() -> None:
    # An east edge landing exactly on an integer meridian must NOT pull the next tile
    # (it's only touched, zero-area overlap). -78.0 exact → no w078 cell.
    tiles = dem.tiles_for_bbox(-79.4, 37.8, -78.0, 39.1)
    assert "n38w078" not in tiles and "n39w078" not in tiles


def test_tiles_for_bbox_names_are_nw_corner() -> None:
    # A point-ish bbox at (38.5, -78.5) is covered by the cell whose NW corner is
    # (39, -79): n39w079 spans lat [38,39], lon [-79,-78].
    assert dem.tiles_for_bbox(-78.6, 38.4, -78.4, 38.6) == ["n39w079"]


def test_tiles_for_bbox_rejects_degenerate() -> None:
    with pytest.raises(ValueError):
        dem.tiles_for_bbox(-78.0, 38.0, -78.0, 39.0)  # west == east


# ── URL construction ────────────────────────────────────────────────────────


def test_usgs_13_tile_url() -> None:
    url = dem.usgs_13_tile_url("n39w079")
    assert url == (
        "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/13/TIFF/"
        "current/n39w079/USGS_13_n39w079.tif"
    )


# ── checksums (honesty: never fabricate) ────────────────────────────────────


def test_verify_checksum_missing_expected_is_ok_and_records(tmp_path: Path) -> None:
    f = tmp_path / "d.tif"
    f.write_bytes(b"raster-bytes")
    result = dem.verify_checksum(f, None)
    # No recorded checksum yet → ok (nothing to contradict) but computed is surfaced.
    assert result.ok is True
    assert result.expected is None
    assert result.computed == dem.sha256_file(f)


def test_verify_checksum_match_and_mismatch(tmp_path: Path) -> None:
    f = tmp_path / "d.tif"
    f.write_bytes(b"raster-bytes")
    good = dem.sha256_file(f)
    assert dem.verify_checksum(f, good).ok is True
    assert dem.verify_checksum(f, "0" * 64).ok is False


# ── manifest ────────────────────────────────────────────────────────────────


def test_manifest_tiles_match_bbox_math() -> None:
    # The checked-in manifest's declared tile list must equal what the bbox math yields
    # for each region — so a stale hand-edit can't silently under/over-cover a region.
    manifest = dem.load_manifest(_REPO_ROOT / dem.MANIFEST_PATH)
    for region, entry in manifest["regions"].items():
        west, south, east, north = entry["bbox"]
        expected = dem.tiles_for_bbox(west, south, east, north)
        declared = [t["name"] for t in entry["tiles"]]
        assert sorted(declared) == expected, f"{region} tile list drifted from bbox"


def test_manifest_output_paths_under_gitignored_data() -> None:
    manifest = dem.load_manifest(_REPO_ROOT / dem.MANIFEST_PATH)
    for entry in manifest["regions"].values():
        assert entry["output"].startswith("data/dem/")  # never committed


def test_manifest_bbox_contains_region_geojson() -> None:
    # The manifest bbox must CONTAIN the region's geojson bbox — equality is too
    # strict: OSM ways intersecting the region bbox can have centroids outside it,
    # so the DEM clip may carry a small pad or those trails lose elevation (the
    # 2026-07-07 peaks-of-otter 78%-coverage gate trip). The pad is bounded so a
    # typo'd bbox still fails loud.
    max_pad_deg = 0.25
    manifest = dem.load_manifest(_REPO_ROOT / dem.MANIFEST_PATH)
    for region, entry in manifest["regions"].items():
        geojson = json.loads((_REPO_ROOT / "regions" / f"{region}.geojson").read_text())
        mw, ms, me, mn = entry["bbox"]
        rw, rs, re_, rn = geojson["properties"]["bbox"]
        assert mw <= rw and ms <= rs and me >= re_ and mn >= rn, (
            f"{region}: manifest bbox must contain the region bbox"
        )
        assert (rw - mw) <= max_pad_deg and (rs - ms) <= max_pad_deg, region
        assert (me - re_) <= max_pad_deg and (mn - rn) <= max_pad_deg, region


def test_region_entry_unknown_fails_loud() -> None:
    manifest = dem.load_manifest(_REPO_ROOT / dem.MANIFEST_PATH)
    with pytest.raises(KeyError):
        dem.region_entry(manifest, "atlantis")
