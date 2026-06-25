"""Tests for ingestion.commons_fork — the de-identification transforms (Epic 010).

Pure functions, no DB. Covers the S3 quasi-identifier reduction (band/buckets/
trim) and S4 writer_hash ACs. The end-to-end "fork actually fires + is unlinkable"
suite lives in tests/test_commons_privacy.py.

Test names follow: test_s{story}_{ac}_{description}
"""

from __future__ import annotations

from datetime import datetime

from ingestion import commons_fork as cf

_SALT = "test-salt-not-a-real-secret"


def _straight_track(n: int = 30, step_lon: float = 0.0006) -> list[tuple[float, float]]:
    """A ~1.5km straight track (~52m/step at lat 38.5) — long enough to trim."""
    return [(38.5, -78.40 + i * step_lon) for i in range(n)]


# ── S3 — capability band (raw pace → 4 half-open bands, S9-9) ─────────────────


def test_s3_ac4_capability_band_boundaries_half_open() -> None:
    """AC-3.4: half-open [lo, hi) — the four boundary cases land correctly."""
    assert cf.capability_band(11.99) == "easy"
    assert cf.capability_band(12.0) == "easy-moderate"
    assert cf.capability_band(16.0) == "moderate"
    assert cf.capability_band(20.0) == "strenuous"
    # interior sanity
    assert cf.capability_band(5.0) == "easy"
    assert cf.capability_band(25.0) == "strenuous"


def test_s3_ac4_capability_band_in_allowed_set() -> None:
    assert cf.capability_band(14.0) in {"easy", "easy-moderate", "moderate", "strenuous"}


def test_s3_ac4_capability_band_none_when_no_pace() -> None:
    assert cf.capability_band(None) is None


# ── S3 — coarse buckets (never the raw total) ────────────────────────────────


def test_s3_ac6_ascent_bucket_is_coarse_not_raw() -> None:
    """AC-3.6: ascent bucketed in 200m bands, not the raw value."""
    assert cf.ascent_bucket(735.0) == "600-800"
    assert cf.ascent_bucket(800.0) == "800-1000"
    assert cf.ascent_bucket(735.0) != 735.0
    assert cf.ascent_bucket(None) is None


def test_s3_ac6_distance_bucket_is_coarse_not_raw() -> None:
    assert cf.distance_bucket(15000.0) == "15-20km"
    assert cf.distance_bucket(4900.0) == "0-5km"
    assert cf.distance_bucket(15000.0) != 15000.0


# ── S3 — month bucket (never the raw date) ───────────────────────────────────


def test_s3_ac5_month_bucket_year_month_only() -> None:
    """AC-3.5: 'YYYY-MM', matches the regex, no day/time."""
    import re

    m = cf.month_bucket(datetime(2026, 6, 24, 13, 30, 5))
    assert m == "2026-06"
    assert re.fullmatch(r"\d{4}-\d{2}", m or "")
    assert "24" not in (m or "")  # the day never appears


def test_s3_ac5_month_bucket_accepts_iso_string() -> None:
    assert cf.month_bucket("2026-06-24T13:30:00+00:00") == "2026-06"
    assert cf.month_bucket(None) is None


# ── S3 — endpoint trim (the re-ID vector) ────────────────────────────────────


def test_s3_ac2_endpoint_trim_fires_beyond_250m() -> None:
    """AC-3.2: trimmed start/end are provably >250m from the raw start/end."""
    track = _straight_track()
    trimmed = cf.endpoint_trim(track)
    assert trimmed is not None
    assert cf._haversine_m(trimmed[0], track[0]) > cf.TRIM_RADIUS_M
    assert cf._haversine_m(trimmed[-1], track[-1]) > cf.TRIM_RADIUS_M
    # the trimmed track is a strict interior subset
    assert track[0] not in trimmed and track[-1] not in trimmed
    assert len(trimmed) < len(track)


def test_s3_ac3_endpoint_trim_none_without_gps() -> None:
    """AC-3.3: no track → None (degrade gracefully)."""
    assert cf.endpoint_trim(None) is None
    assert cf.endpoint_trim([]) is None
    assert cf.endpoint_trim([(38.5, -78.4)]) is None  # single point


