"""Route assembly — fold a trail's segment lines into one ready-to-serve route.

Geometry lives per-`Segment` (`Segment.geom_wkt`, a LineString) under each trail
(`(:CanonicalTrail)-[:HAS_SEGMENT]->(:Segment)`); a trail's full route is the
*assembled* line across those segments (Epic 016 S1, ⚠️ review correction). This
module is the pure (shapely-only, no DB, no I/O) assembler:

- `assemble_route` / `assemble_geometry` — order + merge segment lines into a
  single route geometry: a `LineString` when the segments join end-to-end, a
  `MultiLineString` (parts ordered start → end) when they don't join cleanly.
  Precompute this at ingest and store it on the trail so the API is a simple read,
  not a runtime graph-walk (D3/D4).
- `wkt_to_geojson` — convert the stored route WKT to a GeoJSON geometry at the API
  boundary, coordinate order `(lon, lat)` per the GeoJSON spec (AC-1.3).

Source-or-silence (Rule #1): no parseable segment line → `None`, never an empty or
fabricated line.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from shapely import wkt as shapely_wkt
from shapely.geometry import LineString, MultiLineString, mapping
from shapely.geometry.base import BaseGeometry
from shapely.ops import linemerge


def parse_wkt(wkt: str | None) -> BaseGeometry | None:
    """Parse a WKT string to a shapely geometry; `None` on empty/missing/invalid
    (the assembler never raises on a malformed segment — degrade, Rule #1/#6)."""
    if not wkt or not isinstance(wkt, str):
        return None
    try:
        geom = shapely_wkt.loads(wkt)
    except Exception:
        return None
    if geom is None or geom.is_empty:
        return None
    return geom


def _collect_lines(geom: BaseGeometry | None) -> list[LineString]:
    """Flatten any geometry into its constituent (≥2-vertex) LineStrings."""
    out: list[LineString] = []
    if geom is None or geom.is_empty:
        return out
    gt = geom.geom_type
    if gt == "LineString":
        if len(geom.coords) >= 2:
            out.append(geom)
    elif gt in ("MultiLineString", "GeometryCollection"):
        for part in geom.geoms:
            out.extend(_collect_lines(part))
    return out


def _dist2(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Squared planar distance in degrees — only ever used for nearest-endpoint
    *comparisons*, so the lon/lat aspect distortion is irrelevant (no metres here)."""
    dx, dy = a[0] - b[0], a[1] - b[1]
    return dx * dx + dy * dy


def _endpoints(line: LineString) -> tuple[tuple[float, float], tuple[float, float]]:
    coords = line.coords
    return (coords[0][0], coords[0][1]), (coords[-1][0], coords[-1][1])


def _order_lines(lines: list[LineString]) -> list[LineString]:
    """Order + orient disconnected line parts into one start → end sequence via a
    greedy nearest-endpoint chain. Deterministic: the chain starts at the
    westernmost-then-southernmost endpoint, so the same parts always assemble the
    same way (idempotent ingest). Each part is flipped as needed so its first
    vertex continues the chain — orientation matters for the elevation profile
    (which samples start → end)."""
    remaining = [ls for ls in lines if len(ls.coords) >= 2]
    if not remaining:
        return []

    # Deterministic seed: the part carrying the lexicographically-smallest endpoint,
    # oriented so that endpoint is first.
    seed_key: tuple[float, float] | None = None
    seed_ls = remaining[0]
    seed_flip = False
    for ls in remaining:
        start, end = _endpoints(ls)
        for pt, flip in ((start, False), (end, True)):
            if seed_key is None or pt < seed_key:
                seed_key, seed_ls, seed_flip = pt, ls, flip
    remaining.remove(seed_ls)
    seed_coords = list(seed_ls.coords)
    if seed_flip:
        seed_coords.reverse()
    ordered = [LineString(seed_coords)]
    cur_end = seed_coords[-1]

    while remaining:
        pick_ls = remaining[0]
        pick_flip = False
        best_d: float | None = None
        for ls in remaining:
            start, end = _endpoints(ls)
            d_start, d_end = _dist2(cur_end, start), _dist2(cur_end, end)
            d = min(d_start, d_end)
            if best_d is None or d < best_d:
                best_d, pick_ls, pick_flip = d, ls, d_end < d_start
        remaining.remove(pick_ls)
        coords = list(pick_ls.coords)
        if pick_flip:
            coords.reverse()
        ordered.append(LineString(coords))
        cur_end = coords[-1]
    return ordered


def _assemble_lines(lines: list[LineString]) -> BaseGeometry | None:
    """Merge contiguous lines (shapely `linemerge`) then order any disconnected
    runs. One connected route → a `LineString`; otherwise a `MultiLineString` whose
    parts are ordered start → end."""
    if not lines:
        return None
    merged: BaseGeometry = lines[0] if len(lines) == 1 else linemerge(lines)
    if merged.is_empty:
        return None
    if merged.geom_type == "LineString":
        return merged
    parts = _order_lines(_collect_lines(merged))
    if not parts:
        return None
    return parts[0] if len(parts) == 1 else MultiLineString(parts)


def assemble_geometry(geom: BaseGeometry | None) -> BaseGeometry | None:
    """Assemble a route from an already-parsed geometry (e.g. a spine `Feature.geom`
    that is itself a union of OSM ways). `None` when it carries no line."""
    return _assemble_lines(_collect_lines(geom))


def line_parts(geom: BaseGeometry | None) -> list[LineString]:
    """The ordered LineString parts of an (assembled) geometry — one for a
    `LineString`, the components for a `MultiLineString`. The unit each `Segment`
    is persisted from at ingest."""
    return _collect_lines(geom)


def assemble_route(segment_wkts: Sequence[str | None]) -> str | None:
    """Assemble the full route from a trail's ordered segment WKT lines and return
    it as WKT (LineString or MultiLineString). `None` when no segment is parseable
    (drives the API's `geometry: null` / "trailhead only" state — Rule #1)."""
    lines: list[LineString] = []
    for wkt in segment_wkts:
        lines.extend(_collect_lines(parse_wkt(wkt)))
    assembled = _assemble_lines(lines)
    return assembled.wkt if assembled is not None else None


def _coords_to_lists(coords: Any) -> Any:
    """Recursively convert shapely's nested coord tuples to JSON lists of floats."""
    if isinstance(coords, (list, tuple)):
        if coords and isinstance(coords[0], (int, float)):
            return [float(c) for c in coords]
        return [_coords_to_lists(c) for c in coords]
    return coords


def geometry_to_geojson(geom: BaseGeometry | None) -> dict[str, Any] | None:
    """A line geometry → a GeoJSON `LineString`/`MultiLineString` dict, `(lon, lat)`
    order (AC-1.3). `None` for empty/non-line geometry (never a point/polygon)."""
    if geom is None or geom.is_empty:
        return None
    if geom.geom_type not in ("LineString", "MultiLineString"):
        return None
    shape = mapping(geom)
    return {"type": shape["type"], "coordinates": _coords_to_lists(shape["coordinates"])}


def wkt_to_geojson(wkt: str | None) -> dict[str, Any] | None:
    """Stored route WKT → GeoJSON geometry dict at the API boundary. `None` when the
    WKT is missing/invalid/empty (Rule #1)."""
    return geometry_to_geojson(parse_wkt(wkt))
