"""Maps contract test — the backend's wire shape == the frontend's published types.

The Epic 017 AC-4.3 join: the JSON the API emits must match the wire DTOs the
frontend declares in `frontend/src/data/api.ts` (the source of truth). This test
locks the backend Pydantic models to that contract two ways:

1. **Always:** assert each model's field names equal the canonical set transcribed
   from `frontend/src/data/api.ts` (`EXPECTED`, below). This guards the backend even
   on a branch where the frontend types haven't merged yet.
2. **When present:** if `frontend/src/data/api.ts` already carries the `Wire*` types
   (post-merge / on main), parse them and assert they match `EXPECTED` too — a live
   three-way lock (TS file == EXPECTED == Pydantic) that fails loud on any drift.

Field NAMES are the contract (snake_case, verbatim); a rename on either side breaks
this test.
"""

from __future__ import annotations

import re
from pathlib import Path

from api.schemas import (
    ElevationProfile,
    ElevationSample,
    FeedCardResponse,
    GeoJsonGeometry,
    GeoPoint,
)

_API_TS = Path(__file__).resolve().parent.parent / "frontend" / "src" / "data" / "api.ts"

# Canonical wire field names, transcribed from frontend/src/data/api.ts (source of truth).
EXPECTED: dict[str, set[str]] = {
    "WirePoint": {"lat", "lon", "derived"},
    "WireGeometry": {"type", "coordinates"},
    "WireElevationSample": {"distance_m", "elevation_m"},
    "WireElevationProfile": {
        "samples",
        "total_gain_m",
        "total_loss_m",
        "max_grade_pct",
        "source",
        "resolution_m",
        "estimated_duration_min",
    },
    "FeedCardResponse": {
        "canonical_id",
        "name",
        "distance_mi",
        "lines",
        "warnings",
        "unavailable",
        "geometry",
        "trailhead",
        "geometry_confidence",
        "summit",
        "elevation_profile",
    },
}

# Which Pydantic model implements each wire type.
_MODEL_FOR = {
    "WirePoint": GeoPoint,
    "WireGeometry": GeoJsonGeometry,
    "WireElevationSample": ElevationSample,
    "WireElevationProfile": ElevationProfile,
    "FeedCardResponse": FeedCardResponse,
}


# ── 1. The backend models match the canonical contract (always) ───────────────


def test_pydantic_models_match_the_wire_contract():
    for wire_name, expected in EXPECTED.items():
        model = _MODEL_FOR[wire_name]
        assert set(model.model_fields) == expected, (
            f"{model.__name__} fields {set(model.model_fields)} != contract {expected}"
        )


def test_elevation_profile_fields_are_snake_case():
    # Regression guard for the camelCase→snake_case fix-forward.
    fields = set(ElevationProfile.model_fields) | set(ElevationSample.model_fields)
    assert not any(c.isupper() for f in fields for c in f), f"camelCase leaked: {fields}"


# ── 2. Cross-check against the published TS types when they're present ─────────


def _ts_interface_fields(text: str, name: str) -> set[str] | None:
    """Field names of `export interface <name> { ... }` (no nested braces in these
    DTOs). `None` when the interface isn't declared in the file."""
    match = re.search(rf"interface\s+{re.escape(name)}\s*\{{(.*?)\}}", text, re.DOTALL)
    if match is None:
        return None
    return set(re.findall(r"^\s*(\w+)\??\s*:", match.group(1), re.MULTILINE))


def test_frontend_api_ts_matches_when_wire_types_present():
    if not _API_TS.exists():
        return  # frontend not in this checkout
    text = _API_TS.read_text(encoding="utf-8")
    if "WireElevationProfile" not in text:
        # The Wire* maps types haven't merged into this branch's api.ts yet; the
        # always-on check above still locks the backend to the contract.
        return
    # Interface-shaped wire types: parse + assert they equal the canonical set.
    for wire_name in (
        "WirePoint",
        "WireElevationSample",
        "WireElevationProfile",
        "FeedCardResponse",
    ):
        found = _ts_interface_fields(text, wire_name)
        assert found is not None, f"{wire_name} missing from api.ts"
        assert found == EXPECTED[wire_name], (
            f"api.ts {wire_name} {found} != contract {EXPECTED[wire_name]}"
        )
