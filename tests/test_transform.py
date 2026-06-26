"""Stage-3 transform/normalization tests (pure)."""

from __future__ import annotations

from ingestion.transform import (
    normalize_allowed_use,
    normalize_surface,
    to_feet,
    to_meters,
    to_miles,
)


def test_unit_conversions_roundtrip() -> None:
    assert abs(to_miles(1609.344) - 1.0) < 1e-9
    assert abs(to_meters(1.0) - 1609.344) < 1e-9
    assert abs(to_feet(1000.0) - 3280.839895) < 1e-3


def test_normalize_allowed_use() -> None:
    assert normalize_allowed_use("hiker/pedestrian") == "foot"
    assert normalize_allowed_use("Bicycle") == "bike"
    assert normalize_allowed_use("unicycle") is None  # unknown -> None, never guessed


def test_normalize_surface() -> None:
    assert normalize_surface("Asphalt") == "paved"
    assert normalize_surface("dirt") == "natural"
    assert normalize_surface("lava") is None
