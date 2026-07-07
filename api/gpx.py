"""GPX 1.1 serializer (CoMaps borrow plan §D4) — the wire format only, ported from
`libs/kml/serdes_gpx.cpp` (reference clone), not the C++ file/geometry machinery.

Pure: no I/O, no Neo4j, no filesystem. `build_gpx` takes already-resolved world
route data and returns a GPX 1.1 XML string with one `<trk>`/`<trkseg>`, an
altitude-guarded `<ele>` (D4.3 — emitted only when the elevation samples align 1:1
with the route vertices), and an optional trailhead `<wpt>`. Dropped relative to the
CoMaps reference: gpxx/gpx_style/xsi extension namespaces, colour `<extensions>`,
`<time>`, and all KML/file/multi-geometry machinery — out of scope for this epic.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

_GPX_HEADER = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<gpx version="1.1" creator="Adventure Planner" '
    'xmlns="http://www.topografix.com/GPX/1/1">\n'
)
_GPX_FOOTER = "</gpx>"


def _fmt(value: float) -> str:
    """~8 significant figures, never scientific notation (mirrors CoMaps'
    `CoordToString`, `serdes_gpx.cpp:437-443`)."""
    return f"{value:.8f}".rstrip("0").rstrip(".")


def build_gpx(
    name: str,
    coords: list[tuple[float, float]],
    *,
    elevations: list[float] | None,
    elev_source: str | None,
    trailhead: tuple[float, float] | None,
) -> str:
    """Serialize one trail's world route to a GPX 1.1 string.

    `coords` and `trailhead` are `(lon, lat)` order (matching GeoJSON) — this
    function transposes internally to GPX's `lat`-then-`lon` attribute order.
    `<ele>` is emitted on every trkpt iff `elev_source` is truthy AND `elevations`
    is not None AND its length matches `coords` (D4.3 altitude gate) — otherwise no
    trkpt carries `<ele>`, never a partial or interpolated altitude.
    """
    has_altitude = bool(elev_source) and elevations is not None and len(elevations) == len(coords)

    parts = [_GPX_HEADER]

    if trailhead is not None:
        th_lon, th_lat = trailhead
        parts.append(
            f'  <wpt lat="{_fmt(th_lat)}" lon="{_fmt(th_lon)}">\n'
            f"    <name>{escape(f'{name} trailhead')}</name>\n"
            f"  </wpt>\n"
        )

    parts.append(f"  <trk>\n    <name>{escape(name)}</name>\n    <trkseg>\n")
    if has_altitude:
        for (lon, lat), ele in zip(coords, elevations):  # type: ignore[arg-type]
            parts.append(
                f'      <trkpt lat="{_fmt(lat)}" lon="{_fmt(lon)}"><ele>{_fmt(ele)}</ele></trkpt>\n'
            )
    else:
        for lon, lat in coords:
            parts.append(f'      <trkpt lat="{_fmt(lat)}" lon="{_fmt(lon)}"/>\n')
    parts.append("    </trkseg>\n  </trk>\n")

    parts.append(_GPX_FOOTER)
    return "".join(parts)
