"""Region config files — schema + non-overlap guards over `regions/*.geojson`.

Hermetic (stdlib json only): no graph, no network, no shapely. Every region file
is pure config consumed by three independent readers — `ingestion.pipeline.
load_region` (bbox → ingest scope), `orchestration.regions.list_regions` (the
picker catalog), and `ingestion.boundary.load_region_boundary` (the spatial
classifier) — so a malformed file degrades three surfaces at once. These tests
pin the contract every reader assumes.

The pairwise-disjoint test is the double-ingest guard: two regions whose bboxes
overlap would both fetch (and both own) the same OSM ways, and the per-region
prune of one would fight the other's load. Edge *contact* (zero-area touch) is
fine; positive-area overlap is not.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path

import pytest

_REGIONS_DIR = Path(__file__).resolve().parent.parent / "regions"
_REGION_FILES = sorted(_REGIONS_DIR.glob("*.geojson"))
_IDS = [p.stem for p in _REGION_FILES]

# Keys every region file must carry (the union of what the three readers and the
# fetch-floor gate consume). Comment keys document the schema in-band and are
# required so a new region can't silently drop the operator guidance.
_REQUIRED_PROPS = (
    "region_id",
    "name",
    "region_label",
    "description",
    "bbox",
    "bbox_comment",
    "sources",
    "area_ids",
    "origins",
    "min_fetch_counts",
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


@pytest.mark.parametrize("path", _REGION_FILES, ids=_IDS)
def test_region_file_schema(path: Path) -> None:
    feat = _load(path)
    assert feat.get("type") == "Feature", f"{path.name}: not a GeoJSON Feature"
    props = feat["properties"]
    for key in _REQUIRED_PROPS:
        assert key in props, f"{path.name}: missing properties.{key}"
    # The filename IS the --region CLI id (load_region does Path(f"regions/{id}.geojson")).
    assert props["region_id"] == path.stem, f"{path.name}: region_id must match filename"


@pytest.mark.parametrize("path", _REGION_FILES, ids=_IDS)
def test_region_bbox_is_valid(path: Path) -> None:
    west, south, east, north = _load(path)["properties"]["bbox"]
    assert -180 < west < east < 180, f"{path.name}: bad lon span"
    assert -90 < south < north < 90, f"{path.name}: bad lat span"


@pytest.mark.parametrize("path", _REGION_FILES, ids=_IDS)
def test_region_geometry_fits_bbox(path: Path) -> None:
    # The boundary polygon (placeholder bbox rectangle OR a real protected-area
    # boundary) must sit inside the declared bbox — the classifier tests points
    # against the polygon while the fetch clips to the bbox, so a polygon leaking
    # outside the bbox would classify trails the region never fetched.
    feat = _load(path)
    geom = feat["geometry"]
    assert geom["type"] == "Polygon", f"{path.name}: geometry must be a Polygon"
    ring = geom["coordinates"][0]
    assert ring[0] == ring[-1], f"{path.name}: polygon ring not closed"
    west, south, east, north = feat["properties"]["bbox"]
    eps = 1e-9
    for lon, lat in ring:
        assert west - eps <= lon <= east + eps, f"{path.name}: polygon lon outside bbox"
        assert south - eps <= lat <= north + eps, f"{path.name}: polygon lat outside bbox"


@pytest.mark.parametrize("path", _REGION_FILES, ids=_IDS)
def test_region_origins_inside_bbox(path: Path) -> None:
    # An origin outside its own region's bbox would anchor the picker to a point
    # the region never ingested trails around — drive-time sorting goes nonsense.
    props = _load(path)["properties"]
    west, south, east, north = props["bbox"]
    for origin in props["origins"]:
        for key in ("key", "label", "lat", "lon"):
            assert key in origin, f"{path.name}: origin missing {key}"
        assert west <= origin["lon"] <= east, f"{path.name}: origin {origin['key']} lon"
        assert south <= origin["lat"] <= north, f"{path.name}: origin {origin['key']} lat"


@pytest.mark.parametrize("path", _REGION_FILES, ids=_IDS)
def test_region_declares_osm_fetch_floor(path: Path) -> None:
    # The gate-before-prune floor (PR #95): every region must declare a positive
    # OSM floor so a truncated Overpass fetch can never self-wipe the region.
    counts = _load(path)["properties"]["min_fetch_counts"]
    assert isinstance(counts.get("osm"), int) and counts["osm"] >= 1, (
        f"{path.name}: min_fetch_counts.osm must be a positive int"
    )


def test_region_bboxes_pairwise_disjoint() -> None:
    """No two regions may claim overlapping bbox area (trail double-ingest guard).

    Zero-area edge contact is allowed; a positive-area intersection in BOTH axes
    fails, naming the pair and the overlap size so the fix (shrink one bbox) is
    obvious.
    """
    boxes = {p.stem: _load(p)["properties"]["bbox"] for p in _REGION_FILES}
    for (id_a, a), (id_b, b) in itertools.combinations(sorted(boxes.items()), 2):
        lon_overlap = min(a[2], b[2]) - max(a[0], b[0])
        lat_overlap = min(a[3], b[3]) - max(a[1], b[1])
        assert not (lon_overlap > 0 and lat_overlap > 0), (
            f"regions {id_a!r} and {id_b!r} overlap by "
            f"{lon_overlap:.4f}° lon × {lat_overlap:.4f}° lat — trails would double-ingest"
        )
