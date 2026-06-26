"""Conflation reality-check spike (run where egress is open — see README).

Pulls the same few trails from OSM (Overpass) and an agency source (USFS EDW by
default), then runs them through the *tested* matcher in `ingestion.conflate.match`
and prints an auto-accept / review / no-match report. The matching algorithm lives
in (and is unit-tested in) the package; this script is just the network harness
that feeds it real data. Informs Stage-3 thresholds + the OSM-Merge-vs-custom call.

Deps: `pip install -e ".[ingestion,live]"` (httpx, shapely, thefuzz).
"""

from __future__ import annotations

import sys

import httpx
from shapely.geometry import shape

from ingestion.conflate.match import Feature, match

# ── Edit these for your pilot area ──────────────────────────────────────────
# bbox = (south, west, north, east). Default: a small Shenandoah window.
BBOX = (38.55, -78.45, 38.70, -78.25)
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
# USFS EDW National Forest System Trails (FeatureServer/MapServer query -> geojson).
# CONFIRM/adjust against the live service; name field is TRAIL_NAME.
AGENCY_QUERY_URL = (
    "https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_TrailNFSTrails_01/MapServer/0/query"
)
AGENCY_NAME_FIELD = "TRAIL_NAME"
# ────────────────────────────────────────────────────────────────────────────


def fetch_osm(bbox: tuple[float, float, float, float]) -> list[Feature]:
    south, west, north, east = bbox
    query = (
        "[out:json][timeout:60];"
        f'way["highway"~"path|footway|track"]["name"]({south},{west},{north},{east});'
        "out geom;"
    )
    r = httpx.post(OVERPASS_URL, data={"data": query}, timeout=90)
    r.raise_for_status()
    out: list[Feature] = []
    for el in r.json().get("elements", []):
        coords = [(n["lon"], n["lat"]) for n in el.get("geometry", [])]
        name = el.get("tags", {}).get("name")
        if name and len(coords) >= 2:
            out.append(Feature(name, shape({"type": "LineString", "coordinates": coords}), "osm"))
    return out


def fetch_agency(bbox: tuple[float, float, float, float]) -> list[Feature]:
    south, west, north, east = bbox
    params = {
        "where": "1=1",
        "geometry": f"{west},{south},{east},{north}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "outSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": AGENCY_NAME_FIELD,
        "f": "geojson",
    }
    r = httpx.get(AGENCY_QUERY_URL, params=params, timeout=90)
    r.raise_for_status()
    out: list[Feature] = []
    for feat in r.json().get("features", []):
        name = (feat.get("properties") or {}).get(AGENCY_NAME_FIELD)
        geom = feat.get("geometry")
        if name and geom:
            out.append(Feature(name, shape(geom), "agency"))
    return out


def main() -> int:
    print(f"bbox={BBOX}")
    osm = fetch_osm(BBOX)
    agency = fetch_agency(BBOX)
    print(f"OSM features: {len(osm)} | agency features: {len(agency)}\n")

    results = match(osm, agency)  # the tested algorithm
    buckets = {"auto-accept": 0, "review": 0}
    for m in results:
        buckets[m.verdict] = buckets.get(m.verdict, 0) + 1
        print(
            f"[{m.verdict:11}] name={m.name_score:3} overlap={m.agreement.overlap:.2f} "
            f"hausdorff={m.agreement.hausdorff_m:6.0f}m  | OSM '{m.a.name}'  ~  AGENCY '{m.b.name}'"
        )

    print(f"\nsummary: {buckets} (no-match pairs are dropped)")
    print("-> high auto-accept share => custom matcher viable; large review => lean on OSM Merge.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
