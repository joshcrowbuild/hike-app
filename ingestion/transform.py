"""Stage-3 transform / normalization (pure; network-free).

Unit conversion and controlled-vocabulary normalization. Raw source values are
preserved by the caller on the SourceRecord (best-view is computed at load) —
these helpers produce the normalized forms. Conflicting `allowed_use` across
sources is never reconciled here (Stage 1 rule); normalize each independently.
"""

from __future__ import annotations

_M_PER_MILE = 1609.344
_FT_PER_M = 3.280839895


def to_miles(meters: float) -> float:
    return meters / _M_PER_MILE


def to_meters(miles: float) -> float:
    return miles * _M_PER_MILE


def to_feet(meters: float) -> float:
    return meters * _FT_PER_M


_ALLOWED_USE = {
    "hiker": "foot",
    "hiker/pedestrian": "foot",
    "pedestrian": "foot",
    "foot": "foot",
    "hiking": "foot",
    "bicycle": "bike",
    "bike": "bike",
    "mountain bike": "bike",
    "horse": "horse",
    "equestrian": "horse",
    "atv": "motor",
    "motorized": "motor",
    "motor_vehicle": "motor",
}

_SURFACE = {
    "dirt": "natural",
    "ground": "natural",
    "earth": "natural",
    "natural": "natural",
    "gravel": "gravel",
    "fine_gravel": "gravel",
    "compacted": "gravel",
    "paved": "paved",
    "asphalt": "paved",
    "concrete": "paved",
    "rock": "rock",
    "boulder": "rock",
}


def normalize_allowed_use(raw: str) -> str | None:
    """Map a raw allowed-use string to the controlled vocab; None if unknown."""
    return _ALLOWED_USE.get(raw.strip().lower())


def normalize_surface(raw: str) -> str | None:
    """Map a raw surface string to the controlled vocab; None if unknown."""
    return _SURFACE.get(raw.strip().lower())
