"""GPX reader-tolerance module (Epic 031, Phase-C C1 — built pre-Phase-C, additive).

Turns a noisy real-world GPX export (Strava/Garmin) into a list of cleaned,
free-floating tracks: consecutive near-duplicate points dropped, degenerate
(<2-point) segments removed, and partial/missing timestamps corrected with
every synthesized timestamp flagged `derived` (Rule #1 — source-or-silence).
No map-matching, no database, no network, no auth surface.

Attribution: parses via gpxpy (Apache-2.0) — https://github.com/tkrajina/gpxpy.
The cleaning heuristics (dedupe / <2pt-drop / timestamp correction) are
re-derived from the CoMaps `serdes_gpx.cpp` C1 spec (pattern-only; no code
copied — see docs/research/comaps-borrow-plan.md wave C).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

_GPX_REQUIRED = "gpxpy"

EPSILON_M = 1.0  # analog of CoMaps kMwmPointAccuracy
_EARTH_RADIUS_M = 6_371_000.0


@dataclass(frozen=True)
class CleanTrack:
    points: list[tuple[float, float, float | None]]  # (lat, lon, ele|None)
    timestamps: list[datetime | None]  # one per point (parallel)
    timestamps_derived: list[bool]  # True iff synthesized (Rule #1)
    timestamps_cleared: bool  # True iff >50% invalid → all cleared


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1_r, lon1_r, lat2_r, lon2_r = (radians(v) for v in (lat1, lon1, lat2, lon2))
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = sin(dlat / 2) ** 2 + cos(lat1_r) * cos(lat2_r) * sin(dlon / 2) ** 2
    a = min(1.0, a)  # guard fp rounding past 1.0 for near-antipodal inputs (asin domain)
    return 2 * _EARTH_RADIUS_M * asin(sqrt(a))


def _dedupe(
    points: list[tuple[float, float, float | None]],
    timestamps: list[datetime | None],
    epsilon_m: float,
) -> tuple[list[tuple[float, float, float | None]], list[datetime | None]]:
    """Drop point i when it is < epsilon_m from the last *kept* point.

    Re-derived from CoMaps' Pop()-at-kTrkPt (not gpxpy's reduce_points, which
    reshuffles indices and would desync the parallel timestamp array).
    """
    kept_points: list[tuple[float, float, float | None]] = []
    kept_timestamps: list[datetime | None] = []
    for (lat, lon, ele), ts in zip(points, timestamps):
        if kept_points:
            last_lat, last_lon, _ = kept_points[-1]
            if _haversine_m(last_lat, last_lon, lat, lon) < epsilon_m:
                continue
        kept_points.append((lat, lon, ele))
        kept_timestamps.append(ts)
    return kept_points, kept_timestamps


def _normalize_timestamps(timestamps: list[datetime | None]) -> list[datetime | None]:
    """Replace missing/non-monotonic/tz-inconsistent timestamps with None (AC-3.1)."""
    normalized: list[datetime | None] = []
    last_valid: datetime | None = None
    for ts in timestamps:
        valid = ts is not None
        if valid and last_valid is not None and ts is not None:
            try:
                valid = ts > last_valid
            except TypeError:
                # Mixed tz-awareness (naive vs aware) — fail-soft, not a crash.
                valid = False
        if valid:
            normalized.append(ts)
            last_valid = ts
        else:
            normalized.append(None)
    return normalized


def _correct_timestamps(
    timestamps: list[datetime | None],
) -> tuple[list[datetime | None], list[bool], bool]:
    """Normalize, then clear (>50% invalid) or interpolate/edge-fill (AC-3.2/3.3)."""
    n = len(timestamps)
    normalized = _normalize_timestamps(timestamps)
    invalid_count = sum(1 for t in normalized if t is None)
    if invalid_count > n / 2:
        return [None] * n, [False] * n, True

    result = list(normalized)
    derived = [False] * n
    valid_indices = [i for i, t in enumerate(normalized) if t is not None]

    if valid_indices:
        first_valid = valid_indices[0]
        for i in range(first_valid):
            result[i] = normalized[first_valid]
            derived[i] = True

        last_valid = valid_indices[-1]
        for i in range(last_valid + 1, n):
            result[i] = normalized[last_valid]
            derived[i] = True

        for a, b in zip(valid_indices, valid_indices[1:]):
            if b - a <= 1:
                continue
            t_i, t_j = normalized[a], normalized[b]
            assert t_i is not None and t_j is not None  # by construction (valid_indices)
            span = t_j - t_i
            for k in range(a + 1, b):
                result[k] = t_i + span * ((k - a) / (b - a))
                derived[k] = True

    return result, derived, False


def read_gpx(source: str | Path | bytes, *, epsilon_m: float = EPSILON_M) -> list[CleanTrack]:
    """Parse a GPX file/bytes into cleaned, free-floating tracks.

    `source` as `str`/`Path` is read as a filesystem path; `bytes` is raw GPX
    content. Reads only <trk>/<trkseg>/<trkpt> geometry + time — extensions,
    waypoints, routes, and names/descriptions are never read (Rule #5).
    """
    try:
        import gpxpy  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(f"{_GPX_REQUIRED} not installed. Run: pip install gpxpy") from exc

    if isinstance(source, bytes):
        text = source.decode("utf-8")
    else:
        text = Path(source).read_text(encoding="utf-8")

    gpx = gpxpy.parse(text)

    tracks: list[CleanTrack] = []
    for track in gpx.tracks:
        for segment in track.segments:
            raw_points = [(p.latitude, p.longitude, p.elevation) for p in segment.points]
            raw_timestamps = [p.time for p in segment.points]

            points, timestamps = _dedupe(raw_points, raw_timestamps, epsilon_m)
            if len(points) < 2:
                continue

            corrected, derived, cleared = _correct_timestamps(timestamps)
            tracks.append(
                CleanTrack(
                    points=points,
                    timestamps=corrected,
                    timestamps_derived=derived,
                    timestamps_cleared=cleared,
                )
            )

    return tracks
