"""Protected-area boundary signal (Phase 2 — spatial trail classifier).

The durable discriminator the name regexes in `trail_filter` were approximating:
a way's position relative to the region's protected-area boundary (the NPS / USFS /
PAD-US polygon that defines the region). A way whose representative point falls
INSIDE the boundary — a fire/dike road like "Compton Gap Road" or "Salt Pond Road" —
is a real hike; an ambiguous `track`/`footway` OUTSIDE it — the "Andreae" wellness
path, coastal residential streets — is likely access/residential/institutional
infrastructure and gets SOFT-demoted in the feed (never dropped) by the Curator.

Why this over another regex: the boundary comes from the region config
(`regions/{region}.geojson`'s `geometry`), so a *new* geography needs a polygon, not
a hand-added name pattern. This is the whole point of Phase 2 — "the boundary tells
us" replaces "add a regex per geography." There is zero per-region code here.

**Degradation is total (never worse than today).** The classifier only speaks when
the region ships a *real* protected-area polygon. A region whose `geometry` is the
placeholder bbox rectangle every region carries today — or that has no polygon at
all — yields no boundary, and `classify_outside_boundary` returns `None` (unknown):
nothing is demoted, and the name-only `trail_filter` behaviour is unchanged. The
spatial signal activates the moment a region's `geometry` is tightened to the true
NPS/USFS boundary, with no code change.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry

log = logging.getLogger(__name__)

# A region `geometry` whose area fills this fraction (or more) of its own bounding
# box is a rectangle — the placeholder bbox every region ships today, not a real
# protected-area outline. Real NPS/USFS boundaries are irregular and fill well under
# this. Above the threshold we abstain (return no boundary) so behaviour degrades to
# today's name-only filter rather than demoting on a meaningless whole-bbox "inside".
_PLACEHOLDER_BBOX_AREA_RATIO = 0.99


def _is_placeholder_bbox(geom: BaseGeometry) -> bool:
    """True if `geom` is (essentially) its own bounding rectangle — the placeholder
    bbox a region carries before a real boundary polygon is committed. Such a polygon
    contains the entire region, so an inside/outside test against it is meaningless."""
    minx, miny, maxx, maxy = geom.bounds
    bbox_area = (maxx - minx) * (maxy - miny)
    if bbox_area <= 0:
        return True  # degenerate (line/point) — no usable interior
    return geom.area / bbox_area >= _PLACEHOLDER_BBOX_AREA_RATIO


def load_region_boundary(region_id: str) -> BaseGeometry | None:
    """The region's protected-area boundary polygon, read from
    `regions/{region_id}.geojson`'s `geometry`, or `None` when there is no usable
    boundary (missing file, non-polygon geometry, or a placeholder bbox rectangle).

    `None` is the degrade signal — the caller must treat it as "no spatial signal"
    and leave classification to the name-only filter (never worse than today)."""
    # Path is derived from a caller-supplied id; reject traversal defensively (the
    # ingest CLI already guards this, but the helper must not trust its caller).
    if "/" in region_id or "\\" in region_id or ".." in region_id:
        log.warning("Refusing suspicious region id for boundary load: %r", region_id)
        return None
    path = Path(f"regions/{region_id}.geojson")
    if not path.exists():
        return None
    try:
        with path.open() as f:
            feat = json.load(f)
        raw = feat.get("geometry")
        if not raw or raw.get("type") not in ("Polygon", "MultiPolygon"):
            return None
        geom = shape(raw)
    except Exception as exc:  # malformed geojson → degrade, never raise into ingest
        log.warning("Region %s boundary unreadable, degrading to no boundary: %s", region_id, exc)
        return None
    if geom.is_empty or not geom.is_valid or _is_placeholder_bbox(geom):
        log.info("Region %s has no real protected-area boundary — spatial signal off", region_id)
        return None
    return geom


def classify_outside_boundary(
    lat: float | None, lon: float | None, boundary: BaseGeometry | None
) -> bool | None:
    """Whether a trail at (`lat`, `lon`) sits OUTSIDE the region's protected-area
    boundary. Returns `None` (unknown → never demoted) when there is no boundary or
    no point — the degrade path. Otherwise `True` when the point is not covered by
    the boundary, `False` when it is inside.

    Uses `covers` (not `contains`) so a point exactly on the edge counts as inside —
    a trail on the park boundary is kept, honouring "a real trail must not vanish"."""
    if boundary is None or lat is None or lon is None:
        return None
    return not boundary.covers(Point(lon, lat))  # geojson/shapely x=lon, y=lat
