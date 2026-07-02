"""Trail-worthiness filter for OSM ways (corpus quality — Lead 1).

The Overpass spine query pulls *any named* `path|footway|track|bridleway|steps`. That
sweeps in urban non-trails — sidewalks, school/utility connector footways, private
drives — which pollute the feed ("Path to School", "Haden Place Sidewalk", "Leach
Road"). This drops those by OSM tags + a tight name denylist, **without** excluding
legitimate unpaved fire roads / forest tracks (`highway=track`, e.g. "Compton Gap
Road", "Mathews Arm Road") that are real hikes.

It also drops numbered public routes that Census-TIGER mis-imported as
`highway=track` (numbered VA state / county / US routes — cars drive them) by keying
on the route number in `ref`, while leaving genuine fire roads (no numbered `ref`)
untouched.

Deliberately conservative — high precision over recall. It removes only clear
non-trails; the residual noise (residential footway loops with innocuous names, a
named `track` that is really a back road, private institutional footways like the
"Andreae" wellness path) needs a spatial / park-boundary signal, which is a follow-up.
Tags come straight from Overpass (`element["tags"]`); they were previously discarded
at fetch, so capturing them is half the fix.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

# `access` values that mean "not open to the public" — unless `foot` re-grants it.
_PRIVATE_ACCESS = {"private", "no", "customers", "permit", "military", "delivery", "agricultural"}
_FOOT_OK = {"yes", "designated", "permissive", "public", "official"}

# `footway` sub-types that are pedestrian *infrastructure*, never a recreational trail.
_NON_TRAIL_FOOTWAY = {"sidewalk", "crossing", "traffic_island", "link"}

# Numbered public-route signal. Census-TIGER mis-imported numbered state/county/US
# routes as `highway=track`, so they survive the highway gate and pose as "fire roads"
# ("Little Loop Road" ref=SR 652, "Snake Road" ref=SR 650 — cars drive them). The `ref`
# carries the route number; matching it drops the route. Deliberately NOT keyed on
# `tiger:cfcc=A41`: real fire roads (Compton Gap Rd, Mathews Arm Rd) carry A41 too but
# have no numbered `ref`, so a cfcc rule would drop genuine hikes.
# `[\s-]*(Route\s*)?` so it catches the space, hyphenated, and spelled-out forms OSM
# editors normalize TIGER refs into — "SR 652", "US-211", "VA Route 55" — all of which
# are numbered routes. A digit is always required, so no bare word can false-positive.
_PUBLIC_ROUTE_REF = re.compile(r"\b(SR|CR|VA|US|State Route|County Route)[\s-]*(Route\s*)?\d", re.I)
# TIGER also records the route class in `tiger:name_base_1` ("State Route" / "County
# Route") even when `ref` is absent — a second, name-base signal for the same class.
_TIGER_ROUTE_BASE = re.compile(r"\b(State|County) Route\b", re.I)

# Residential street-name suffixes. On barrier-island / coastal TIGER grids, sand
# residential streets are tagged `highway=track|footway` (not `residential`), so they
# clear the highway gate and pose as trails ("Barracuda Street", "Malbon Drive",
# "Seagull Lane" in the Outer Banks). A name ending in an unambiguous street suffix is a
# residential road, never a hikeable trail. Deliberately EXCLUDES "Road": real fire / dike
# roads end in "Road" ("Salt Pond Road", "LORAN Road" — both NPS-corroborated OBX trails),
# matching the existing "keep fire roads" stance (`highway=track`). Anchored to the end of
# the name and matched as whole words (OSM spells suffixes out) so it can't fire mid-name
# (a "Drive"-containing trail name) nor inside a compound ("Greenway"/"Broadway" — no word
# boundary before the "way", so they don't match).
_RESIDENTIAL_STREET_SUFFIX = re.compile(
    r"\b(street|avenue|boulevard|court|drive|lane|way)\s*$", re.I
)

# Unambiguous non-trail name signals. Kept tight so it never matches a real trail
# (e.g. "Hull School Trail", "Meadows School Trail" are real) or a fire road — it
# targets the utilitarian-connector / urban-infra class only.
#
# The `wellness <institution>` branch is an interim token for the institutional-footway
# class ("The Andreae Family Wellness and Recreation Trail" — a private hospital/campus
# path tag-identical to a nature trail, so no clean tag fix exists). It requires
# `wellness` be followed by an institutional word ("and recreation", "center", "campus",
# …) so a bare public "Wellness Trail" / "Wellness Loop" — a common, legitimate municipal
# fitness loop — is NOT dropped. Still a name heuristic, not a real signal.
# TODO: replace the `wellness` token with a spatial / park-boundary test (is the way
# inside a managed recreation area?) — the durable discriminator for institutional
# footways, which the name denylist can only approximate.
_NAME_DENY = re.compile(
    r"\b(side ?walk|drive ?way|cross ?walk|wheelchair|colonnade"
    r"|parking (lot|area)|bus (stop|loop))\b"
    r"|\bwellness (and recreation|cent(er|re)|campus|clinic|hospital|institute)\b"
    r"|\bpath to (a |an |the )?"
    r"(school|store|parking|lot|bus|garage|garden|building|club|gym|colonnade)\b"
    r"|\b(ramp|stairs?) to\b",
    re.I,
)


def is_trail_worthy(tags: Mapping[str, str], coords: Sequence[object]) -> bool:
    """True if an OSM way looks like a real hikeable trail, not urban/private infra.

    `tags` is the raw OSM tag map (must include `name`); `coords` is the way's vertex
    list (only its length is used). Pure and side-effect-free."""
    name = (tags.get("name") or "").strip()
    if not name:
        return False  # unnamed: not displayable / conflatable (existing drop)

    highway = tags.get("highway", "")
    access = tags.get("access", "")
    foot = tags.get("foot", "")

    # Private / no public foot access → not a hikeable trail (e.g. "Leach Road").
    if access in _PRIVATE_ACCESS and foot not in _FOOT_OK:
        return False

    # Numbered public route (TIGER-misimported as highway=track) → a road, not a trail.
    # Keyed on the route number in `ref` OR in the `name` itself (OBX carried a bare
    # "State Route 1108" whose route number lived only in the name, not `ref`), or the
    # route class in `tiger:name_base_1`. NOT on tiger:cfcc=A41 — real fire roads share
    # A41 but carry no numbered ref. A digit is always required after the route token, so
    # a real name ("US Life-Saving Station Trail") can't false-positive.
    if _PUBLIC_ROUTE_REF.search(tags.get("ref", "")) or _PUBLIC_ROUTE_REF.search(name):
        return False
    if _TIGER_ROUTE_BASE.search(tags.get("tiger:name_base_1", "")):
        return False

    # Urban pedestrian infrastructure (sidewalks, crossings) → not a trail.
    if tags.get("footway", "") in _NON_TRAIL_FOOTWAY:
        return False

    # Conservative name denylist for utilitarian connectors / urban infra.
    if _NAME_DENY.search(name):
        return False

    # Residential street posing as a track/footway (coastal sand-street grids).
    if _RESIDENTIAL_STREET_SUFFIX.search(name):
        return False

    # A named footway with exactly two vertices is almost always a driveway / connector
    # stub, not a trail. Restricted to `footway` so 2-vertex path/track segments survive.
    if highway == "footway" and len(coords) == 2:
        return False

    return True
