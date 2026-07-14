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
    # suffix (Street/Avenue/Boulevard/Court/Circle/Place/Terrace/Drive/Lane) is a
    # residential road, not a hike.
    for name in ("Barracuda Street", "Amadas Avenue", "Malbon Drive", "Seagull Lane"):
        assert not is_trail_worthy(_w(name=name, highway="track"), _MANY), name
    assert not is_trail_worthy(_w(name="Tasman Drive", highway="footway"), _MANY)
    assert not is_trail_worthy(_w(name="Brother's Way", highway="track"), _MANY)


def test_drops_residential_circle_place_terrace_track():
    # Dogfood #2: TIGER-imported cul-de-sacs near Front Royal survived the original
    # suffix set — it listed Court/Drive/Lane but omitted Circle/Place/Terrace, so
    # these residential tracks (no numbered ref, tiger:name_type Cir/Pl/Ter) cleared
    # every gate and reached the live /plan feed (Oak Circle + Overlook Circle in the
    # top-10; Peace and Quiet Circle above real trails). Real observed names + tags.
    survivors = (
        _w(name="Oak Circle", highway="track", **{"tiger:name_type": "Cir", "tiger:cfcc": "A41"}),
        _w(name="Peace and Quiet Circle", highway="track", **{"tiger:name_type": "Cir"}),
        _w(name="Bluebird Circle", highway="track"),  # residential, no tiger:name_type
        _w(name="Wildwood Place", highway="track", **{"tiger:name_type": "Pl"}),
    )
    for tags in survivors:
        assert not is_trail_worthy(tags, _MANY), tags["name"]
    # Terrace completes the residential set (no live instance in-region yet; pinned so
    # the next TIGER "…Terrace" import can't re-open the gap the way Circle did).
    assert not is_trail_worthy(_w(name="Sunset Terrace", highway="footway"), _MANY)


def test_keeps_trailish_suffixes_adjacent_to_residential():
    # Precision guard for the Circle/Place/Terrace addition: real trail-feature words
    # that a broader denylist could wrongly sweep must survive. All are live Shenandoah
    # corpus keeps (highway=path/footway, no tiger street suffix): Loop/Run/Hollow/
    # Crossing are geographic trail terms, not street types.
    for name in ("Bear Rocks Loop", "Biscuit Run", "Barger Hollow", "Boyd's Crossing"):
        assert is_trail_worthy(_w(name=name, highway="path"), _MANY), name
    # End-anchored + word-boundary: a suffix word mid-name or inside a compound must not
    # fire ("Circle Rock Trail" ends in Trail; "Semicircle" has no boundary before it).
    assert is_trail_worthy(_w(name="Circle Rock Trail", highway="path"), _MANY)
    assert is_trail_worthy(_w(name="Semicircle", highway="path"), _MANY)


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


# ── GLM corpus-quality-sweep additions (2026-07) ───────────────────────────────
# docs/research/glm-corpus-quality-sweep-2026-07.md F1-F4. Verified + narrowed
# against the raw proposal (see regions/exclusions.json `_comment`): the `showers`
# token widened to catch both word orders the doc's `\bshowers? path\b` missed
# ("Path Loop B Showers"), and `unnamed` narrowed to only fire on OSM-editor
# placeholder names, not the real-world "Unnamed Creek Trail" naming convention.


def test_drops_campground_comfort_station_path():
    # F2 (OBX): "Loop G path to Comfort Station" / "Path Loop B Comfort Station" —
    # campground utility paths to restroom buildings, not recreational trails.
    assert not is_trail_worthy(
        _w(name="Loop G path to Comfort Station", highway="footway", surface="wood"), _MANY
    )
    assert not is_trail_worthy(_w(name="Path Loop B Comfort Station", highway="footway"), _MANY)


def test_keeps_comfort_named_real_trail():
    assert is_trail_worthy(_w(name="Comfort Ridge Trail", highway="path"), _MANY)


