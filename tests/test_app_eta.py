"""Tests for the grade-aware pedestrian ETA (Epic 032) — the per-segment integral
that replaces flat whole-route Naismith. Pure/hermetic: no DB, no network; drives
`api.app._grade_time_factor` / `_estimated_duration_min` directly with synthetic
distance/elevation arrays (planimetric horizontal ground distance, matching
`ingestion/elevation.py`'s convention).

Ported curve: Valhalla (github.com/valhalla/valhalla), `src/sif/pedestriancost.cc`,
`kGradeBasedSpeedFactor`. MIT license, Copyright (c) 2018 Valhalla contributors /
Mapzen. See `docs/epics/epic-032-grade-aware-eta.md` for the port-vs-call verdict
and the independent BRouter+CoMaps Tobler second opinion the S3 oracle below
cross-checks against — re-derived here from the published formula, not copied
from either project's source (both are cross-check-only in this lane; see the
epic's license gate).
"""

from __future__ import annotations

import inspect
import math
import pathlib

import pytest

import api.app as app_mod
from api.app import (
    _GRADE_BREAKPOINTS_PCT,
    _GRADE_TIME_FACTORS,
    _elevation_profile,
    _estimated_duration_min,
    _grade_time_factor,
)


def _constant_grade_profile(
    total_m: float, grade_pct: float, n_samples: int = 6
) -> tuple[list[float], list[float]]:
    """An evenly-spaced profile of `n_samples` points over `total_m` horizontal
    ground distance at a constant `grade_pct` (so every merged segment resolves to
    exactly the same grade, regardless of the coarsening window)."""
    distances = [total_m * i / (n_samples - 1) for i in range(n_samples)]
    elevations = [600.0 + d * grade_pct / 100.0 for d in distances]
    return distances, elevations


# ── S1: the ported Valhalla grade→time-factor curve ─────────────────────────


def test_curve_constants_have_16_entries_and_flat_breakpoint_is_unity():
    assert len(_GRADE_BREAKPOINTS_PCT) == 16
    assert len(_GRADE_TIME_FACTORS) == 16
    flat_index = _GRADE_BREAKPOINTS_PCT.index(0.0)
    assert _GRADE_TIME_FACTORS[flat_index] == 1.00


def test_attribution_names_source_file_license_and_project():
    # AC-1.2: the port must carry its provenance — a silently-dropped attribution
    # header would violate the MIT license gate this epic ports code under.
    source = inspect.getsource(app_mod)
    assert "pedestriancost" in source
    assert "MIT" in source
    assert "Valhalla" in source


def test_grade_time_factor_exact_breakpoints_return_exact_factors():
    assert _grade_time_factor(0.0) == 1.00
    assert _grade_time_factor(-3.0) == 0.88
    assert _grade_time_factor(15.0) == 2.50


def test_grade_time_factor_interpolates_between_breakpoints():
    assert 0.88 < _grade_time_factor(-4.0) < 0.97


def test_grade_time_factor_extrapolates_past_steep_descent_endpoint():
    # Clamping would be a defect: it would make a -40% descent read as fast as a
    # -10% one. A real descent keeps getting slower past the tabulated endpoint.
    assert _grade_time_factor(-20.0) > _grade_time_factor(-10.0)
    assert _grade_time_factor(-20.0) > 1.33


def test_grade_time_factor_extrapolates_past_steep_ascent_endpoint():
    assert _grade_time_factor(30.0) > _grade_time_factor(15.0)
    assert _grade_time_factor(30.0) > 2.50


# ── S2: the per-segment grade-aware integral ────────────────────────────────


def test_estimated_duration_min_has_exactly_one_definition_and_one_call_site():
    # AC-2.1: the old two-scalar (distance_m, gain_m) signature must be fully
    # gone — grep api/ for stray callers still on the old contract.
    api_dir = pathlib.Path(__file__).resolve().parent.parent / "api"
    hits = [
        (path, lineno)
        for path in sorted(api_dir.rglob("*.py"))
        for lineno, line in enumerate(path.read_text().splitlines(), start=1)
        if "_estimated_duration_min" in line
    ]
    assert len(hits) == 2, hits


def test_flat_profile_yields_the_honest_flat_pace():
    distances, elevations = _constant_grade_profile(5000.0, 0.0)
    assert _estimated_duration_min(distances, elevations) == pytest.approx(60.0)


def test_ascent_takes_longer_than_flat():
    flat_d, flat_e = _constant_grade_profile(5000.0, 0.0)
    climb_d, climb_e = _constant_grade_profile(5000.0, 8.0)
    assert _estimated_duration_min(climb_d, climb_e) > _estimated_duration_min(flat_d, flat_e)


def test_steeper_ascent_takes_longer_than_gentler_ascent():
    gentle_d, gentle_e = _constant_grade_profile(5000.0, 3.0)
    steep_d, steep_e = _constant_grade_profile(5000.0, 10.0)
    assert _estimated_duration_min(steep_d, steep_e) > _estimated_duration_min(gentle_d, gentle_e)


def test_gentle_descent_is_faster_than_flat():
    flat_d, flat_e = _constant_grade_profile(5000.0, 0.0)
    desc_d, desc_e = _constant_grade_profile(5000.0, -3.0)
    assert _estimated_duration_min(desc_d, desc_e) < _estimated_duration_min(flat_d, flat_e)


