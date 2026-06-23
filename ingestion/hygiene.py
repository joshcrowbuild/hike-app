"""Stage-3 data hygiene (pure; network-free).

Validity + completeness + provenance-integrity checks. Failures surface as flags
the pipeline logs, not silent drops. Provenance integrity is the hard invariant —
no record lacking (source, source_pk, fetched_at, ingest_version) may enter load,
which is what makes the whole graph source-or-silence-able (rule #1).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from shapely.geometry.base import BaseGeometry

_REQUIRED_PROVENANCE = ("source", "source_pk", "fetched_at", "ingest_version")


def valid_lonlat(lon: float, lat: float) -> bool:
    if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
        return False
    return not (lon == 0.0 and lat == 0.0)  # reject null island


def in_bbox(lon: float, lat: float, bbox: tuple[float, float, float, float]) -> bool:
    west, south, east, north = bbox
    return west <= lon <= east and south <= lat <= north


def geometry_valid(geom: BaseGeometry) -> bool:
    return geom is not None and not geom.is_empty and bool(geom.is_valid)


def has_provenance(record: Mapping[str, Any]) -> bool:
    return all(record.get(key) for key in _REQUIRED_PROVENANCE)


def hygiene_flags(record: Mapping[str, Any]) -> list[str]:
    """Non-fatal flags for a record (kept, not dropped, so the pipeline can log)."""
    flags: list[str] = []
    if not record.get("name") and not record.get("ref"):
        flags.append("attr_incomplete")  # geometry-only; can't conflate by attribute
    if record.get("informal"):
        flags.append("informal")  # social/unofficial trail — keep but flag
    if not has_provenance(record):
        flags.append("missing_provenance")
    return flags
