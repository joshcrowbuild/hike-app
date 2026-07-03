"""DEM acquisition helpers — the reproducible half of the elevation durability fix.

Elevation "kept disappearing" because the 3DEP DEM raster lived only in a transient
local worktree and was lost on prune, leaving `usgs-3dep` with no sampler and the
corpus elevation-less. The durable answer is a checked-in **manifest** (per-region
USGS-3DEP tile list + URLs + optional checksums) plus a reproducible fetch, so any
environment can re-obtain the exact DEM. This module is the pure core — tile math,
URL construction, manifest parsing, checksum verification — kept import-light (stdlib
only) so it's unit-testable without rasterio or network. `scripts/fetch_dem.py` is the
thin CLI that adds the actual download + merge/clip (which needs rasterio).

USGS 3DEP 1/3-arc-second tiles are named by their **NW corner** integer degree:
`n{lat}w{lon}` spans latitude [lat-1, lat] and longitude [-lon, -lon+1]. The current
staged GeoTIFFs live at a stable S3 path (`USGS_13_TILE_BASE`).
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Stable public URL for the "current" staged 1/3-arc-second GeoTIFFs (The National Map).
USGS_13_TILE_BASE = "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/13/TIFF/current"

# Repo-root-relative manifest path (checked in; the raster it describes is NOT — it
# lands under gitignored data/).
MANIFEST_PATH = "regions/dem_manifest.json"


def tiles_for_bbox(
    west: float, south: float, east: float, north: float, *, eps: float = 1e-9
) -> list[str]:
    """The USGS-3DEP 1/3-arc-second tile names covering a `[west, south, east, north]`
    bbox (the geojson `properties.bbox` order). Cells that a bbox edge only *touches*
    (zero-area overlap, e.g. an east edge landing exactly on an integer meridian) are
    excluded via `eps`, so a boundary-aligned region doesn't pull a whole extra tile.

    Each returned name `n{lat}w{lon}` is a 1°×1° tile whose NW corner is at integer
    (lat, -lon). West longitudes are negative in the bbox; the name carries their
    absolute value. Sorted for a stable, diff-friendly manifest."""
    if not (west < east and south < north):
        raise ValueError(f"degenerate bbox: [{west}, {south}, {east}, {north}]")
    lat_lo = math.floor(south + eps)
    lat_hi = math.ceil(north - eps)
    lon_lo = math.floor(west + eps)
    lon_hi = math.ceil(east - eps)
    tiles: list[str] = []
    for lat_cell in range(lat_lo, lat_hi):  # cell covers [lat_cell, lat_cell + 1]
        nw_lat = lat_cell + 1
        for lon_cell in range(lon_lo, lon_hi):  # cell covers [lon_cell, lon_cell + 1]
            nw_lon = lon_cell  # negative in CONUS; the NW corner's longitude
            ns = "n" if nw_lat >= 0 else "s"
            ew = "w" if nw_lon < 0 else "e"
            tiles.append(f"{ns}{abs(nw_lat):02d}{ew}{abs(nw_lon):03d}")
    return sorted(tiles)


def usgs_13_tile_url(tile: str, *, base_url: str = USGS_13_TILE_BASE) -> str:
    """The download URL for a 1/3-arc-second tile, e.g.
    `.../current/n39w079/USGS_13_n39w079.tif`."""
    return f"{base_url}/{tile}/USGS_13_{tile}.tif"


def sha256_file(path: str | Path, *, chunk_bytes: int = 1 << 20) -> str:
    """Streaming SHA-256 of a file (chunked so a multi-GB raster doesn't load into
    memory). Hex digest — the manifest's checksum format."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk_bytes), b""):
            h.update(block)
    return h.hexdigest()


@dataclass(frozen=True)
class ChecksumResult:
    """Outcome of verifying a file against an expected checksum. `expected is None`
    means the manifest hadn't recorded one yet (first fetch) — `ok` is True (nothing
    to contradict) but `computed` carries the value the operator should record."""

    path: str
    computed: str
    expected: str | None
    ok: bool


def verify_checksum(path: str | Path, expected: str | None) -> ChecksumResult:
    """Compute a file's SHA-256 and compare to `expected`. A missing `expected`
    (manifest not yet populated) is not a failure — it's the honest "record me"
    signal (source-or-silence: we never fabricate a checksum). A present-but-mismatched
    checksum IS a failure (`ok=False`), the corruption/tamper guard reproducibility
    exists for."""
    computed = sha256_file(path)
    ok = expected is None or computed.lower() == expected.lower()
    return ChecksumResult(path=str(path), computed=computed, expected=expected, ok=ok)


def load_manifest(path: str | Path = MANIFEST_PATH) -> dict[str, Any]:
    """Parse the DEM manifest JSON. Fail loud (FileNotFoundError / JSONDecodeError) —
    a fetch driven by a broken manifest should not proceed on guesses."""
    with open(path) as f:
        data: dict[str, Any] = json.load(f)
    return data


def region_entry(manifest: dict[str, Any], region: str) -> dict[str, Any]:
    """The manifest entry for a region, or a KeyError naming what IS declared — so a
    typo'd/unlisted region fails loud with an actionable message rather than a bare
    KeyError."""
    regions = manifest.get("regions", {})
    if region not in regions:
        known = ", ".join(sorted(regions)) or "(none)"
        raise KeyError(f"region {region!r} not in DEM manifest; declared: {known}")
    entry: dict[str, Any] = regions[region]
    return entry


def tile_base_url(manifest: dict[str, Any]) -> str:
    """The manifest's tile base URL, defaulting to the USGS 3DEP staged-TIFF path."""
    base: str = manifest.get("tile_base_url") or USGS_13_TILE_BASE
    return base