def test_drops_campground_showers_path_either_word_order():
    # F2 (OBX): both observed word orders — "Loop G Showers Path" and "Path Loop B
    # Showers" (the doc's `\bshowers? path\b` proposal missed the second order).
    assert not is_trail_worthy(
        _w(name="Loop G Showers Path", highway="footway", surface="wood"), _MANY
    )
    assert not is_trail_worthy(_w(name="Path Loop B Showers", highway="footway"), _MANY)


def test_keeps_shower_named_waterfall_trail():
    # Singular "Shower" attached to a geographic feature is a real, if unusual,
    # trail-naming convention (e.g. Shower Creek Falls, Oregon) — must survive.
    # Narrow enough that it never collides with the plural campground-facility word.
    assert is_trail_worthy(_w(name="Shower Creek Falls Trail", highway="path"), _MANY)
    assert is_trail_worthy(_w(name="Crystal Shower Falls Walk", highway="path"), _MANY)


def test_drops_new_placeholder_names():
    # F3 (York River): "New Trail (in progress)" / "New Section" are OSM editor
    # placeholder names, not real trail names.
    assert not is_trail_worthy(_w(name="New Trail (in progress)", highway="path"), _MANY)
    assert not is_trail_worthy(_w(name="New Section", highway="footway"), _MANY)


def test_keeps_new_river_and_new_england_trail():
    # "New River Trail" / "New England National Scenic Trail" are real, well-known
    # trails — "new" precedes a proper noun, not the placeholder words "trail"/
    # "section" directly, so the deny pattern must not fire.
    assert is_trail_worthy(_w(name="New River Trail", highway="path"), _MANY)
    assert is_trail_worthy(_w(name="New England National Scenic Trail", highway="path"), _MANY)


def test_drops_unnamed_placeholder_trail():
    # F3 (York River): "New Unnamed Trail Shortcut" — an OSM editor placeholder name
    # ("unnamed" directly modifying trail/path/shortcut/section/way).
    assert not is_trail_worthy(_w(name="New Unnamed Trail Shortcut", highway="path"), _MANY)
    assert not is_trail_worthy(_w(name="Unnamed Trail", highway="path"), _MANY)


def test_keeps_unnamed_creek_trail_naming_convention():
    # "Unnamed Creek Trail" is a real, if unusual, trail name used across multiple
    # US trail databases (a locally-unnamed creek, not an OSM editor placeholder) —
    # "unnamed" modifies "Creek"/"Falls", not "trail"/"path" directly, so it survives.
    assert is_trail_worthy(_w(name="Unnamed Creek Trail", highway="path"), _MANY)
    assert is_trail_worthy(_w(name="Unnamed Falls Trail", highway="path"), _MANY)


def test_drops_generic_access_route():
    # F4 (York River): "Access Route" — a generic access path with no recreational
    # trail tags and no more-specific name.
    assert not is_trail_worthy(_w(name="Access Route", highway="path"), _MANY)


def test_keeps_beach_access_trail():
    # "Beach Access Trail" / "ADA Access Trail" name the destination, not the
    # generic "route" placeholder — must survive.
    assert is_trail_worthy(_w(name="Beach Access Trail", highway="path"), _MANY)
    assert is_trail_worthy(_w(name="ADA Access Trail", highway="path"), _MANY)


def test_drops_numbered_beach_access_ramp():
    # F1 (OBX): bare numbered "Ramp N" — Cape Hatteras National Seashore beach/ORV
    # access ramps (boardwalk/sand paths from parking to beach), not hiking trails.
    for name in ("Ramp 1", "Ramp 45", "Ramp 70"):
        assert not is_trail_worthy(_w(name=name, highway="footway", surface="sand"), _MANY), name


def test_keeps_unnumbered_ramp_named_trail():
    # A "ramp" name without a trailing number is not the OBX beach-access pattern —
    # must survive (only `ramp \d+` is denied, not bare "ramp").
    assert is_trail_worthy(_w(name="Boat Ramp Trail", highway="path"), _MANY)
    assert is_trail_worthy(_w(name="Ramp Overlook Trail", highway="path"), _MANY)
