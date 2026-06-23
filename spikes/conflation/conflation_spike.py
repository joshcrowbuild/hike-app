"""Conflation reality-check spike (run where egress is open — see README).

Pulls the same few trails from OSM (Overpass) and an agency source (USFS EDW by
default), scores every cross-source pair on name + geometry agreement, and prints
an auto-accept / review / no-match report. Exploratory — informs Stage-3
thresholds and the OSM-Merge-vs-custom call. Not imported by the test suite.

Deps: `pip install -e ".[ingestion,live]"` (httpx, shapely, thefuzz).
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass

import httpx
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from thefuzz import fuzz

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

# Scoring thresholds (the thing the spike is here to calibrate).
NAME_MIN = 60  # below this we don't even consider a pair
NAME_AUTO = 85
BUFFER_DEG = 0.0003  # ~30 m at mid-latitudes; rough, good enough for a spike
OVERLAP_AUTO = 0.5
HAUSDORFF_AUTO_M = 80.0
DEG_TO_M = 111_000.0
# ────────────────────────────────────────────────────────────────────────────


@dataclass
class Feature:
    name: str
    source: str
    geom: BaseGeometry


def _norm(name: str) -> str:
    s = name.lower()
    s = re.sub(r"\b(trail|tr|trl|path|road|rd|fr|fs)\b", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return s.strip()


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
            out.append(Feature(name, "osm", shape({"type": "LineString", "coordinates": coords})))
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
            out.append(Feature(name, "agency", shape(geom)))
    return out


def geom_scores(a: BaseGeometry, b: BaseGeometry) -> tuple[float, float]:
    """Return (buffer-overlap ratio, Hausdorff distance in metres)."""
    ba, bb = a.buffer(BUFFER_DEG), b.buffer(BUFFER_DEG)
    inter = ba.intersection(bb).area
    overlap = inter / min(ba.area, bb.area) if min(ba.area, bb.area) else 0.0
    hausdorff_m = a.hausdorff_distance(b) * DEG_TO_M
    return overlap, hausdorff_m


def classify(name_score: int, overlap: float, hausdorff_m: float) -> str:
    if name_score >= NAME_AUTO and (overlap >= OVERLAP_AUTO or hausdorff_m <= HAUSDORFF_AUTO_M):
        return "AUTO-ACCEPT"
    if name_score >= NAME_MIN and overlap > 0:
        return "REVIEW"
    return "NO-MATCH"


def main() -> int:
    print(f"bbox={BBOX}")
    osm = fetch_osm(BBOX)
    agency = fetch_agency(BBOX)
    print(f"OSM features: {len(osm)} | agency features: {len(agency)}\n")

    buckets = {"AUTO-ACCEPT": 0, "REVIEW": 0, "NO-MATCH": 0}
    for o in osm:
        for a in agency:
            name_score = fuzz.token_sort_ratio(_norm(o.name), _norm(a.name))
            if name_score < NAME_MIN:
                continue
            overlap, hausdorff_m = geom_scores(o.geom, a.geom)
            verdict = classify(name_score, overlap, hausdorff_m)
            buckets[verdict] += 1
            if verdict != "NO-MATCH":
                print(
                    f"[{verdict:11}] name={name_score:3} overlap={overlap:.2f} "
                    f"hausdorff={hausdorff_m:6.0f}m  | OSM '{o.name}'  ~  AGENCY '{a.name}'"
                )

    print(f"\nsummary: {buckets}")
    print("-> high AUTO-ACCEPT share => custom matcher viable; large REVIEW => lean on OSM Merge.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
