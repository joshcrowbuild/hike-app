"""Tests for ingestion.elevation — densify + gain/loss/grade + source-or-silence.

Pure (no rasterio): the DEM is replaced by a fake `ElevationSampler` so the
profile math runs in the lean CI leg. A synthetic hill of known gain is asserted
within tolerance (Epic 017 AC-3.2); missing coverage yields `None`, never a faked
curve (Rule #1 / D3).
"""

from __future__ import annotations

from ingestion.elevation import (
    build_profile,
    build_profile_from_wkt,
    compute_gain_loss_grade,
    densify,
    haversine_m,
)

# A ~0.10° lon span at 38.5°N — used to size known elevations against real distance.
_LON0 = -78.30
_LAT = 38.50


class _Ramp:
    """A monotonic climb: elevation rises linearly with longitude (0 m at _LON0 to
    1000 m at _LON0 + 0.10°)."""

    def sample(self, lon: float, lat: float) -> float | None:
        return (lon - _LON0) * 10_000.0


class _Tent:
    """Up then down: a 1000 m peak at the midpoint, 0 m at both ends."""

    def __init__(self, mid: float) -> None:
        self.mid = mid

    def sample(self, lon: float, lat: float) -> float | None:
        return 1000.0 - abs(lon - self.mid) * 10_000.0


class _NoCoverage:
    def sample(self, lon: float, lat: float) -> float | None:
        return None


class _HalfCoverage:
    """Covers only the western half (lon < mid) — drives the partial-coverage path."""

    def __init__(self, mid: float) -> None:
        self.mid = mid

    def sample(self, lon: float, lat: float) -> float | None:
        return 100.0 if lon < self.mid else None


# ── haversine + densify ───────────────────────────────────────────────────────


def test_haversine_one_degree_latitude_is_about_111km():
    d = haversine_m((0.0, 0.0), (0.0, 1.0))
    assert abs(d - 111_195) / 111_195 < 0.01


def test_densify_inserts_points_and_tracks_distance():
    pts = densify([(_LON0, _LAT), (_LON0 + 0.10, _LAT)], resolution_m=50.0)
    assert pts[0][2] == 0.0
    dists = [d for _, _, d in pts]
    assert dists == sorted(dists)  # monotonic
    assert len(pts) > 100  # ~8.7 km / 50 m
    assert abs(dists[-1] - haversine_m((_LON0, _LAT), (_LON0 + 0.10, _LAT))) < 1.0


def test_densify_handles_degenerate_input():
    assert densify([], 10.0) == []
    assert densify([(1.0, 2.0)], 10.0) == [(1.0, 2.0, 0.0)]


# ── gain/loss/grade denoise (D2) ──────────────────────────────────────────────


def test_gain_loss_ignores_sub_threshold_noise():
    # The ±2 m wobble is below the 3 m threshold and must not count; only the climb does.
    gain, loss, _ = compute_gain_loss_grade(
        [0, 10, 20, 30, 40], [0.0, 2.0, 0.0, 2.0, 100.0], noise_threshold_m=3.0
    )
    assert abs(gain - 100.0) < 1e-6
    assert loss == 0.0


def test_max_grade_is_steepest_rise_over_run():
    _, _, grade = compute_gain_loss_grade([0, 100], [0.0, 50.0])
    assert abs(grade - 50.0) < 1e-6  # 50 m over 100 m = 50%


def test_max_grade_windowed_rejects_single_cell_spike():
    # Flat ground with one +4 m DEM spike at 40 m. Adjacent 20 m samples would report
    # 4/20 = 20%; the 100 m window washes the single cell out (the CRITICAL fix).
    dists = [0, 20, 40, 60, 80, 100, 120, 140, 160, 180, 200]
    elevs = [100, 100, 104, 100, 100, 100, 100, 100, 100, 100, 100.0]
    _, _, grade = compute_gain_loss_grade(dists, elevs, grade_window_m=100.0)
    assert grade < 6.0


def test_max_grade_still_captures_a_sustained_grade():
    # A real sustained 10% over the first 100 m must survive the windowing.
    dists = [0, 20, 40, 60, 80, 100, 120, 140]
    elevs = [0, 2, 4, 6, 8, 10, 10, 10.0]
    _, _, grade = compute_gain_loss_grade(dists, elevs, grade_window_m=100.0)
    assert 9.0 <= grade <= 11.0


# ── synthetic hill: known gain within tolerance (AC-3.2) ──────────────────────


def test_monotonic_climb_gain_matches_known_value():
    profile = build_profile([[(_LON0, _LAT), (_LON0 + 0.10, _LAT)]], _Ramp(), resolution_m=50.0)
    assert profile is not None
    assert 990.0 <= profile.total_gain_m <= 1000.5  # ~1000 m climb
    assert profile.total_loss_m == 0.0  # purely uphill
    assert 10.0 < profile.max_grade_pct < 13.0  # 1000 m / ~8.7 km
    assert profile.source == "usgs-3dep"
    assert len(profile.distances_m) == len(profile.elevations_m) > 2
    assert profile.distances_m[0] == 0.0


def test_up_then_down_reports_both_gain_and_loss():
    mid = _LON0 + 0.10
    profile = build_profile([[(_LON0, _LAT), (mid + 0.10, _LAT)]], _Tent(mid), resolution_m=50.0)
    assert profile is not None
    assert 990.0 <= profile.total_gain_m <= 1001.0
    assert 990.0 <= profile.total_loss_m <= 1001.0


# ── source-or-silence (Rule #1 / D3) ──────────────────────────────────────────


def test_no_coverage_returns_none():
    assert build_profile([[(_LON0, _LAT), (_LON0 + 0.10, _LAT)]], _NoCoverage()) is None


def test_coverage_below_threshold_returns_none():
    # Half-covered with a 0.6 floor → null (too sparse to be honest).
    mid = _LON0 + 0.05
    assert build_profile([[(_LON0, _LAT), (_LON0 + 0.10, _LAT)]], _HalfCoverage(mid)) is None


def test_partial_coverage_above_threshold_returns_profile():
    # Cover ~80% (mid at 0.08 of the 0.10 span) with a low floor → a profile over the span.
    mid = _LON0 + 0.08
    profile = build_profile(
        [[(_LON0, _LAT), (_LON0 + 0.10, _LAT)]], _HalfCoverage(mid), min_coverage=0.5
    )
    assert profile is not None
    assert all(e == 100.0 for e in profile.elevations_m)


def test_empty_geometry_returns_none():
    assert build_profile([], _Ramp()) is None
    assert build_profile([[]], _Ramp()) is None


# ── from WKT (the 3DEP source's entry point) ──────────────────────────────────


def test_build_profile_from_wkt_ramp():
    wkt = f"LINESTRING({_LON0} {_LAT}, {_LON0 + 0.10} {_LAT})"
    profile = build_profile_from_wkt(wkt, _Ramp(), resolution_m=50.0)
    assert profile is not None and profile.total_gain_m > 900.0


def test_build_profile_from_wkt_none_for_missing_geometry():
    assert build_profile_from_wkt(None, _Ramp()) is None
    assert build_profile_from_wkt("POINT(1 2)", _Ramp()) is None
