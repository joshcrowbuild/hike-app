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
    # "Compton Gap Road" / "Mathews Arm Road" are real Shenandoah fire-road hikes. They
    # carry tiger:cfcc=A41 (the same road-class TIGER stamps on misimported state
    # routes) but NO numbered `ref` — proving the route filter keys on `ref`, not cfcc,
    # so it can't drop a genuine fire road.
    assert is_trail_worthy(
        _w(name="Compton Gap Road", highway="track", **{"tiger:cfcc": "A41"}), _MANY
    )
    assert is_trail_worthy(
        _w(name="Mathews Arm Road", highway="track", **{"tiger:cfcc": "A41", "ref": ""}), _MANY
    )


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


def test_keeps_public_wellness_trail():
    # A bare public "Wellness Trail" / "Wellness Loop" (municipal fitness loop) must
    # survive — only the institutional "Wellness <institution>" pattern is dropped.
    assert is_trail_worthy(_w(name="Wellness Trail", highway="path"), _MANY)
    assert is_trail_worthy(_w(name="Riverside Wellness Loop", highway="footway"), _MANY)


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


def test_drops_numbered_state_route_track():
    # "Little Loop Road" (ref=SR 652) / "Snake Road" (ref=SR 650): numbered VA state
    # routes TIGER mis-imported as highway=track — cars drive them, not hikes.
    assert not is_trail_worthy(_w(name="Little Loop Road", highway="track", ref="SR 652"), _MANY)
    assert not is_trail_worthy(_w(name="Snake Road", highway="track", ref="SR 650"), _MANY)


def test_drops_numbered_routes_by_ref_variants():
    # Space, hyphenated, and spelled-out "Route" forms OSM editors normalize TIGER into.
    refs = (
        "CR 600",
        "VA 55",
        "US 211",
        "State Route 12",
        "County Route 7",
        "US-211",
        "VA-55",
        "SR-652",
        "US Route 211",
        "VA Route 55",
    )
    for ref in refs:
        assert not is_trail_worthy(_w(name="Some Road", highway="track", ref=ref), _MANY), ref


def test_drops_route_by_tiger_name_base():
    # ref absent but TIGER recorded the route class in tiger:name_base_1.
    assert not is_trail_worthy(
        _w(name="Old Pike", highway="track", **{"tiger:name_base_1": "State Route"}), _MANY
    )


def test_drops_institutional_wellness_footway():
    # "The Andreae Family Wellness and Recreation Trail" — a private institutional
    # footway tag-identical to a nature trail; the `wellness` token is the interim drop.
    assert not is_trail_worthy(
        _w(name="The Andreae Family Wellness and Recreation Trail", highway="footway"), _MANY
    )


def test_drops_residential_street_suffix_track():
    # Outer Banks sand residential streets are tagged highway=track|footway (not
    # `residential`), clearing the highway gate. A name ending in an unambiguous street
    # suffix (Street/Avenue/Boulevard/Court/Drive/Lane) is a residential road, not a hike.
    for name in ("Barracuda Street", "Amadas Avenue", "Malbon Drive", "Seagull Lane"):
        assert not is_trail_worthy(_w(name=name, highway="track"), _MANY), name
    assert not is_trail_worthy(_w(name="Tasman Drive", highway="footway"), _MANY)
    assert not is_trail_worthy(_w(name="Brother's Way", highway="track"), _MANY)


def test_keeps_compound_way_suffix_trail():
    # "Way" only drops as a whole trailing word: a compound ending in "way"
    # ("Greenway"/"Broadway") has no word boundary before it and must survive.
    assert is_trail_worthy(_w(name="Riverside Greenway", highway="path"), _MANY)


def test_drops_numbered_state_route_by_name():
    # "State Route 1108" (OBX): the route number lived in the NAME, not `ref` — the
    # ref-only check missed it, so the numbered-route gate now also reads the name.
    assert not is_trail_worthy(_w(name="State Route 1108", highway="track"), _MANY)


def test_keeps_walkable_road_suffix_and_trail_names():
    # "Road" and "Way" are deliberately NOT residential-street suffixes: real fire / dike
    # roads end in "Road" (NPS-corroborated OBX trails). And a suffix word appearing
    # mid-name must not fire (end-anchored) — a real trail is kept.
    assert is_trail_worthy(_w(name="Salt Pond Road", highway="footway", surface="unpaved"), _MANY)
    assert is_trail_worthy(_w(name="LORAN Road", highway="track"), _MANY)
    assert is_trail_worthy(_w(name="Open Ponds Trail", highway="path"), _MANY)
    assert is_trail_worthy(_w(name="Drive-In Overlook Trail", highway="path"), _MANY)


def test_drops_two_point_footway_stub():
    assert not is_trail_worthy(_w(name="Connector", highway="footway"), _TWO)


def test_drops_unnamed():
    assert not is_trail_worthy(_w(highway="path"), _MANY)
    assert not is_trail_worthy(_w(name="   ", highway="path"), _MANY)
