"""Trail-worthiness filter for OSM ways (corpus quality — Lead 1).

The Overpass spine query pulls *any named* `path|footway|track|bridleway|steps`. That
sweeps in urban non-trails — sidewalks, school/utility connector footways, private
drives — which pollute the feed ("Path to School", "Haden Place Sidewalk", "Leach
Road"). This drops those by OSM tags + a tight name denylist, **without** excluding
legitimate unpaved fire roads / forest tracks (`highway=track`, e.g. "Compton Gap
Road", "Mathews Arm Road") that are real hikes.

Deliberately conservative — high precision over recall. It removes only clear
non-trails; the residual noise (residential footway loops with innocuous names, a
named `track` that is really a back road) needs a spatial / park-boundary signal,
which is a follow-up. Tags come straight from Overpass (`element["tags"]`); they were
previously discarded at fetch, so capturing them is half the fix.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

# `access` values that mean "not open to the public" — unless `foot` re-grants it.
_PRIVATE_ACCESS = {"private", "no", "customers", "permit", "military", "delivery", "agricultural"}
_FOOT_OK = {"yes", "designated", "permissive", "public", "official"}

# `footway` sub-types that are pedestrian *infrastructure*, never a recreational trail.
_NON_TRAIL_FOOTWAY = {"sidewalk", "crossing", "traffic_island", "link"}

# Unambiguous non-trail name signals. Kept tight so it never matches a real trail
# (e.g. "Hull School Trail", "Meadows School Trail" are real) or a fire road — it
# targets the utilitarian-connector / urban-infra class only.
_NAME_DENY = re.compile(
    r"\b(side ?walk|drive ?way|cross ?walk|wheelchair|colonnade"
    r"|parking (lot|area)|bus (stop|loop))\b"
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

    # Urban pedestrian infrastructure (sidewalks, crossings) → not a trail.
    if tags.get("footway", "") in _NON_TRAIL_FOOTWAY:
        return False

    # Conservative name denylist for utilitarian connectors / urban infra.
    if _NAME_DENY.search(name):
        return False

    # A named footway with exactly two vertices is almost always a driveway / connector
    # stub, not a trail. Restricted to `footway` so 2-vertex path/track segments survive.
    if highway == "footway" and len(coords) == 2:
        return False

    return True