def test_s3_short_track_that_never_clears_radius_returns_none() -> None:
    """A track entirely within the trim radius leaves nothing to keep."""
    tiny = [(38.5, -78.4 + i * 0.00001) for i in range(5)]  # ~1m steps, ~4m total
    assert cf.endpoint_trim(tiny) is None


def test_s3_track_to_wkt_lon_lat_order() -> None:
    wkt = cf.track_to_wkt([(38.5, -78.4), (38.6, -78.3)])
    assert wkt == "LINESTRING(-78.4 38.5, -78.3 38.6)"
    assert cf.track_to_wkt(None) is None


# ── S4 — writer_hash (one-way, salted, not a quasi-identifier) ───────────────


def test_s4_ac1_writer_hash_deterministic_and_distinct() -> None:
    """AC-4.1: same member → same hash; different members → different hashes."""
    h1 = cf.writer_hash("mem:josh", _SALT)
    h2 = cf.writer_hash("mem:josh", _SALT)
    h3 = cf.writer_hash("mem:carter", _SALT)
    assert h1 == h2
    assert h1 != h3


def test_s4_ac1_writer_hash_is_salted_not_plain_digest() -> None:
    """AC-4.1: HMAC, not a plain hash — a different salt yields a different hash,
    so the small member-id space cannot be brute-forced without the salt."""
    import hashlib

    h = cf.writer_hash("mem:josh", _SALT)
    assert h != cf.writer_hash("mem:josh", "different-salt")
    assert h != hashlib.sha256(b"mem:josh").hexdigest()  # not a plain digest


def test_s4_ac3_writer_hash_not_member_id() -> None:
    """AC-4.3: the hash is not the member_id and the id is not in it."""
    h = cf.writer_hash("mem:josh", _SALT)
    assert h != "mem:josh"
    assert "mem:josh" not in h
    assert len(h) == 64  # sha256 hex


# ── S3/S4 — build_observation: only de-identified values cross ───────────────


def test_s3_build_observation_carries_no_raw_quasi_identifier() -> None:
    """AC-3.4/3.5/3.6 + AC-5.3: no observation property equals the raw pace,
    distance, ascent, or date; band/buckets/month are present instead."""
    obs = cf.build_observation(
        member_id="mem:josh",
        salt=_SALT,
        trail_id="ct:old-rag-loop",
        pace_on_grade=17.3,
        distance_m=15000.0,
        ascent_m=735.0,
        start_time=datetime(2026, 6, 24, 13, 30, 5),
        gps_track=_straight_track(),
    )
    values = list(obs.values())
    assert 17.3 not in values and "17.3" not in values  # raw pace absent
    assert 15000.0 not in values
    assert 735.0 not in values
    assert not any("2026-06-24" in str(v) for v in values)  # raw date absent
    # de-identified values present
    assert obs["capability_band"] == "moderate"
    assert obs["month"] == "2026-06"
    assert obs["ascent_bucket"] == "600-800"
    assert obs["distance_bucket"] == "15-20km"
    assert obs["trimmed_track"].startswith("LINESTRING(")
    assert obs["ingest_version"] == cf.INGEST_VERSION


def test_s2_build_observation_has_no_owner_id() -> None:
    """AC-2.2: the observation carries no owner_id (severed by construction)."""
    obs = cf.build_observation(
        member_id="mem:josh",
        salt=_SALT,
        trail_id=None,
        pace_on_grade=10.0,
        distance_m=3000.0,
        ascent_m=100.0,
        start_time=datetime(2026, 1, 2),
        gps_track=None,
    )
    assert "owner_id" not in obs
    assert obs["trail_id"] is None  # null when unmatched
    assert obs["trimmed_track"] is None  # AC-3.3: null with no GPS
    assert obs["writer_hash"]  # but the revocation handle is still written


def test_s4_ac2_salt_never_in_observation() -> None:
    """AC-4.2: the salt never appears on any observation property."""
    obs = cf.build_observation(
        member_id="mem:josh",
        salt=_SALT,
        trail_id="ct:x",
        pace_on_grade=14.0,
        distance_m=9000.0,
        ascent_m=300.0,
        start_time=datetime(2026, 6, 1),
        gps_track=_straight_track(),
    )
    assert all(_SALT not in str(v) for v in obs.values())
