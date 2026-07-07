"""Tests for ingestion.classify — table-driven parity for the three tag classifiers.

Covers Epic 026 AC-2.1 (path_grade), AC-2.2 (surface), AC-2.3 (foot_access), and the
empty-on-absent invariant (AC-2.4 / binding correction A1.1): a missing/unrecognized
tag must return "" and never a fabricated default.
"""

from __future__ import annotations

import pytest

from ingestion.classify import classify_foot_access, classify_path_grade, classify_surface

# ── classify_path_grade (AC-2.1) ───────────────────────────────────────────────

_PATH_GRADE_CASES = [
    # (tags, expected)
    ({"highway": "path", "sac_scale": "alpine_hiking"}, "expert"),
    ({"highway": "path", "sac_scale": "demanding_alpine_hiking"}, "expert"),
    ({"highway": "path", "sac_scale": "difficult_alpine_hiking"}, "expert"),
    ({"highway": "path", "trail_visibility": "horrible"}, "expert"),
    ({"highway": "path", "trail_visibility": "no"}, "expert"),
    ({"highway": "path", "trail_visibility": "very_bad"}, "expert"),
    ({"highway": "path", "sac_scale": "demanding_mountain_hiking"}, "difficult"),
    ({"highway": "path", "trail_visibility": "bad"}, "difficult"),
    ({"highway": "path", "trail_visibility": "poor"}, "difficult"),
    # No "normal" — every other scale/visibility combination is empty.
    ({"highway": "path", "sac_scale": "hiking"}, ""),
    ({"highway": "path", "sac_scale": "mountain_hiking"}, ""),
    ({"highway": "path", "trail_visibility": "excellent"}, ""),
    ({"highway": "path", "trail_visibility": "good"}, ""),
    ({"highway": "path", "trail_visibility": "intermediate"}, ""),
    ({"highway": "path", "trail_visibility": "unknown"}, ""),
    # Non-`path` highway → always empty, even with a scale/visibility tag.
    ({"highway": "footway", "sac_scale": "alpine_hiking"}, ""),
    ({"highway": "track", "trail_visibility": "horrible"}, ""),
    ({}, ""),
    # `path` but neither tag present → empty.
    ({"highway": "path"}, ""),
]


@pytest.mark.parametrize("tags,expected", _PATH_GRADE_CASES)
def test_classify_path_grade(tags, expected):
    assert classify_path_grade(tags) == expected


def test_classify_path_grade_never_returns_normal():
    # Explicit lock-in: sac_scale=hiking is the CoMaps "normal" case but there is no
    # positive/default grade in our enum (binding correction A1.1).
    result = classify_path_grade({"highway": "path", "sac_scale": "hiking"})
    assert result != "normal"
    assert result == ""


# ── classify_surface (AC-2.2) ──────────────────────────────────────────────────

_SURFACE_CASES = [
    ({"highway": "path", "surface": "asphalt"}, "paved_good"),
    ({"highway": "path", "surface": "ground", "surface:grade": "1"}, "unpaved_bad"),
    ({"highway": "path", "surface": "compacted"}, "unpaved_good"),
    ({"highway": "path", "smoothness": "impassable"}, "unpaved_bad"),
    ({"highway": "track", "smoothness": "bad"}, "unpaved_bad"),
    ({"highway": "path", "surface": "concrete:plates"}, "paved_good"),
    ({"4wd_only": "yes"}, "unpaved_bad"),
    ({"4wd_only": "recommended", "highway": "path"}, "unpaved_bad"),
    ({"surface": "asphalt"}, ""),  # no highway → guard fires, never paved_good
    ({"highway": "path"}, ""),  # no surface, no smoothness
    ({}, ""),
]


@pytest.mark.parametrize("tags,expected", _SURFACE_CASES)
def test_classify_surface(tags, expected):
    assert classify_surface(tags) == expected


def test_classify_surface_bad_grade_falls_back_to_default_not_crash():
    # A garbage surface:grade must not raise — falls back to the 2.0 default.
    result = classify_surface({"highway": "path", "surface": "ground", "surface:grade": "banana"})
    assert result == "unpaved_bad"  # ground is a veryBadSurface at the default grade


def test_classify_surface_compound_bad_value_matches_any_token():
    # Has() tokenizes on ;:/ — "sand/dirt" should match veryBadSurfaces via "sand".
    result = classify_surface({"highway": "path", "surface": "sand/dirt", "surface:grade": "1"})
    assert result == "unpaved_bad"


def test_classify_surface_ford_highway_ignored():
    # highway=ford is never assigned — treated as if highway were absent.
    result = classify_surface({"highway": "ford", "surface": "asphalt"})
    assert result == ""


# ── classify_foot_access (AC-2.3) ──────────────────────────────────────────────

_FOOT_ACCESS_CASES = [
    ({"foot": "yes"}, "yes"),
    ({"foot": "designated"}, "yes"),
    ({"foot": "permissive"}, "yes"),
    ({"foot": "destination"}, "yes"),
    ({"foot": "official"}, "yes"),
    ({"foot": "permit"}, "permit"),
    ({"foot": "private"}, "private"),
    ({"foot": "customers"}, "private"),
    ({"foot": "agricultural"}, "private"),
    ({"foot": "forestry"}, "private"),
    ({"foot": "delivery"}, "private"),
    ({"foot": "discouraged"}, "discouraged"),
    ({"foot": "no"}, "no"),
    ({"access": "yes"}, "yes"),
    ({"access": "private"}, "private"),
    ({"access": "no"}, "no"),
    ({"foot": "unicorn"}, ""),  # unrecognized → silence, never coerced to "yes"
    ({"access": "unicorn"}, ""),
    ({}, ""),  # neither tag present
]


@pytest.mark.parametrize("tags,expected", _FOOT_ACCESS_CASES)
def test_classify_foot_access(tags, expected):
    assert classify_foot_access(tags) == expected


def test_classify_foot_access_foot_beats_access():
    # foot is pedestrian-specific and wins over the more general access tag.
    assert classify_foot_access({"foot": "yes", "access": "private"}) == "yes"
    assert classify_foot_access({"foot": "no", "access": "yes"}) == "no"
