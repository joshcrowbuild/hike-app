"""Set-aside contract test — the backend's wire shape == the frontend's published types.

The Epic 018 S5 join: the set-aside disclosure the API emits (a hazardous live
condition ruled a trail out, with cause + source) must match the wire DTOs the
frontend declares in `frontend/src/data/api.ts` (the source of truth). Mirrors
`tests/test_maps_contract.py`: an always-on Pydantic lock plus a cross-check
against the TS interfaces when they're present (a three-way lock on drift).

Field NAMES are the contract (snake_case, verbatim); a rename on either side
breaks this test so the S4 (frontend) and S5 (backend) lanes can't silently drift.
"""

from __future__ import annotations

import re
from pathlib import Path

from api.schemas import FeedResponse, SetAsideReasonResponse, SetAsideResponse

_API_TS = Path(__file__).resolve().parent.parent / "frontend" / "src" / "data" / "api.ts"

# Canonical wire field names, transcribed from frontend/src/data/api.ts (source of truth).
# conditions_complete: the Epic 040 two-phase self-description (additive; absent/true
# means the verified single-pass truth, false means a phase-1 response).
EXPECTED: dict[str, set[str]] = {
    "SetAsideReasonResponse": {"text", "source", "kind"},
    "SetAsideResponse": {"canonical_id", "name", "reasons"},
    "FeedResponse": {
        "query",
        "cards",
        "card_count",
        "notices",
        "set_aside",
        "conditions_complete",
        "region_conditions",
        "personalization_degraded",
    },
}

# Backend-only fields shipped ahead of frontend adoption (frame-conditions-wave
# §5, epic-054): additive/optional, exactly like `conditions_complete` before it —
# a field TS hasn't grown YET is not drift, only a field TS HAS that the backend
# doesn't (or vice versa for a non-pending field) is. Remove an entry here once
# the corresponding frontend lane lands it in `api.ts`.
_PENDING_FRONTEND_ADOPTION: dict[str, set[str]] = {
    "FeedResponse": {"region_conditions", "personalization_degraded"},
}

_MODEL_FOR = {
    "SetAsideReasonResponse": SetAsideReasonResponse,
    "SetAsideResponse": SetAsideResponse,
    "FeedResponse": FeedResponse,
}


# ── 1. The backend models match the canonical contract (always) ───────────────


def test_pydantic_models_match_the_wire_contract() -> None:
    for wire_name, expected in EXPECTED.items():
        model = _MODEL_FOR[wire_name]
        assert set(model.model_fields) == expected, (
            f"{model.__name__} fields {set(model.model_fields)} != contract {expected}"
        )


def test_set_aside_fields_are_snake_case() -> None:
    fields = set(SetAsideResponse.model_fields) | set(SetAsideReasonResponse.model_fields)
    assert not any(c.isupper() for f in fields for c in f), f"camelCase leaked: {fields}"


# ── 2. Cross-check against the published TS types when they're present ─────────


def _ts_interface_fields(text: str, name: str) -> set[str] | None:
    """Field names of `export interface <name> { ... }` (no nested braces in these
    DTOs). `None` when the interface isn't declared in the file."""
    match = re.search(rf"interface\s+{re.escape(name)}\s*\{{(.*?)\}}", text, re.DOTALL)
    if match is None:
        return None
    return set(re.findall(r"^\s*(\w+)\??\s*:", match.group(1), re.MULTILINE))


def test_frontend_api_ts_matches_when_wire_types_present() -> None:
    if not _API_TS.exists():
        return  # frontend not in this checkout
    text = _API_TS.read_text(encoding="utf-8")
    if "SetAsideResponse" not in text:
        # The set-aside wire types haven't merged into this branch's api.ts yet; the
        # always-on Pydantic check above still locks the backend to the contract.
        return
    for wire_name in ("SetAsideReasonResponse", "SetAsideResponse", "FeedResponse"):
        found = _ts_interface_fields(text, wire_name)
        assert found is not None, f"{wire_name} missing from api.ts"
        pending = _PENDING_FRONTEND_ADOPTION.get(wire_name, set())
        # `found` may freely include or omit a pending field (either side of
        # adoption); every OTHER field must match exactly in both directions.
        assert found <= EXPECTED[wire_name], (
            f"api.ts {wire_name} has field(s) unknown to the backend: {found - EXPECTED[wire_name]}"
        )
        assert (EXPECTED[wire_name] - pending) <= found, (
            f"api.ts {wire_name} is missing required field(s): "
            f"{(EXPECTED[wire_name] - pending) - found}"
        )