def test_steep_descent_is_slower_than_flat():
    flat_d, flat_e = _constant_grade_profile(5000.0, 0.0)
    desc_d, desc_e = _constant_grade_profile(5000.0, -20.0)
    assert _estimated_duration_min(desc_d, desc_e) > _estimated_duration_min(flat_d, flat_e)


def test_dem_jitter_within_a_segment_does_not_swing_the_estimate():
    # AC-2.6: two profiles with identical endpoints + net gain, one smooth and one
    # with +-2 m per-sample jitter, must land within 5% of each other — the
    # _ETA_MIN_SEGMENT_M coarsening window absorbs the jitter before grading.
    n = 60
    total_m = 900.0
    distances = [total_m * i / (n - 1) for i in range(n)]
    smooth = [600.0 + d * 0.08 for d in distances]
    jittered = [e + (2.0 if i % 2 == 0 else -2.0) for i, e in enumerate(smooth)]
    jittered[0] = smooth[0]
    jittered[-1] = smooth[-1]
    smooth_min = _estimated_duration_min(distances, smooth)
    jittered_min = _estimated_duration_min(distances, jittered)
    assert jittered_min == pytest.approx(smooth_min, rel=0.05)


def test_empty_and_single_sample_profiles_return_zero():
    assert _estimated_duration_min([], []) == 0.0
    assert _estimated_duration_min([0.0], [600.0]) == 0.0


def test_zero_total_horizontal_distance_returns_zero():
    # Duplicate-point degenerate case: no ground covered, no time fabricated.
    assert _estimated_duration_min([0.0, 0.0, 0.0], [600.0, 650.0, 600.0]) == 0.0


def test_duplicated_interior_points_are_skipped_without_dividing_by_zero():
    distances = [0.0, 100.0, 100.0, 200.0]
    elevations = [600.0, 610.0, 610.0, 620.0]
    result = _estimated_duration_min(distances, elevations)
    assert math.isfinite(result)
    assert result > 0.0


def test_full_profile_still_exposes_a_finite_estimated_duration_min():
    # AC-2.8: the ElevationProfile contract (field name, float type, presence) is
    # unchanged by the computation swap underneath it.
    row = {
        "profile_distances_m": [0.0, 100.0, 250.0, 400.0],
        "profile_elevations_m": [600.0, 680.0, 900.0, 850.0],
        "elev_source": "usgs-3dep",
        "elev_resolution_m": 20.0,
    }
    profile = _elevation_profile(row)
    assert profile is not None
    assert isinstance(profile.estimated_duration_min, float)
    assert math.isfinite(profile.estimated_duration_min)


# ── S3: speed-vs-grade oracle — independent BRouter+CoMaps Tobler cross-check ──


def _tobler_kmh(grade_pct: float) -> float:
    """CoMaps' flat-anchored form of Tobler's hiking function, re-derived from the
    published formula (cross-check-only — never copied as product code)."""
    g = grade_pct / 100.0
    return 5.0 * math.exp(3.5 * (0.05 - abs(g + 0.05)))


def _our_kmh(grade_pct: float, total_m: float = 4000.0) -> float:
    distances, elevations = _constant_grade_profile(total_m, grade_pct)
    hours = _estimated_duration_min(distances, elevations) / 60.0
    return (total_m / 1000.0) / hours


_ORACLE_GRADES = (-40.0, -30.0, -20.0, -10.0, -5.0, 0.0, 10.0, 20.0, 30.0, 40.0)


def test_flat_anchor_is_honest_5kmh_for_both_models():
    assert _our_kmh(0.0) == pytest.approx(5.0)
    assert _tobler_kmh(0.0) == pytest.approx(5.0, rel=0.02)


def test_descent_sweet_spot_is_faster_than_flat_for_both_models():
    # Flat Naismith can never produce this — it pins descent at the flat pace.
    assert _our_kmh(-3.0) > 5.0
    assert _our_kmh(-5.0) > 5.0
    assert _tobler_kmh(-5.0) > 5.0  # Tobler's peak sits near -5%


def test_ascent_speed_is_monotonically_decreasing():
    ascent_grades = (0.0, 10.0, 20.0, 30.0, 40.0)
    speeds = [_our_kmh(g) for g in ascent_grades]
    assert all(a > b for a, b in zip(speeds, speeds[1:]))


def test_ascent_speed_is_more_conservative_than_tobler():
    # The Valhalla-DIN curve is the deliberately slower/more-conservative sibling
    # on ascent (e.g. at +10% ours is ~2.7 km/h vs Tobler's ~3.5 km/h) — the ~1%
    # agreement noted in the brief is between BRouter and CoMaps (both Tobler);
    # Valhalla-DIN is not expected to match that closely.
    for g in (10.0, 20.0, 30.0, 40.0):
        assert _our_kmh(g) <= _tobler_kmh(g)


def test_our_model_and_tobler_agree_on_order_of_magnitude_not_precision():
    for g in _ORACLE_GRADES:
        ratio = _our_kmh(g) / _tobler_kmh(g)
        assert 0.5 < ratio < 2.0, f"grade={g}: our={_our_kmh(g)} tobler={_tobler_kmh(g)}"
