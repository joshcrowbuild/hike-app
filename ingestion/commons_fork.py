"""Commons fork — contributor-side de-identification transforms (Epic 010).

Pure functions (no DB, no model call — Stage 9 §4.1, AC-3.7) that reduce an
episode's raw, identifying signals to the bucketed/banded values a born-severed
`:CommonsObservation` may carry (Stage 9 §2). Every high-entropy field is reduced
*before* it crosses into the commons node: the raw pace becomes a 4-band
capability label, the raw date a month bucket, the raw totals coarse buckets, and
the GPS track has its identifying endpoints trimmed.

`build_observation` assembles the property dict for the `CREATE` (the Cypher is in
`graph.queries.create_commons_observation`). `observation_id` (randomUUID) and
`written_at` (datetime) are generated server-side in Cypher, not here.

Privacy invariants this module upholds (proven in tests/test_commons_fork.py +
tests/test_commons_privacy.py): no raw quasi-identifier (pace/date/totals) ever
appears on the observation; the trimmed track's endpoints are provably >250m from
the raw track's; the writer_hash is one-way (HMAC) and the salt never returned.
"""

from __future__ import annotations

import hashlib
import hmac
import math
from datetime import datetime
from typing import Any, Sequence

# v0 de-id parameters (Stage 9 §2.2 / §4.2 — provisional, tuned against accreted
# volume before public release; this epic uses the seeds).
TRIM_RADIUS_M = 250.0
ASCENT_BAND_M = 200
DISTANCE_BAND_KM = 5
# Stamps which de-id ruleset produced a row, so a future re-fit knows the vintage.
INGEST_VERSION = "commons-deid-v0"

# Capability bands (S9-9, supersedes S5-11): half-open [lo, hi) so no value falls
# in two bands. Grade-adjusted pace in min/km.
_BAND_CUTOFFS: tuple[tuple[float, str], ...] = (
    (12.0, "easy"),
    (16.0, "easy-moderate"),
    (20.0, "moderate"),
)
_BAND_TOP = "strenuous"


def capability_band(pace_on_grade: float | None) -> str | None:
    """Raw grade-adjusted pace → one of the 4 S9-9 bands (half-open `[lo, hi)`).
    Returns None only when there is no pace to band (degrade, not a default band)."""
    if pace_on_grade is None:
        return None
    for hi, label in _BAND_CUTOFFS:
        if pace_on_grade < hi:
            return label
    return _BAND_TOP


def ascent_bucket(ascent_m: float | None) -> str | None:
    """Coarse ascent band (200m), e.g. `"600-800"` — never the raw total."""
    if ascent_m is None:
        return None
    lo = int(ascent_m // ASCENT_BAND_M) * ASCENT_BAND_M
    return f"{lo}-{lo + ASCENT_BAND_M}"


def distance_bucket(distance_m: float | None) -> str | None:
    """Coarse distance band (5km), e.g. `"15-20km"` — never the raw total."""
    if distance_m is None:
        return None
    lo = int((distance_m / 1000.0) // DISTANCE_BAND_KM) * DISTANCE_BAND_KM
    return f"{lo}-{lo + DISTANCE_BAND_KM}km"


def month_bucket(start_time: datetime | str | None) -> str | None:
    """`"YYYY-MM"` from the episode start — never the raw date/day/timestamp."""
    if start_time is None:
        return None
    if isinstance(start_time, datetime):
        return start_time.strftime("%Y-%m")
    s = str(start_time)
    # accept a leading ISO-ish "YYYY-MM..." string; otherwise no month
    return s[:7] if len(s) >= 7 and s[4] == "-" and s[:4].isdigit() else None


def _haversine_m(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    """Great-circle distance in metres between (lat, lon) points."""
    r = 6_371_000.0
    lat1, lon1 = p1
    lat2, lon2 = p2
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def endpoint_trim(
    track: Sequence[tuple[float, float]] | None, radius_m: float = TRIM_RADIUS_M
) -> list[tuple[float, float]] | None:
    """Strip leading points within `radius_m` (straight-line) of the start and
    trailing points within `radius_m` of the end (Stage 9 §2.2 / S5-10). The
    surviving endpoints are therefore provably >`radius_m` from the raw endpoints
    — the trailhead/home cluster, the dominant re-ID vector, is removed. Returns
    None when there is no track or nothing survives the trim."""
    if not track or len(track) < 2:
        return None
    start, end = track[0], track[-1]
    start_idx = next(
        (i for i in range(len(track)) if _haversine_m(track[i], start) > radius_m), None
    )
    end_idx = next(
        (i for i in range(len(track) - 1, -1, -1) if _haversine_m(track[i], end) > radius_m), None
    )
    if start_idx is None or end_idx is None or start_idx > end_idx:
        return None
    trimmed = list(track[start_idx : end_idx + 1])
    return trimmed if len(trimmed) >= 2 else None


def track_to_wkt(track: Sequence[tuple[float, float]] | None) -> str | None:
    """Render a (lat, lon) track as a WKT `LINESTRING(lon lat, ...)`; None if empty."""
    if not track:
        return None
    pts = ", ".join(f"{lon} {lat}" for lat, lon in track)
    return f"LINESTRING({pts})"


def writer_hash(member_id: str, salt: str) -> str:
    """One-way HMAC-SHA256(salt, member_id) — deterministic (a member's rows are
    findable for revocation), non-reversible (the salt stays in the secrets store,
    never the graph), and not a quasi-identifier (a single opaque value). HMAC, not
    a plain hash: the member-id space is small + enumerable, so a plain digest is
    brute-forceable; the keyed salt defeats a dictionary attack (Stage 9 §2.3)."""
    return hmac.new(salt.encode("utf-8"), member_id.encode("utf-8"), hashlib.sha256).hexdigest()


def build_observation(
    *,
    member_id: str,
    salt: str,
    trail_id: str | None,
    pace_on_grade: float | None,
    distance_m: float | None,
    ascent_m: float | None,
    start_time: datetime | str | None,
    gps_track: Sequence[tuple[float, float]] | None,
    segment_ids: Sequence[str] | None = None,
    ingest_version: str = INGEST_VERSION,
) -> dict[str, Any]:
    """Assemble the de-identified `:CommonsObservation` property dict. Every raw
    input is reduced to a band/bucket (or trimmed) here, contributor-side, before
    it could ever cross into the commons node — the raw pace/date/totals/full track
    never enter the observation (Stage 9 §4.1). Pure: no DB, no model call."""
    trimmed = endpoint_trim(gps_track)
    return {
        "trail_id": trail_id,  # FK-by-value to the unowned world layer (no edge)
        "segment_ids": list(segment_ids or []),
        "capability_band": capability_band(pace_on_grade),
        "month": month_bucket(start_time),
        "ascent_bucket": ascent_bucket(ascent_m),
        "distance_bucket": distance_bucket(distance_m),
        "trimmed_track": track_to_wkt(trimmed),
        "writer_hash": writer_hash(member_id, salt),
        "ingest_version": ingest_version,
    }
