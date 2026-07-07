"""Tests for scripts/fetch_osm_pbf.py's CLI plumbing — the manifest lookup and
the --dry-run plan (Epic 036 AC-4.2). Network- and osmium-free: --dry-run
returns before either is touched, and --write-manifest's osmium import is
lazy (module-top import would break this file's collection if osmium were
absent), matching scripts/fetch_usfs.py's --dry-run contract.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_MOD_PATH = _REPO / "scripts" / "fetch_osm_pbf.py"
_spec = importlib.util.spec_from_file_location("fetch_osm_pbf", _MOD_PATH)
assert _spec and _spec.loader
fetch_osm_pbf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fetch_osm_pbf)


def test_dry_run_prints_plan_for_default_state(capsys: pytest.CaptureFixture[str]) -> None:
    rc = fetch_osm_pbf._cmd_fetch(state="virginia", dry_run=True, write_manifest=False)
    assert rc == 0
    out = capsys.readouterr().out
    assert "download.geofabrik.de" in out
    assert "virginia-latest.osm.pbf" in out
    assert "dry-run" in out


def test_dry_run_prints_plan_for_north_carolina(capsys: pytest.CaptureFixture[str]) -> None:
    rc = fetch_osm_pbf._cmd_fetch(state="north-carolina", dry_run=True, write_manifest=False)
    assert rc == 0
    out = capsys.readouterr().out
    assert "north-carolina-latest.osm.pbf" in out


def test_unknown_state_fails_loud_naming_it() -> None:
    with pytest.raises(SystemExit, match="unknown state 'atlantis'"):
        fetch_osm_pbf._cmd_fetch(state="atlantis", dry_run=True, write_manifest=False)


def test_dry_run_does_not_create_output_file() -> None:
    # Belt-and-suspenders: dry-run must never touch the filesystem for the
    # output path either, not just skip the network call.
    manifest = fetch_osm_pbf._load_manifest()
    extract = fetch_osm_pbf._find_extract(manifest, "virginia")
    output = _REPO / extract["output"]
    existed_before = output.exists()
    fetch_osm_pbf._cmd_fetch(state="virginia", dry_run=True, write_manifest=False)
    assert output.exists() == existed_before  # dry-run created nothing
