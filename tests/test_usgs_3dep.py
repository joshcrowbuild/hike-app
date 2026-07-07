"""Tests for the USGS-3DEP enrichment source (Epic 017 S2/S3).

Two layers, matching the design:
- The adapter logic (fact emission, source-or-silence, from_config) is tested with
  a FAKE `ElevationSampler` — no raster, so it runs in the lean CI leg.
- `RasterioDEMSampler` is tested against a generated fixture GeoTIFF, guarded by
  `importorskip("rasterio")` so a DEM-less env skips it cleanly (AC-2.1).
"""

from __future__ import annotations

import pytest

from graph.load import load_enrichment_facts
from ingestion.sources.base import CanonicalNode, ConflationRole, SourceKind
from ingestion.sources.usgs_3dep import ELEV_SOURCE, RasterioDEMSampler, UsgsThreeDEPSource
from orchestration.config import Settings

_WKT = "LINESTRING(-78.30 38.50, -78.20 38.50)"  # ~8.7 km west→east at 38.5°N

_EXPECTED_ATTRS = {
    "profile_distances_m",
    "profile_elevations_m",
    "total_gain_m",
    "total_loss_m",
    "max_grade_pct",
    "elev_source",
    "elev_resolution_m",
    "elev_version",
}


class _Ramp:
    """A monotonic 0→1000 m climb keyed on longitude."""

    def sample(self, lon: float, lat: float) -> float | None:
        return (lon + 78.30) * 10_000.0


class _NoCoverage:
    def sample(self, lon: float, lat: float) -> float | None:
        return None


class _Boom:
    def sample(self, lon: float, lat: float) -> float | None:
        raise RuntimeError("simulated raster I/O error")


# ── declarations + validation (the seam contract) ────────────────────────────


def test_source_declarations():
    src = UsgsThreeDEPSource(sampler=_Ramp())
    assert src.name == "usgs-3dep"
    assert src.kind is SourceKind.enrichment
    assert src.role is ConflationRole.enrich
    assert src.authority_tier == 1


def test_registered_in_registry():
    from ingestion.sources.registry import SOURCE_REGISTRY, known_source_names

    assert SOURCE_REGISTRY.get("usgs-3dep") is UsgsThreeDEPSource
    assert "usgs-3dep" in known_source_names()


# ── enrich emits the parallel-array + scalar facts (AC-3.1) ───────────────────


def test_enrich_emits_profile_facts():
    src = UsgsThreeDEPSource(sampler=_Ramp(), resolution_m=50.0)
    facts = src.enrich(CanonicalNode(canonical_id="ct:1", name="X", geom_wkt=_WKT))

    assert {f.attribute for f in facts} == _EXPECTED_ATTRS
    assert all(f.canonical_id == "ct:1" for f in facts)
    assert all(f.recorded_resolution == "50m" for f in facts)

    by = {f.attribute: f.value for f in facts}
    assert by["elev_source"] == ELEV_SOURCE
    assert isinstance(by["profile_distances_m"], list)
    assert isinstance(by["profile_elevations_m"], list)
    assert len(by["profile_distances_m"]) == len(by["profile_elevations_m"]) > 2
    assert by["total_gain_m"] > 900.0  # ~1000 m climb
    assert by["total_loss_m"] == 0.0
    assert by["elev_resolution_m"] == 50.0


def test_facts_round_trip_through_loader():
    src = UsgsThreeDEPSource(sampler=_Ramp(), resolution_m=50.0)
    facts = src.enrich(CanonicalNode(canonical_id="ct:1", name="X", geom_wkt=_WKT))
    calls: list[tuple[str, dict]] = []
    n = load_enrichment_facts(lambda c, p: calls.append((c, p)), facts)
    assert n == 1  # one node written
    cypher = calls[0][0]
    for attr in ("profile_distances_m", "total_gain_m", "elev_source", "elev_version"):
        assert attr in cypher


# ── source-or-silence: no fact rather than a faked curve (Rule #1 / D3) ───────


def test_enrich_no_geometry_is_silent():
    assert UsgsThreeDEPSource(sampler=_Ramp()).enrich(CanonicalNode("ct:1", "X")) == []


def test_enrich_no_coverage_is_silent():
    src = UsgsThreeDEPSource(sampler=_NoCoverage())
    assert src.enrich(CanonicalNode("ct:1", "X", geom_wkt=_WKT)) == []


