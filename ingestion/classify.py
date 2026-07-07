"""Tag classifiers — normalize raw OSM tags into source-or-silence properties.

Three pure, total functions over a way's `tags` dict, each returning a normalized
string with **empty-on-absent**: a missing or unrecognized tag returns `""`, never a
fabricated default (Rule #1). Ported from CoMaps `generator/osm2type.cpp`
(`DeterminePathGrade`, the tail of `DetermineSurfaceAndHighwayType`) plus a
project-original `foot`/`access` normalizer — see Epic 026 for the binding
corrections (no `"normal"` path_grade; no highway-rewrite port).
"""

from __future__ import annotations

from collections.abc import Mapping

_EXPERT_SAC_SCALES = frozenset(
    {"alpine_hiking", "demanding_alpine_hiking", "difficult_alpine_hiking"}
)
_EXPERT_VISIBILITY = frozenset({"horrible", "no", "very_bad"})
_DIFFICULT_SAC_SCALES = frozenset({"demanding_mountain_hiking"})
_DIFFICULT_VISIBILITY = frozenset({"bad", "poor"})


def classify_path_grade(tags: Mapping[str, str]) -> str:
    """Port of CoMaps `DeterminePathGrade` (osm2type.cpp ~822-848).

    Returns one of `{"expert", "difficult", ""}` — there is no `"normal"`; a way with
    no `sac_scale`/`trail_visibility`, or a non-`path` highway, is empty (Epic 026
    binding correction A1.1)."""
    if tags.get("highway") != "path":
        return ""
    scale = tags.get("sac_scale", "")
    visibility = tags.get("trail_visibility", "")
    if not scale and not visibility:
        return ""
    if scale in _EXPERT_SAC_SCALES or visibility in _EXPERT_VISIBILITY:
        return "expert"
    if scale in _DIFFICULT_SAC_SCALES or visibility in _DIFFICULT_VISIBILITY:
        return "difficult"
    return ""


# Word-lists ported VERBATIM from osm2type.cpp:624-661 (Epic 026 A1.2).
_PAVED_SURFACES = frozenset(
    {
        "asphalt",
        "cobblestone",
        "chipseal",
        "concrete",
        "grass_paver",
        "stone",
        "metal",
        "paved",
        "paving_stones",
        "sett",
        "brick",
        "bricks",
        "unhewn_cobblestone",
        "wood",
    }
)
_BAD_SURFACES = frozenset(
    {
        "cobblestone",
        "dirt",
        "earth",
        "soil",
        "grass",
        "gravel",
        "ground",
        "metal",
        "mud",
        "rock",
        "stone",
        "unpaved",
        "pebblestone",
        "sand",
        "sett",
        "brick",
        "bricks",
        "snow",
        "stepping_stones",
        "unhewn_cobblestone",
        "grass_paver",
        "wood",
        "woodchips",
    }
)
_VERY_BAD_SURFACES = frozenset(
    {
        "dirt",
        "earth",
        "soil",
        "grass",
        "ground",
        "mud",
        "rock",
        "sand",
        "snow",
        "stepping_stones",
        "woodchips",
    }
)
_VERY_BAD_SMOOTHNESS = frozenset(
    {
        "very_bad",
        "horrible",
        "very_horrible",
        "impassable",
        "robust_wheels",
        "high_clearance",
        "off_road_wheels",
        "rough",
    }
)
_MID_SMOOTHNESS = frozenset({"unknown", "intermediate"})

_DEFAULT_SURFACE_GRADE = 2.0


def _has(values: frozenset[str], raw: str) -> bool:
    """Compound-value tokenizer (osm2type.cpp ~663-673): a value like
    `concrete:plates` or `sand/dirt` matches if ANY `;:/`-separated part is in
    `values`."""
    if not raw:
        return False
    for sep in (";", ":", "/"):
        raw = raw.replace(sep, ";")
    return any(part in values for part in raw.split(";"))


def classify_surface(tags: Mapping[str, str]) -> str:
    """Port of the TAIL of CoMaps `DetermineSurfaceAndHighwayType`
    (osm2type.cpp ~772-820) plus its word-lists and `Has` tokenizer. Does NOT port
    the highway-rewrite block (~683-766) — `highway` is read only as an input to the
    guard below, never rewritten (Epic 026 binding correction A1.2).

    Returns one of `{"paved_good", "paved_bad", "unpaved_good", "unpaved_bad", ""}`."""
    if tags.get("4wd_only", "") in {"yes", "recommended"}:
        return "unpaved_bad"

    surface = tags.get("surface", "")
    smoothness = tags.get("smoothness", "")
    tracktype = tags.get("tracktype", "")
    highway = tags.get("highway", "")
    if highway == "ford":
        highway = ""
    try:
        grade = float(tags.get("surface:grade", ""))
    except ValueError:
        grade = _DEFAULT_SURFACE_GRADE

    if highway == "" or (surface == "" and smoothness == ""):
        return ""

    is_good = True
    is_paved = True

    # Check surface.
    if surface == "":
        if _has(_VERY_BAD_SMOOTHNESS, smoothness):
            return "unpaved_bad"
        if highway == "track" and tracktype != "grade1":
            is_paved = False
    else:
        is_paved = _has(_PAVED_SURFACES, surface)

    # Check smoothness.
    if smoothness != "":
        if _has(_MID_SMOOTHNESS, smoothness):
            if is_paved:
                if highway in {"motorway", "trunk"}:
                    return ""
                is_good = False
            else:
                is_good = not _has(_BAD_SURFACES, surface)
        else:
            is_good = smoothness != "bad" and not _has(_VERY_BAD_SMOOTHNESS, smoothness)
    elif grade < 2:
        is_good = False
    elif surface != "" and grade < 3:
        is_good = not (
            _has(_BAD_SURFACES, surface) if is_paved else _has(_VERY_BAD_SURFACES, surface)
        )

    return ("paved_" if is_paved else "unpaved_") + ("good" if is_good else "bad")


_FOOT_ACCESS_YES = frozenset({"yes", "designated", "permissive", "destination", "official"})
_FOOT_ACCESS_PERMIT = frozenset({"permit"})
_FOOT_ACCESS_PRIVATE = frozenset({"private", "customers", "agricultural", "forestry", "delivery"})
_FOOT_ACCESS_DISCOURAGED = frozenset({"discouraged"})
_FOOT_ACCESS_NO = frozenset({"no"})


def classify_foot_access(tags: Mapping[str, str]) -> str:
    """Normalized pedestrian-access enum (Epic 026 AC-2.3, no CoMaps port). The
    `foot` tag wins over `access` (pedestrian-specific); an absent/unrecognized value
    is `""` — never coerced to `"yes"` (Rule #1)."""
    raw = tags.get("foot") or tags.get("access") or ""
    if raw in _FOOT_ACCESS_YES:
        return "yes"
    if raw in _FOOT_ACCESS_PERMIT:
        return "permit"
    if raw in _FOOT_ACCESS_PRIVATE:
        return "private"
    if raw in _FOOT_ACCESS_DISCOURAGED:
        return "discouraged"
    if raw in _FOOT_ACCESS_NO:
        return "no"
    return ""
