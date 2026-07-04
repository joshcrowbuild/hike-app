#!/usr/bin/env python3
"""Reproducibly fetch USFS National Forest System (NFS) Trails from the checked-in
manifest.

`ingestion/fetch/usfs.py` reads `data/usfs/trails.geojson` at ingest time but has no
way to obtain it — this script is the reproducible other half (DEM-style, see
`scripts/fetch_dem.py`): download the USFS EDW bulk shapefile named in
`regions/usfs_manifest.json`, convert to WGS84 GeoJSON with **geopandas**
(geopandas>=1.0 uses `pyogrio` as its default I/O engine — do NOT reach for
`fiona`/`ogr2ogr`), consolidate the raw per-segment export into whole trails keyed by
`TRAIL_NO`, and optionally clip to a region's bbox.

Usage:
  python scripts/fetch_usfs.py --dry-run                    # print the plan only
  python scripts/fetch_usfs.py                               # full national convert
  python scripts/fetch_usfs.py --region shenandoah-gwj       # clip output to a region
  python scripts/fetch_usfs.py --write-manifest               # record the zip's sha256

Network + geopandas are needed only for the actual convert; `--dry-run` is
stdlib-only. The GeoJSON lands under gitignored `data/usfs/` and is never committed —
the manifest (URL + checksum + vintage) is the durable, checked-in artifact.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from ingestion.dem import verify_checksum  # noqa: E402  (generic checksum helper)
from ingestion.usfs_convert import (  # noqa: E402  (after sys.path insert)
    MANIFEST_PATH,
    clip_to_bbox,
    consolidate_by_trail_no,
    geodataframe_to_wgs84_features,
    load_manifest,
)


def _manifest_file() -> Path:
    return _REPO_ROOT / MANIFEST_PATH


def _region_bbox(region: str) -> list[float]:
    """The `[west, south, east, north]` bbox from the region's geojson."""
    path = _REPO_ROOT / "regions" / f"{region}.geojson"
    with path.open() as f:
        feat = json.load(f)
    bbox = feat.get("properties", {}).get("bbox")
    if not bbox or len(bbox) != 4:
        raise SystemExit(f"region {region!r} geojson missing a valid bbox")
    return [float(x) for x in bbox]


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  downloading {url}")
    with urllib.request.urlopen(url) as resp, open(dest, "wb") as out:  # noqa: S310 (trusted USDA)
        while chunk := resp.read(1 << 20):
            out.write(chunk)


def _cmd_fetch(*, region: str | None, dry_run: bool, write_manifest: bool) -> int:
    manifest = load_manifest(_manifest_file())
    url = manifest["source_url"]
    dataset = manifest["dataset"]
    output = _REPO_ROOT / manifest["output"]
    vintage = manifest.get("vintage") or "unknown (record after first fetch)"

    bbox = _region_bbox(region) if region else None

    print(f"USFS NFS Trails: {url}")
    print(f"  dataset vintage: {vintage}")
    print(f"  → {manifest['output']}")
    if region:
        print(f"  clipped to region {region!r} bbox {bbox}")
    if dry_run:
        print("dry-run: nothing downloaded.")
        return 0

    try:
        import geopandas as gpd
    except ImportError:
        raise SystemExit(
            "geopandas is required to convert the USFS shapefile — "
            "`pip install -e '.[dev]'` (or `.[ingestion]`). "
            "(--dry-run needs neither network nor geopandas.)"
        )

    zip_dest = _REPO_ROOT / "data" / "usfs" / f"{dataset}.zip"
    if not zip_dest.is_file():
        _download(url, zip_dest)
    result = verify_checksum(zip_dest, manifest.get("sha256"))
    if not result.ok:
        raise SystemExit(
            f"USFS zip checksum MISMATCH (expected {manifest['sha256']}, got {result.computed})"
        )
    elif manifest.get("sha256") is None:
        print(f"  • zip sha256 {result.computed} (record with --write-manifest)")
        manifest["sha256"] = result.computed
    else:
        print("  ✓ zip checksum ok")

    extract_dir = _REPO_ROOT / "data" / "usfs" / dataset
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_dest) as zf:
        zf.extractall(extract_dir)
    shp_path = extract_dir / f"{dataset}.shp"

    print(f"  reading {shp_path} …")
    gdf = gpd.read_file(shp_path)  # pyogrio engine (geopandas>=1.0 default)
    raw_features = geodataframe_to_wgs84_features(gdf)
    print(f"  {len(raw_features)} raw segment(s)")

    if bbox:
        raw_features = clip_to_bbox(raw_features, bbox)
        print(f"  {len(raw_features)} segment(s) after bbox clip")

    consolidated = consolidate_by_trail_no(raw_features)
    print(f"  {len(consolidated)} trail(s) after TRAIL_NO consolidation")

    output.parent.mkdir(parents=True, exist_ok=True)
    doc = {"type": "FeatureCollection", "features": consolidated}
    with output.open("w") as f:
        json.dump(doc, f)
    print(f"✓ wrote {manifest['output']}")

    if write_manifest:
        with open(_manifest_file(), "w") as f:
            json.dump(manifest, f, indent=2)
            f.write("\n")
        print(f"✓ recorded checksum into {MANIFEST_PATH}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch USFS NFS Trails from the manifest")
    parser.add_argument("--region", help="Clip the output to a region's bbox (regions/*.geojson)")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan, download nothing")
    parser.add_argument(
        "--write-manifest",
        action="store_true",
        help="Record the computed zip sha256 back into the manifest after a successful fetch",
    )
    args = parser.parse_args()
    return _cmd_fetch(region=args.region, dry_run=args.dry_run, write_manifest=args.write_manifest)


if __name__ == "__main__":
    raise SystemExit(main())
