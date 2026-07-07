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
"Andreae" wellness path) is handled by the Phase-2 spatial signal: a way OUTSIDE the
region's protected-area boundary is SOFT-demoted in the feed (never dropped) — see
`ingestion.boundary` + `orchestration.curator.is_outside_boundary_demoted`. These
regexes stay as the high-precision *hard-drop* catch (TIGER routes, private access,
residential suffixes); the spatial signal ADDS to them, it does not replace them.
Tags come straight from Overpass (`element["tags"]`); they were previously discarded
at fetch, so capturing them is half the fix.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from functools import lru_cache

# `access` values that mean "not open to the public" — unless `foot` re-grants it.
_PRIVATE_ACCESS = {"private", "no", "customers", "permit", "military", "delivery", "agricultural"}
_FOOT_OK = {"yes", "designated", "permissive", "public", "official"}

# `footway` sub-types that are pedestrian *infrastructure*, never a recreational trail.
_NON_TRAIL_FOOTWAY = {"sidewalk", "crossing", "traffic_island", "link"}

# The four incident-tuned denylist regexes below (numbered public routes, TIGER route
# base, residential street suffixes, unambiguous non-trail names) live in
# `regions/exclusions.json` — the single source of truth (Epic 025) — not as literals
# here. See that file's `_comment` + `tests/test_trail_filter.py` for the pinned
# incident behavior each one exists to catch/keep.
EXCLUSIONS_PATH = "regions/exclusions.json"

_EXCLUSION_KEYS = (
    "public_route_ref",
    "tiger_route_base",
    "residential_street_suffix",
    "name_deny",
)


@lru_cache(maxsize=None)
def _load_exclusion_patterns(path: str = EXCLUSIONS_PATH) -> dict[str, re.Pattern[str]]:
    """Load + compile the denylist patterns from `regions/exclusions.json`.

    Fails loud on any malformation (missing file, missing key, non-string value, bad
    JSON, invalid regex) — a filter driven by a broken config must never silently
    degrade to an empty denylist and re-pollute the corpus."""
    with open(path) as f:
        data = json.load(f)
    compiled: dict[str, re.Pattern[str]] = {}
    for key in _EXCLUSION_KEYS:
        if key not in data:
            raise KeyError(f"{path} is missing required exclusion pattern {key!r}")
        pattern = data[key]
        if not isinstance(pattern, str):
            raise TypeError(
                f"{path} exclusion pattern {key!r} must be a string, got {type(pattern).__name__}"
            )
        compiled[key] = re.compile(pattern, re.I)
    return compiled


def _pattern(key: str) -> re.Pattern[str]:
    return _load_exclusion_patterns()[key]


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
    public_route_ref = _pattern("public_route_ref")
    if public_route_ref.search(tags.get("ref", "")) or public_route_ref.search(name):
        return False
    if _pattern("tiger_route_base").search(tags.get("tiger:name_base_1", "")):
        return False

    # Urban pedestrian infrastructure (sidewalks, crossings) → not a trail.
    if tags.get("footway", "") in _NON_TRAIL_FOOTWAY:
        return False

    # Conservative name denylist for utilitarian connectors / urban infra — see
    # `regions/exclusions.json` `name_deny` for the institutional-wellness /
    # path-to-X / ramp-to-X tokens this catches.
    if _pattern("name_deny").search(name):
        return False

    # Residential street posing as a track/footway (coastal sand-street grids). The
    # pattern deliberately excludes "Road": real fire/dike roads end in "Road"
    # (NPS-corroborated OBX trails), matching the "keep fire roads" stance.
    if _pattern("residential_street_suffix").search(name):
        return False

    # A named footway with exactly two vertices is almost always a driveway / connector
    # stub, not a trail. Restricted to `footway` so 2-vertex path/track segments survive.
    if highway == "footway" and len(coords) == 2:
        return False

    return True
