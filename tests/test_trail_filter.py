"""Trail-worthiness filter tests (Lead 1) — calibrated on the live Front Royal corpus.

The fixtures use the *real* OSM tags observed on the offending ways (Overpass, Front
Royal bbox): "Leach Road" (track, access=private), "Path to School" (footway, dirt,
foot=yes), vs real trails ("Dickey Ridge Trail", path/ground) and fire roads
("Compton Gap Road", track). Precision matters: a fire road must NOT be dropped.
"""

from __future__ import annotations

from ingestion.trail_filter import is_trail_worthy

_TWO = [(-78.20, 38.90), (-78.19, 38.91)]
_MANY = [(-78.20, 38.90), (-78.198, 38.905), (-78.196, 38.91), (-78.194, 38.915)]


def _w(**tags):
    return dict(tags)


# ── keeps: real trails + fire roads ───────────────────────────────────────────


def test_keeps_real_path_trail():
    assert is_trail_worthy(_w(name="Dickey Ridge Trail", highway="path", surface="ground"), _MANY)


def test_keeps_unpaved_fire_road_track():
    # "Compton Gap Road" / "Mathews Arm Road" are real Shenandoah fire-road hikes.
    assert is_trail_worthy(_w(name="Compton Gap Road", highway="track"), _MANY)
    assert is_trail_worthy(_w(name="Snake Road", highway="track"), _MANY)


def test_keeps_school_named_real_trail():
    # "Hull School Trail" / "Meadows School Trail" are real trails — name has "School"
    # but the deny-list only fires on the "path to school" connector pattern.
    assert is_trail_worthy(_w(name="Hull School Trail", highway="path"), _MANY)


def test_keeps_private_track_with_public_foot_access():
    assert is_trail_worthy(
        _w(name="Old Mill Track", highway="track", access="private", foot="yes"), _MANY
    )


def test_keeps_two_point_path_segment():
    # Only 2-point *footways* are dropped; a 2-point path/track segment survives.
    assert is_trail_worthy(_w(name="Ridge Connector", highway="path"), _TWO)


# ── drops: urban / private / utility non-trails ───────────────────────────────


def test_drops_private_access_road():
    # "Leach Road": highway=track, access=private, no foot grant.
    assert not is_trail_worthy(_w(name="Leach Road", highway="track", access="private"), _MANY)


def test_drops_path_to_school_footway():
    # "Path to School": footway, surface=dirt, foot=yes — tags look trail-ish; the
    # NAME is the discriminator.
    assert not is_trail_worthy(
        _w(name="Path to School", highway="footway", surface="dirt", foot="yes"), _MANY
    )


def test_drops_sidewalk_by_footway_tag():
    assert not is_trail_worthy(
        _w(name="Haden Place Sidewalk", highway="footway", footway="sidewalk"), _MANY
    )


def test_drops_sidewalk_by_name():
    assert not is_trail_worthy(_w(name="Main Street Sidewalk", highway="footway"), _MANY)


def test_drops_driveway_and_ramp_names():
    assert not is_trail_worthy(_w(name="old driveway", highway="footway"), _MANY)
    assert not is_trail_worthy(_w(name="Wheelchair Ramp to garden", highway="footway"), _MANY)


def test_drops_two_point_footway_stub():
    assert not is_trail_worthy(_w(name="Connector", highway="footway"), _TWO)


def test_drops_unnamed():
    assert not is_trail_worthy(_w(highway="path"), _MANY)
    assert not is_trail_worthy(_w(name="   ", highway="path"), _MANY)
