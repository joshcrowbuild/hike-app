"""Elevation-profile computation — sample a route, derive the shape of the climb.

The geospatial half of Epic 017, kept **pure** (math + shapely only; no rasterio):
the DEM read sits behind the injectable `ElevationSampler` so this logic — densify
→ sample → gain/loss/grade — is testable without a raster (a fake sampler stands in
for the DEM). `ingestion.sources.usgs_3dep` supplies the real `RasterioDEMSampler`.

Method (D2):
- **Densify** the route to ~`resolution_m` spacing along the ground (haversine), so
  the profile's x-axis is real distance, not vertex index.
- **Gain/loss** use a minimum-change (hysteresis) accumulator: only an elevation
  move exceeding `noise_threshold_m` since the last counted point is credited. This
  suppresses the well-known 10 m-DEM noise that otherwise inflates "total gain".
- **Max grade** is the steepest rise/run between consecutive samples.

Source-or-silence (Rule #1 / D3): no geometry, or DEM coverage below
`min_coverage`, yields `None` — never an interpolated or faked curve.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Protocol

from ingestion.route import line_parts, parse_wkt

log = logging.getLogger(__name__)

_EARTH_RADIUS_M = 6_371_000.0

# Defaults (Epic 017 Open Q 1/2 — cheap to tune later).
DEFAULT_RESOLUTION_M = 20.0
DEFAULT_NOISE_THRESHOLD_M = 3.0
DEFAULT_MIN_COVERAGE = 0.6


class ElevationSampler(Protocol):
    """Reads one ground elevation (metres) at a `(lon, lat)`. Returns `None` outside
    coverage or on nodata — the source-or-silence signal the profile builder honors."""

    def sample(self, lon: float, lat: float) -> float | None: ...


@dataclass(frozen=True)
class ElevationProfile:
    """A computed climb profile. `distances_m`/`elevations_m` are parallel arrays
    ordered start → end (the Neo4j-friendly encoding, Epic 017 AC-3.1)."""

    distances_m: list[float]
    elevations_m: list[float]
    total_gain_m: float
    total_loss_m: float
    max_grade_pct: float
    source: str
    resolution_m: float


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance in metres between two `(lon, lat)` points."""
    lon1, lat1 = math.radians(a[0]), math.radians(a[1])
    lon2, lat2 = math.radians(b[0]), math.radians(b[1])
    dlon, dlat = lon2 - lon1, lat2 - lat1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(h))


