#!/usr/bin/env python3
"""Reproducibly fetch a Geofabrik state `.osm.pbf` extract named in the
checked-in manifest (Epic 036 — deterministic pyosmium transport).

`ingestion/fetch/osm_pbf.py` reads a local `.osm.pbf` at ingest time but has no
way to obtain it — this script is the reproducible other half (DEM/USFS-style,
see `scripts/fetch_usfs.py`): download the named Geofabrik state extract
(`regions/osm_pbf_manifest.json`) to gitignored `data/osm/`, and optionally
record its replication vintage (the PBF header's
`osmosis_replication_timestamp`) back into the manifest.

Usage:
  python scripts/fetch_osm_pbf.py --dry-run                          # print the plan only
  python scripts/fetch_osm_pbf.py                                     # download the VA extract
  python scripts/fetch_osm_pbf.py --state north-carolina              # a different state
  python scripts/fetch_osm_pbf.py --write-manifest                    # + record the vintage

Network is needed only for the actual download; `--dry-run` is stdlib-only.
`osmium` (needed only to read the vintage header) is imported LAZILY inside the
`--write-manifest` branch — mirroring how `scripts/fetch_usfs.py` defers its
`geopandas` import off the dry-run path — so `--dry-run` never needs it
installed and never touches the network. The extract lands under gitignored
`data/osm/` and is never committed — the manifest (URL + vintage) is the
durable, checked-in artifact. A state extract is ~386-398 MB: never downloaded
in CI or a test path.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

MANIFEST_PATH = "regions/osm_pbf_manifest.json"


def _manifest_file() -> Path:
    return _REPO_ROOT / MANIFEST_PATH


def _load_manifest() -> dict:
    with _manifest_file().open() as f:
        return json.load(f)


def _find_extract(manifest: dict, state: str) -> dict:
    for extract in manifest["extracts"]:
        if extract["state"] == state:
            return extract
    known = ", ".join(e["state"] for e in manifest["extracts"])
    raise SystemExit(f"unknown state {state!r} in {MANIFEST_PATH}. Known: {known}")


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  downloading {url}")
    with urllib.request.urlopen(url) as resp, open(dest, "wb") as out:  # noqa: S310 (trusted Geofabrik)
        while chunk := resp.read(1 << 20):
            out.write(chunk)


def _cmd_fetch(*, state: str, dry_run: bool, write_manifest: bool) -> int:
    manifest = _load_manifest()
    extract = _find_extract(manifest, state)
    url = extract["source_url"]
    output = _REPO_ROOT / extract["output"]
    vintage = extract.get("replication_timestamp") or "unknown (record after first fetch)"

    print(f"Geofabrik {state} extract: {url}")
    print(f"  replication vintage: {vintage}")
    print(f"  → {extract['output']}")
    if dry_run:
        print("dry-run: nothing downloaded.")
        return 0

    _download(url, output)
    print(f"✓ wrote {extract['output']}")

    if write_manifest:
        import osmium  # lazy: only --write-manifest needs the vintage header read

        header = osmium.io.Reader(str(output)).header()
        ts = header.get("osmosis_replication_timestamp") or None
        extract["replication_timestamp"] = ts
        with _manifest_file().open("w") as f:
            json.dump(manifest, f, indent=2)
            f.write("\n")
        print(f"✓ recorded replication_timestamp={ts!r} into {MANIFEST_PATH}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch a Geofabrik OSM PBF state extract from the manifest"
    )
    parser.add_argument(
        "--state",
        default="virginia",
        help="Geofabrik state extract to fetch (regions/osm_pbf_manifest.json)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the plan, download nothing")
    parser.add_argument(
        "--write-manifest",
        action="store_true",
        help="Record the PBF's replication vintage back into the manifest after a successful fetch",
    )
    args = parser.parse_args()
    return _cmd_fetch(state=args.state, dry_run=args.dry_run, write_manifest=args.write_manifest)


if __name__ == "__main__":
    raise SystemExit(main())
