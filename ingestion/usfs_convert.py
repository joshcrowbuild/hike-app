"""USFS NFS Trails conversion helpers — pure GeoJSON transforms, the reproducible
half of getting `data/usfs/trails.geojson` (the file `ingestion.fetch.usfs.fetch`
reads at ingest time) from the raw USFS EDW bulk export.

The raw `S_USA.TrailNFS_Publish` shapefile emits one feature per maintained
*segment* (ranger-district/maintenance breaks fragment a single named trail into
dozens of short pieces sharing a `TRAIL_NO`). `consolidate_by_trail_no` groups those
segments back into one feature per trail, so downstream conflation matching and
boundary containment checks (`ingestion.conflate.match`, `ingestion.boundary`) see
whole trails instead of fragments.

Kept import-light (shapely only — already an `ingestion`/`dev` dep) so it's
unit-testable without geopandas or network. `scripts/fetch_usfs.py` is the thin CLI
that adds the actual download + shapefile→GeoJSON reprojection (which needs
geopandas).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from shapely.geometry import LineString, MultiLineString, box, mapping, shape
from shapely.ops import unary_union

if TYPE_CHECKING:
    import geopandas as gpd

# Repo-root-relative manifest path (checked in; the shapefile/geojson it describes
# are NOT — they land under gitignored data/).
MANIFEST_PATH = "regions/usfs_manifest.json"

_NAME_FIELDS = ("TRAIL_NAME", "TRLNAME", "NAME")
_TRAIL_NO_FIELDS = ("TRAIL_NO", "TRAIL_NUMBER")


def load_manifest(path: str | Path = MANIFEST_PATH) -> dict[str, Any]:
    """Parse the USFS source manifest JSON. Fail loud — a fetch driven by a broken
    manifest should not proceed on guesses."""
    with open(path) as f:
        data: dict[str, Any] = json.load(f)
    return data


def _pick_name(props: dict[str, Any]) -> str | None:
    for field in _NAME_FIELDS:
        v = props.get(field)
        if v and str(v).strip():
            return str(v).strip()
    return None


def _pick_trail_no(props: dict[str, Any]) -> str | None:
    for field in _TRAIL_NO_FIELDS:
        v = props.get(field)
        if v and str(v).strip():
            return str(v).strip()
    return None


def _line_parts(geom: Any) -> list[LineString]:
    if isinstance(geom, MultiLineString):
        return [seg for seg in geom.geoms if not seg.is_empty]
    if isinstance(geom, LineString) and not geom.is_empty:
        return [geom]
    return []


def consolidate_by_trail_no(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group GeoJSON Feature dicts sharing a `TRAIL_NO` into one feature per trail
    (geometry merged into a single Line/MultiLineString), so a trail exported as N
    maintenance segments becomes N-1 fewer downstream fragments. Features with no
    usable `TRAIL_NO` pass through unmerged (each keeps its own identity — never
    accidentally combined with an unrelated unkeyed feature). Input order is
    preserved by each group's first occurrence.
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for i, feat in enumerate(features):
        props = feat.get("properties") or {}
        trail_no = _pick_trail_no(props)
        key = f"trail_no:{trail_no}" if trail_no else f"__unkeyed_{i}"
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(feat)

    consolidated: list[dict[str, Any]] = []
    for key in order:
        group = groups[key]
        if len(group) == 1:
            consolidated.append(group[0])
            continue
        lines: list[LineString] = []
        for feat in group:
            lines.extend(_line_parts(shape(feat["geometry"])))
        if not lines:
            continue
        merged = unary_union(lines)
        # All segments of one trail should share a name; prefer whichever segment's
        # properties carry a usable one, falling back to the first segment's.
        props = next(
            (f["properties"] for f in group if _pick_name(f.get("properties") or {})),
            group[0]["properties"],
        )
        consolidated.append(
            {
                "type": "Feature",
                "properties": props,
                "geometry": mapping(merged),
            }
        )
    return consolidated


def geodataframe_to_wgs84_features(gdf: "gpd.GeoDataFrame") -> list[dict[str, Any]]:
    """Reproject a GeoDataFrame to WGS84 (if it isn't already) and return its rows as
    GeoJSON Feature dicts. The one geopandas-touching seam in this module — kept
    minimal so `consolidate_by_trail_no` / `clip_to_bbox` stay unit-testable without
    the dependency. Takes a GeoDataFrame rather than a shapefile path so
    `scripts/fetch_usfs.py` owns the actual file I/O (`gpd.read_file`, pyogrio
    engine)."""
    if gdf.crs is not None and str(gdf.crs).upper() != "EPSG:4326":
        gdf = gdf.to_crs(epsg=4326)
    features: list[dict[str, Any]] = json.loads(gdf.to_json())["features"]
    return features


def clip_to_bbox(
    features: list[dict[str, Any]], bbox: tuple[float, float, float, float]
) -> list[dict[str, Any]]:
    """Keep only features intersecting a `[west, south, east, north]` bbox (WGS84) —
    the region geojson's own bbox convention (matching `ingestion.dem.tiles_for_bbox`
    and `scripts/fetch_dem.py`)."""
    west, south, east, north = bbox
    region_box = box(west, south, east, north)
    return [feat for feat in features if shape(feat["geometry"]).intersects(region_box)]
