"""Tests for scripts/fetch_dem.py's DEM-clip buffer — the bbox-edge null-profile fix.

Trails that cross a region's ingest bbox (spurs exiting a park, connectors) used to
run off the edge of a bbox-tight DEM raster and drop to a null elevation profile
(confirmed for the Prince William Forest / Douthat nulls, 2026-07-14). fetch_dem now
buffers the bbox on every side before selecting tiles and clipping the raster.
Network- and rasterio-free: these exercise the pure bbox math only.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from ingestion import dem

_REPO = Path(__file__).resolve().parent.parent
_MOD_PATH = _REPO / "scripts" / "fetch_dem.py"
_spec = importlib.util.spec_from_file_location("fetch_dem", _MOD_PATH)
assert _spec and _spec.loader
fetch_dem = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fetch_dem)


def test_buffer_bbox_expands_every_side() -> None:
    # Prince William Forest's bbox, buffered by the default ~3 km margin.
    assert fetch_dem._buffer_bbox([-77.46, 38.53, -77.3, 38.66], buffer_deg=0.03) == [
        -77.49,
        38.5,
        -77.27,
        38.69,
    ]


def test_buffer_bbox_default_margin_is_outward_on_all_sides() -> None:
    west, south, east, north = fetch_dem._buffer_bbox([-79.9, 37.8, -79.72, 38.06])
    assert west < -79.9 and south < 37.8 and east > -79.72 and north > 38.06


def test_buffer_pulls_adjacent_tile_when_bbox_edge_is_within_the_margin() -> None:
    # A bbox whose north edge sits just below an integer degree covers a single tile
    # raw, but the buffer crosses the 39°N cell boundary and must pull the tile above —
    # exactly the boundary-crossing coverage the buffer exists to restore.
    raw = [-78.5, 38.9, -78.4, 38.99]  # entirely within the 38–39°N cell
    assert dem.tiles_for_bbox(*raw) == ["n39w079"]
    buffered = dem.tiles_for_bbox(*fetch_dem._buffer_bbox(raw))
    assert "n40w079" in buffered  # buffer crossed 39°N into the next cell


def test_buffer_keeps_confirmed_regions_within_existing_tiles() -> None:
    # PWF (1 tile) and Douthat (2 tiles) must NOT need a new tile once buffered — the
    # margin stays inside their 1°×1° source tiles, so no manifest re-init is required.
    assert dem.tiles_for_bbox(*fetch_dem._buffer_bbox([-77.46, 38.53, -77.3, 38.66])) == ["n39w078"]
    assert dem.tiles_for_bbox(*fetch_dem._buffer_bbox([-79.9, 37.8, -79.72, 38.06])) == [
        "n38w080",
        "n39w080",
    ]
