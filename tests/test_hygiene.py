"""Stage-3 data-hygiene tests (pure)."""

from __future__ import annotations

from shapely.geometry import LineString

from ingestion.hygiene import (
    geometry_valid,
    has_provenance,
    hygiene_flags,
    in_bbox,
    valid_lonlat,
)

_PROV = {
    "source": "OSM",
    "source_pk": "way/1",
    "fetched_at": "2026-06-01T00:00:00Z",
    "ingest_version": "2026-06",
}


def test_valid_lonlat() -> None:
    assert valid_lonlat(-78.4, 38.5)
    assert not valid_lonlat(0.0, 0.0)  # null island
    assert not valid_lonlat(200.0, 0.0)  # out of range


def test_in_bbox() -> None:
    bbox = (-78.45, 38.55, -78.25, 38.70)
    assert in_bbox(-78.30, 38.60, bbox)
    assert not in_bbox(-79.00, 38.60, bbox)


def test_geometry_valid() -> None:
    assert geometry_valid(LineString([(0, 0), (1, 1)]))
    assert not geometry_valid(LineString())  # empty


def test_has_provenance() -> None:
    assert has_provenance(_PROV)
    assert not has_provenance({k: v for k, v in _PROV.items() if k != "fetched_at"})


def test_hygiene_flags() -> None:
    assert hygiene_flags({**_PROV, "name": "Old Rag"}) == []
    flags = hygiene_flags({**_PROV, "informal": True})  # no name/ref + informal
    assert "attr_incomplete" in flags
    assert "informal" in flags
    assert "missing_provenance" in hygiene_flags({"name": "x"})
