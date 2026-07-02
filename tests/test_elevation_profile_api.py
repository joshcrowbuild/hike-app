"""Tests for `api.app._elevation_profile` / `_estimated_duration_min` — the API-layer
derivation that fills the empty "Viability" numbers (finding #2 of the 2026-07-02 UX
eval). Pure/hermetic: no DB, no rasterio — a plain row dict stands in for the graph
read, matching the shape `graph.queries.trail_detail`'s projection returns.
"""

from __future__ import annotations

import pytest

from api.app import _elevation_profile, _estimated_duration_min

# A known sample sequence: 600 -> 680 (+80) -> 900 (+220) -> 898 (-2, sub-threshold
# DEM noise, NOT credited — the hysteresis ref stays at 900) -> 850 (-50 net from the
# still-900 ref, a real descent). Only the two upward moves clear the 3 m noise
# threshold, so total_gain_m must be exactly 300.0, never inflated by the -2 wobble.
_ROW = {
    "profile_distances_m": [0.0, 100.0, 250.0, 300.0, 400.0],
    "profile_elevations_m": [600.0, 680.0, 900.0, 898.0, 850.0],
    "elev_source": "usgs-3dep",
    "elev_resolution_m": 20.0,
}


def test_total_gain_sums_only_positive_deltas_above_the_noise_threshold():
    profile = _elevation_profile(_ROW)
    assert profile is not None
    assert profile.total_gain_m == 300.0  # 80 + 220; the -2 sub-threshold dip ignored
    assert profile.total_loss_m == 50.0  # 900(ref)->850 real descent; -2 dip not credited
    assert profile.source == "usgs-3dep"


def test_no_samples_yields_null_profile():
    row = {
        "profile_distances_m": None,
        "profile_elevations_m": None,
        "elev_source": None,
        "elev_resolution_m": None,
    }
    assert _elevation_profile(row) is None


def test_mismatched_sample_arrays_yield_null_profile():
    row = {
        "profile_distances_m": [0.0, 100.0],
        "profile_elevations_m": [600.0],  # length mismatch — a data-integrity anomaly
        "elev_source": "usgs-3dep",
        "elev_resolution_m": 20.0,
    }
    assert _elevation_profile(row) is None


def test_missing_source_yields_null_profile_even_with_samples():
    row = {**_ROW, "elev_source": None}
    assert _elevation_profile(row) is None


def test_estimated_duration_min_is_monotonic_with_distance():
    short = _estimated_duration_min(distance_m=1_000.0, gain_m=0.0)
    long = _estimated_duration_min(distance_m=5_000.0, gain_m=0.0)
    assert long > short


def test_estimated_duration_min_is_monotonic_with_gain():
    flat = _estimated_duration_min(distance_m=1_000.0, gain_m=0.0)
    steep = _estimated_duration_min(distance_m=1_000.0, gain_m=600.0)
    assert steep > flat


def test_estimated_duration_min_matches_naismiths_rule():
    # Classic Naismith: 5 km/h flat pace + 1 hour per 600 m ascent.
    # 5 km at 5 km/h = 60 min; 600 m ascent = +60 min. Total 120 min.
    assert _estimated_duration_min(distance_m=5_000.0, gain_m=600.0) == pytest.approx(120.0)


def test_estimated_duration_min_present_on_a_full_profile():
    profile = _elevation_profile(_ROW)
    assert profile is not None
    # distance = 400 m = 0.4 km; base = 0.4/5*60 = 4.8 min; ascent = 300 m * 0.1 = 30 min.
    assert profile.estimated_duration_min == pytest.approx(34.8)