def test_enrich_without_sampler_is_silent():
    assert UsgsThreeDEPSource(sampler=None).enrich(CanonicalNode("ct:1", "X", geom_wkt=_WKT)) == []


def test_enrich_swallows_sampler_errors():
    src = UsgsThreeDEPSource(sampler=_Boom())
    assert src.enrich(CanonicalNode("ct:1", "X", geom_wkt=_WKT)) == []


# ── from_config: DEM path is per-region; absent → graceful no-op, never a wipe ─


def test_nonpositive_resolution_fails_loud():
    # A misconfigured spacing must fail at construction, not surface as a swallowed
    # ZeroDivisionError → silent null later.
    with pytest.raises(ValueError, match="resolution_m must be positive"):
        UsgsThreeDEPSource(sampler=_Ramp(), resolution_m=0.0)


def test_from_config_without_dem_path_degrades_to_noop(caplog, tmp_path, monkeypatch):
    monkeypatch.chdir(
        tmp_path
    )  # hermetic: a real data/dem/{region}.tif on the dev box must not leak in
    # usgs-3dep is a default corpus source (so a re-ingest never forgets it), but
    # most regions have no DEM downloaded yet. from_config must not raise — a
    # region-scoped re-ingest without a DEM must complete normally and leave any
    # existing elevation untouched, never error or wipe it.
    src = UsgsThreeDEPSource.from_config(Settings.from_env({}))
    assert isinstance(src, UsgsThreeDEPSource)
    assert src._sampler is None
    assert src.enrich(CanonicalNode("ct:1", "X", geom_wkt=_WKT)) == []


def test_from_config_without_dem_path_logs_a_warning(caplog, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with caplog.at_level("WARNING"):
        UsgsThreeDEPSource.from_config(Settings.from_env({}))
    assert any("ADVENTURE_3DEP_DEM" in r.message for r in caplog.records)


def test_from_config_builds_with_dem_path(tmp_path):
    # Lazy: the DEM is not opened at construction, so a non-existent path is fine here.
    s = Settings.from_env(
        {"ADVENTURE_3DEP_DEM": str(tmp_path / "dem.tif"), "ADVENTURE_3DEP_RESOLUTION_M": "30"}
    )
    src = UsgsThreeDEPSource.from_config(s)
    assert isinstance(src, UsgsThreeDEPSource)
    assert src._resolution_m == 30.0


# ── RasterioDEMSampler against a fixture DEM (AC-2.1) — skipped without rasterio ─


def _write_fixture_dem(path) -> None:
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    width = height = 10
    res = 0.01  # degrees/pixel
    transform = from_origin(-78.30, 38.60, res, res)  # north-up, upper-left origin
    data = np.zeros((height, width), dtype="float32")
    for col in range(width):
        data[:, col] = col * 10.0  # elevation rises west → east (0 … 90 m)
    data[5, 5] = -9999.0  # a nodata cell
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
        nodata=-9999.0,
    ) as dataset:
        dataset.write(data, 1)


def test_rasterio_dem_sampler_reads_fixture(tmp_path):
    pytest.importorskip("rasterio")
    pytest.importorskip("numpy")
    path = tmp_path / "dem.tif"
    _write_fixture_dem(path)
    sampler = RasterioDEMSampler(str(path))
    try:
        west = sampler.sample(-78.295, 38.55)  # col 0 → 0 m
        east = sampler.sample(-78.205, 38.55)  # col 9 → 90 m
        assert west is not None and east is not None
        assert east > west
        assert sampler.sample(-79.0, 38.55) is None  # out of bounds → None
        assert sampler.sample(-78.245, 38.545) is None  # the nodata cell → None
    finally:
        sampler.close()


def test_rasterio_sampler_drives_a_real_profile(tmp_path):
    pytest.importorskip("rasterio")
    pytest.importorskip("numpy")
    path = tmp_path / "dem.tif"
    _write_fixture_dem(path)
    sampler = RasterioDEMSampler(str(path))
    try:
        src = UsgsThreeDEPSource(sampler=sampler, resolution_m=200.0, min_coverage=0.5)
        # A line fully inside the raster, west→east, so elevation climbs.
        wkt = "LINESTRING(-78.295 38.55, -78.205 38.55)"
        facts = src.enrich(CanonicalNode("ct:1", "X", geom_wkt=wkt))
        by = {f.attribute: f.value for f in facts}
        assert by["total_gain_m"] > 0.0  # real climb sampled from the DEM
    finally:
        sampler.close()