def densify(
    coords: list[tuple[float, float]], resolution_m: float
) -> list[tuple[float, float, float]]:
    """Insert interpolated points so consecutive samples are ≤ ~`resolution_m` apart
    along the ground. Returns `(lon, lat, cumulative_distance_m)`, starting at 0, with
    every original vertex retained. Empty/degenerate input degrades to what it has."""
    if not coords:
        return []
    if len(coords) < 2:
        return [(coords[0][0], coords[0][1], 0.0)]
    out: list[tuple[float, float, float]] = [(coords[0][0], coords[0][1], 0.0)]
    cum = 0.0
    for a, b in zip(coords, coords[1:]):
        seg = haversine_m(a, b)
        if seg <= 0:
            continue
        steps = max(1, int(seg // resolution_m))
        for i in range(1, steps + 1):
            t = i / steps
            lon = a[0] + (b[0] - a[0]) * t
            lat = a[1] + (b[1] - a[1]) * t
            out.append((lon, lat, cum + seg * t))
        cum += seg
    return out


def compute_gain_loss_grade(
    distances_m: list[float],
    elevations_m: list[float],
    noise_threshold_m: float = DEFAULT_NOISE_THRESHOLD_M,
) -> tuple[float, float, float]:
    """Total gain, total loss (both ≥ 0), and max grade (%) from a sampled series.

    Gain/loss use a minimum-change accumulator: a move is credited only once it
    exceeds `noise_threshold_m` from the last counted elevation, so sub-threshold
    DEM jitter doesn't inflate the totals (D2). Max grade is the steepest
    rise/run between consecutive samples."""
    if len(elevations_m) < 2:
        return 0.0, 0.0, 0.0
    gain = loss = 0.0
    ref = elevations_m[0]
    for elev in elevations_m[1:]:
        delta = elev - ref
        if delta >= noise_threshold_m:
            gain += delta
            ref = elev
        elif -delta >= noise_threshold_m:
            loss += -delta
            ref = elev
    max_grade = 0.0
    for i in range(1, len(elevations_m)):
        run = distances_m[i] - distances_m[i - 1]
        if run > 0:
            grade = abs(elevations_m[i] - elevations_m[i - 1]) / run * 100.0
            max_grade = max(max_grade, grade)
    return gain, loss, max_grade


def build_profile(
    parts: list[list[tuple[float, float]]],
    sampler: ElevationSampler,
    *,
    resolution_m: float = DEFAULT_RESOLUTION_M,
    source: str = "usgs-3dep",
    noise_threshold_m: float = DEFAULT_NOISE_THRESHOLD_M,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
) -> ElevationProfile | None:
    """Sample elevation along the ordered route `parts` and derive the profile.
    `None` (source-or-silence) when there's no usable geometry, fewer than two
    covered samples, or DEM coverage below `min_coverage` of the sampled points."""
    densified: list[tuple[float, float, float]] = []
    cum = 0.0
    last_pt: tuple[float, float] | None = None
    for part in parts:
        if not part:
            continue
        if last_pt is not None:
            # Bridge a between-parts gap by distance only — do NOT densely sample the
            # bridge (it isn't real trail). Keeps distances monotonic + honest.
            cum += haversine_m(last_pt, part[0])
        local = densify(part, resolution_m)
        densified.extend((lon, lat, cum + d) for lon, lat, d in local)
        if local:
            cum += local[-1][2]
        last_pt = part[-1]

    if len(densified) < 2:
        return None

    distances: list[float] = []
    elevations: list[float] = []
    for lon, lat, dist in densified:
        elev = sampler.sample(lon, lat)
        if elev is not None:
            distances.append(dist)
            elevations.append(float(elev))

    if len(elevations) < 2:
        log.info("Elevation: no DEM coverage along route (source-or-silence → null)")
        return None
    coverage = len(elevations) / len(densified)
    if coverage < min_coverage:
        log.info(
            "Elevation: coverage %.0f%% below %.0f%% threshold → null",
            coverage * 100,
            min_coverage * 100,
        )
        return None

    gain, loss, max_grade = compute_gain_loss_grade(distances, elevations, noise_threshold_m)
    return ElevationProfile(
        distances_m=distances,
        elevations_m=elevations,
        total_gain_m=gain,
        total_loss_m=loss,
        max_grade_pct=max_grade,
        source=source,
        resolution_m=resolution_m,
    )


def _wkt_parts(wkt: str | None) -> list[list[tuple[float, float]]]:
    """The ordered coordinate runs of a (route) WKT — one per assembled-route part."""
    return [list(line.coords) for line in line_parts(parse_wkt(wkt))]


def build_profile_from_wkt(
    wkt: str | None,
    sampler: ElevationSampler,
    *,
    resolution_m: float = DEFAULT_RESOLUTION_M,
    source: str = "usgs-3dep",
    noise_threshold_m: float = DEFAULT_NOISE_THRESHOLD_M,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
) -> ElevationProfile | None:
    """Build a profile from a stored route WKT (the assembled `geom_wkt`). `None`
    when the WKT carries no line (Rule #1)."""
    parts = _wkt_parts(wkt)
    if not parts:
        return None
    return build_profile(
        parts,
        sampler,
        resolution_m=resolution_m,
        source=source,
        noise_threshold_m=noise_threshold_m,
        min_coverage=min_coverage,
    )
