"""NPS fetch — National Park Service trails via ArcGIS public FeatureServer.

Source: NPS Trails public ArcGIS service (IRMA / NPS Open Data).
Authority: tier-1 for existence + geometry within NPS-managed land (Decision Log §27).
License: public domain (US federal government).

Uses the same ArcGIS REST pagination pattern as usfs.py. On any error returns [].
"""

from __future__ import annotations

import logging

import httpx
from shapely.geometry import LineString, MultiLineString, shape

from ingestion.conflate.match import Feature

log = logging.getLogger(__name__)

# Public NPS trails ArcGIS FeatureServer (confirmed reachable; see api-verification doc).
NPS_URL = (
    "https://services1.arcgis.com/fBc8EJBxQRMcHlei/ArcGIS/rest/services"
    "/NPS_Trails_Public/FeatureServer/0/query"
)
# Field names from the NPS layer (TRLNAME is the canonical field; TRLALTNAME is alt).
_NAME_FIELDS = ("TRLNAME", "TRAIL_NAME", "NAME")
_PAGE_SIZE = 1000


def _pick_name(props: dict) -> str | None:
    for field in _NAME_FIELDS:
        v = props.get(field)
        if v and str(v).strip() and str(v).strip().upper() not in ("NULL", "N/A", "NONE"):
            return str(v).strip()
    return None


def fetch(
    bbox: tuple[float, float, float, float],
    *,
    client: httpx.Client | None = None,
    timeout: float = 60.0,
) -> list[Feature]:
    """Fetch NPS trails within bbox (south, west, north, east). Returns [] on error."""
    south, west, north, east = bbox
    c = client or httpx.Client(timeout=timeout)
    features: list[Feature] = []
    offset = 0

    while True:
        params = {
            "where": "1=1",
            "geometry": f"{west},{south},{east},{north}",
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "outSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "*",
            "f": "geojson",
            "resultOffset": offset,
            "resultRecordCount": _PAGE_SIZE,
        }
        try:
            r = c.get(NPS_URL, params=params)
            r.raise_for_status()
            doc = r.json()
        except Exception as exc:
            log.warning("NPS fetch failed at offset %d: %s", offset, exc)
            break

        page_features = doc.get("features", [])
        for feat in page_features:
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
            if isinstance(geom, MultiLineString):
                for line in geom.geoms:
                    ref = str(props.get("OBJECTID") or "")
                    features.append(Feature(name=name, geom=line, source="NPS", ref=ref or None))
            elif isinstance(geom, LineString) and not geom.is_empty:
                ref = str(props.get("OBJECTID") or "")
                features.append(Feature(name=name, geom=geom, source="NPS", ref=ref or None))

        if len(page_features) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE

    log.info("NPS fetch: %d features in bbox %s", len(features), bbox)
    return features
