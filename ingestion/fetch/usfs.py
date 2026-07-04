"""USFS EDW fetch — National Forest System trails from bulk GeoJSON file.

Source: USFS Enterprise Data Warehouse, NFS Trails layer.
Authority: tier-1 for existence + allowed_use (Decision Log §27).
License: public domain (US federal government).

The USFS EDW ArcGIS REST service requires network authentication (returns 403
from non-USFS IPs). Use the bulk shapefile download instead, reproducibly obtained
via `scripts/fetch_usfs.py` (source URL + checksum + vintage tracked in
`regions/usfs_manifest.json`, DEM-manifest-style):

  python scripts/fetch_usfs.py --region shenandoah-gwj

That downloads the national NFS Trails shapefile, converts to WGS84 GeoJSON with
geopandas, consolidates the raw per-segment export into whole trails keyed by
TRAIL_NO, clips to the region bbox, and writes data/usfs/trails.geojson.

Then run: python -m ingestion.pipeline --region shenandoah-gwj

This fetcher clips the national file to the region bbox. Returns [] if absent.
Field names (verified from USFS EDW schema): TRAIL_NAME, GIS_MILES, TRAIL_NO.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from shapely.geometry import LineString, MultiLineString, shape

from ingestion.conflate.match import Feature

log = logging.getLogger(__name__)

_DEFAULT_FILE = Path("data/usfs/trails.geojson")
_NAME_FIELDS = ("TRAIL_NAME", "TRLNAME", "NAME")


def _pick_name(props: dict) -> str | None:
    for field in _NAME_FIELDS:
        v = props.get(field)
        if v and str(v).strip():
            return str(v).strip()
    return None


def _in_bbox(coords: list[tuple[float, float]], bbox: tuple[float, float, float, float]) -> bool:
    """True if any coord falls within bbox (south, west, north, east)."""
    south, west, north, east = bbox
    return any(west <= x <= east and south <= y <= north for x, y in coords)


def fetch(
    bbox: tuple[float, float, float, float],
    *,
    geojson_path: Path | str | None = None,
) -> list[Feature]:
    """Load USFS trails from local GeoJSON, clipped to bbox (south,west,north,east).

    Returns [] if the file is absent (pipeline skips USFS source with a warning).
    See module docstring for how to obtain and prepare the file.
    """
    path = Path(geojson_path) if geojson_path else _DEFAULT_FILE
    if not path.exists():
        log.warning(
            "USFS trail file not found at %s — skipping USFS source.\n"
            "  Fetch it: python scripts/fetch_usfs.py --region <region>",
            path,
        )
        return []

    try:
        with path.open() as f:
            doc = json.load(f)
    except Exception as exc:
        log.warning("USFS file load failed: %s", exc)
        return []

    features: list[Feature] = []
    for feat in doc.get("features", []):
        props = feat.get("properties") or {}
        geom_raw = feat.get("geometry")
        if not geom_raw:
            continue
        name = _pick_name(props)
        if not name:
            continue
        try:
            geom = shape(geom_raw)
        except Exception:
            continue

        ref = str(props.get("TRAIL_NO") or props.get("TRAIL_NUMBER") or "")

        def _add(line: LineString) -> None:
            if line.is_empty:
                return
            if _in_bbox(list(line.coords), bbox):
                features.append(Feature(name=name, geom=line, source="USFS", ref=ref or None))

        if isinstance(geom, MultiLineString):
            for seg in geom.geoms:
                _add(seg)
        elif isinstance(geom, LineString):
            _add(geom)

    log.info("USFS file load: %d features clipped to bbox %s", len(features), bbox)
    return features
