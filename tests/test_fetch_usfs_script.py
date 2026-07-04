"""Tests for scripts/fetch_usfs.py's CLI plumbing — region bbox lookup and the
--dry-run plan. Network- and geopandas-free: --dry-run returns before either is
touched, matching scripts/fetch_dem.py's --dry-run contract.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_MOD_PATH = _REPO / "scripts" / "fetch_usfs.py"
_spec = importlib.util.spec_from_file_location("fetch_usfs", _MOD_PATH)
assert _spec and _spec.loader
fetch_usfs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fetch_usfs)


def test_region_bbox_reads_from_region_geojson() -> None:
    bbox = fetch_usfs._region_bbox("shenandoah-gwj")
    assert bbox == [-79.4, 37.8, -78.0, 39.1]


def test_region_bbox_unknown_region_fails_loud() -> None:
    with pytest.raises((FileNotFoundError, SystemExit)):
        fetch_usfs._region_bbox("atlantis")


def test_dry_run_prints_plan_without_region(capsys: pytest.CaptureFixture[str]) -> None:
    rc = fetch_usfs._cmd_fetch(region=None, dry_run=True, write_manifest=False)
    assert rc == 0
    out = capsys.readouterr().out
    assert "data.fs.usda.gov" in out
    assert "data/usfs/trails.geojson" in out
    assert "dry-run" in out


def test_dry_run_prints_region_clip_plan(capsys: pytest.CaptureFixture[str]) -> None:
    rc = fetch_usfs._cmd_fetch(region="shenandoah-gwj", dry_run=True, write_manifest=False)
    assert rc == 0
    out = capsys.readouterr().out
    assert "shenandoah-gwj" in out
    assert "-79.4" in out


def test_dry_run_unknown_region_fails_loud() -> None:
    # _region_bbox fails loud with the natural FileNotFoundError (mirrors
    # scripts/fetch_dem.py's _region_bbox, which does the same) — not swallowed into
    # a plan that silently proceeds without a region.
    with pytest.raises(FileNotFoundError):
        fetch_usfs._cmd_fetch(region="atlantis", dry_run=True, write_manifest=False)
