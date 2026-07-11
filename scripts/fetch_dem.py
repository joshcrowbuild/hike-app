#!/usr/bin/env python3
"""Reproducibly fetch a region's USGS 3DEP DEM from the checked-in manifest.

The durability half of the elevation fix: the DEM raster used to live only in a
transient local worktree and vanished on prune, silently blanking corpus elevation.
This script reconstructs it anywhere from `regions/dem_manifest.json` — download each
1/3-arc-second tile, verify its sha256 (or record it on first fetch), then merge +
clip to the region bbox into `data/dem/{region}.tif`, the path `Settings` looks for by
convention. After a run, a standard `make ingest` re-applies 3DEP automatically.

Usage:
  python scripts/fetch_dem.py --region shenandoah-gwj            # download + build
  python scripts/fetch_dem.py --region shenandoah-gwj --dry-run  # print plan only
  python scripts/fetch_dem.py --region shenandoah-gwj --write-manifest
                                                    # record computed checksums back
  python scripts/fetch_dem.py --init richmond       # regen tile list from geojson bbox

Network + rasterio are needed only for the actual build; `--dry-run` and `--init` are
stdlib-only. The DEM lands under gitignored data/ and is never committed — the manifest
(URLs + checksums) is the durable, checked-in artifact.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from ingestion.dem import (  # noqa: E402  (after sys.path insert)
    MANIFEST_PATH,
    load_manifest,
    region_entry,
    tile_base_url,
    tiles_for_bbox,
    usgs_13_tile_url,
    verify_checksum,
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


def _cmd_init(region: str) -> int:
    """Regenerate a region's manifest tile list from its geojson bbox (checksums reset
    to null — a re-fetch records them). Prints the JSON block for the operator to paste;
    does not rewrite the manifest in place, so the diff stays reviewable."""
    bbox = _region_bbox(region)
    tiles = tiles_for_bbox(*bbox)
    block = {
        "resolution": "1/3 arc-second (~10 m)",
        "bbox": bbox,
        "output": f"data/dem/{region}.tif",
        "output_sha256": None,
        "tiles": [{"name": t, "sha256": None} for t in tiles],
    }
    print(f"# manifest entry for {region!r} ({len(tiles)} tile(s)):")
    print(json.dumps({region: block}, indent=2))
    return 0


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  downloading {url}")
    # B310-audited: fixed https:// USGS 3DEP URL, no user-supplied scheme.
    with urllib.request.urlopen(url) as resp, open(dest, "wb") as out:  # nosec B310
        while chunk := resp.read(1 << 20):
            out.write(chunk)


def _cmd_fetch(region: str, *, dry_run: bool, write_manifest: bool) -> int:
    manifest = load_manifest(_manifest_file())
    entry = region_entry(manifest, region)
    base = tile_base_url(manifest)
    tiles = entry["tiles"]
    output = _REPO_ROOT / entry["output"]
    tile_dir = _REPO_ROOT / "data" / "dem" / "tiles"

    print(f"region {region!r}: {len(tiles)} tile(s) → {entry['output']}")
    urls = [(t, usgs_13_tile_url(t["name"], base_url=base)) for t in tiles]
    for t, url in urls:
        print(f"  {t['name']}: {url}")
    if dry_run:
        print("dry-run: nothing downloaded.")
        return 0

    try:
        import rasterio
        from rasterio.mask import mask
        from rasterio.merge import merge
        from shapely.geometry import box, mapping
    except ImportError:
        raise SystemExit(
            "rasterio (+ shapely) is required to merge/clip tiles — `pip install -e "
            "'.[graph]'`. (--dry-run and --init need neither network nor rasterio.)"
        )

    tile_paths: list[Path] = []
    checksum_failures = 0
    for t in tiles:
        name = t["name"]
        dest = tile_dir / f"USGS_13_{name}.tif"
        if not dest.is_file():
            _download(usgs_13_tile_url(name, base_url=base), dest)
        result = verify_checksum(dest, t.get("sha256"))
        if not result.ok:
            print(f"  ✗ {name}: checksum MISMATCH (expected {t['sha256']}, got {result.computed})")
            checksum_failures += 1
        elif t.get("sha256") is None:
            print(f"  • {name}: sha256 {result.computed} (record with --write-manifest)")
            t["sha256"] = result.computed
        else:
            print(f"  ✓ {name}: checksum ok")
        tile_paths.append(dest)

    if checksum_failures:
        raise SystemExit(f"{checksum_failures} tile checksum(s) failed — refusing to build DEM")

    # Merge the tiles, then clip to the region bbox so the output raster stays scoped.
    print(f"  merging {len(tile_paths)} tile(s) + clipping to bbox …")
    datasets = [rasterio.open(p) for p in tile_paths]
    try:
        mosaic, transform = merge(datasets)
        profile = datasets[0].profile
    finally:
        for d in datasets:
            d.close()
    profile.update(height=mosaic.shape[1], width=mosaic.shape[2], transform=transform)
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(".merged.tif")
    with rasterio.open(tmp, "w", **profile) as dst:
        dst.write(mosaic)
    west, south, east, north = entry["bbox"]
    with rasterio.open(tmp) as src:
        clipped, clip_transform = mask(src, [mapping(box(west, south, east, north))], crop=True)
        clip_profile = src.profile
    clip_profile.update(height=clipped.shape[1], width=clipped.shape[2], transform=clip_transform)
    with rasterio.open(output, "w", **clip_profile) as dst:
        dst.write(clipped)
    tmp.unlink(missing_ok=True)

    out_result = verify_checksum(output, entry.get("output_sha256"))
    if not out_result.ok:
        raise SystemExit(
            f"output DEM checksum MISMATCH (expected {entry['output_sha256']}, "
            f"got {out_result.computed})"
        )
    if entry.get("output_sha256") is None:
        entry["output_sha256"] = out_result.computed
        print(f"  output sha256 {out_result.computed} (record with --write-manifest)")
    print(f"✓ wrote {entry['output']}")

    if write_manifest:
        with open(_manifest_file(), "w") as f:
            json.dump(manifest, f, indent=2)
            f.write("\n")
        print(f"✓ recorded checksums into {MANIFEST_PATH}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch a region's 3DEP DEM from the manifest")
    parser.add_argument("--region", help="Region id (matches regions/*.geojson + manifest)")
    parser.add_argument(
        "--init", metavar="REGION", help="Print a manifest tile block from the region bbox"
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the plan, download nothing")
    parser.add_argument(
        "--write-manifest",
        action="store_true",
        help="Record computed checksums back into the manifest after a successful build",
    )
    args = parser.parse_args()

    if args.init:
        return _cmd_init(args.init)
    if not args.region:
        parser.error("one of --region or --init is required")
    return _cmd_fetch(args.region, dry_run=args.dry_run, write_manifest=args.write_manifest)


if __name__ == "__main__":
    raise SystemExit(main())
