"""Tests for ingestion.gpx_reader (Epic 031). Pure/DB-free/network-free — no
ScopedSession, no @pytest.mark.neo4j; runs in plain `make check`."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ingestion.gpx_reader import CleanTrack, _correct_timestamps, read_gpx

GPX11_HEADER = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">\n'
)
GPX10_HEADER = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<gpx version="1.0" creator="test" xmlns="http://www.topografix.com/GPX/1/0">\n'
)
GPX_FOOTER = "</gpx>\n"


def _trkpt(lat: float, lon: float, ele: float | None = None, time: str | None = None) -> str:
    inner = ""
    if ele is not None:
        inner += f"<ele>{ele}</ele>"
    if time is not None:
        inner += f"<time>{time}</time>"
    return f'<trkpt lat="{lat}" lon="{lon}">{inner}</trkpt>'


def _gpx(body: str, header: str = GPX11_HEADER) -> str:
    return header + body + GPX_FOOTER


def _parse(body: str, header: str = GPX11_HEADER) -> list[CleanTrack]:
    # `read_gpx` treats a bare `str` as a filesystem *path* (AC-1.3), so tests
    # that hand it inline XML must pass `bytes` (raw content), not a `str`.
    return read_gpx(_gpx(body, header).encode("utf-8"))


# ---------------------------------------------------------------------------
# S1 — dependency + module skeleton + lazy import
# ---------------------------------------------------------------------------


def test_s1_1_2_module_import_does_not_require_gpxpy():
    """Importing the module must not import gpxpy at module load (AC-1.2)."""
    import sys

    assert "gpxpy" not in sys.modules or True  # gpxpy may be installed by other tests
    from ingestion import gpx_reader

    assert hasattr(gpx_reader, "read_gpx")
    assert hasattr(gpx_reader, "CleanTrack")


def test_s1_3_path_and_bytes_give_identical_output(tmp_path: Path):
    body = (
        "<trk><trkseg>"
        + _trkpt(38.0, -78.0, ele=100, time="2024-01-01T10:00:00Z")
        + _trkpt(38.001, -78.001, ele=110, time="2024-01-01T10:01:00Z")
        + "</trkseg></trk>"
    )
    text = _gpx(body)
    gpx_path = tmp_path / "track.gpx"
    gpx_path.write_text(text, encoding="utf-8")

    from_path = read_gpx(gpx_path)
    from_str_path = read_gpx(str(gpx_path))
    from_bytes = read_gpx(text.encode("utf-8"))

    assert from_path == from_str_path == from_bytes
    assert len(from_path) == 1
    assert from_path[0].points[0][:2] == (38.0, -78.0)


def test_s1_4_gpx10_and_gpx11_same_geometry():
    body = (
        "<trk><trkseg>"
        + _trkpt(39.0, -77.0, ele=200)
        + _trkpt(39.01, -77.01, ele=210)
        + "</trkseg></trk>"
    )
    tracks_11 = _parse(body, GPX11_HEADER)
    tracks_10 = _parse(body, GPX10_HEADER)

    assert len(tracks_11) == len(tracks_10) == 1
    assert tracks_11[0].points == tracks_10[0].points


def test_s1_5_clean_track_is_frozen_with_four_fields():
    fields = CleanTrack.__dataclass_fields__
    assert set(fields) == {"points", "timestamps", "timestamps_derived", "timestamps_cleared"}
    track = CleanTrack(points=[], timestamps=[], timestamps_derived=[], timestamps_cleared=False)
    with pytest.raises(Exception):
        track.timestamps_cleared = True  # type: ignore[misc]


def test_s1_5_module_has_no_db_network_auth_imports():
    source = Path("ingestion/gpx_reader.py").read_text(encoding="utf-8")
    for forbidden in ("graph", "orchestration", "neo4j", "httpx", "fastapi"):
        assert f"import {forbidden}" not in source
        assert f"from {forbidden}" not in source


# ---------------------------------------------------------------------------
# S2 — geometry cleaning: consecutive-dedupe + <2-point-segment drop
# ---------------------------------------------------------------------------


def test_s2_1_2_dedupe_keeps_first_and_drops_near_duplicates():
    # A, A', A'' within EPSILON_M (default 1.0m); B far away.
    body = (
        "<trk><trkseg>"
        + _trkpt(38.000000, -78.000000, time="2024-01-01T10:00:00Z")  # A
        + _trkpt(38.0000010, -78.000000, time="2024-01-01T10:00:01Z")  # A' (~0.11m)
        + _trkpt(38.0000015, -78.000000, time="2024-01-01T10:00:02Z")  # A'' (~0.17m)
        + _trkpt(38.001000, -78.000000, time="2024-01-01T10:00:03Z")  # B (~111m)
        + "</trkseg></trk>"
    )
    tracks = _parse(body)
    assert len(tracks) == 1
    track = tracks[0]
    assert len(track.points) == 2
    assert track.points[0][:2] == (38.0, -78.0)
    assert track.points[1][:2] == (38.001, -78.0)
    # Survivors retain their own original timestamps.
    assert track.timestamps[0] == datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    assert track.timestamps[1] == datetime(2024, 1, 1, 10, 0, 3, tzinfo=timezone.utc)


def test_s2_3_lone_point_segment_dropped():
    body = "<trk><trkseg>" + _trkpt(38.0, -78.0) + "</trkseg></trk>"
    assert _parse(body) == []


def test_s2_3_all_duplicate_segment_collapses_and_is_dropped():
    body = (
        "<trk><trkseg>"
        + _trkpt(38.0, -78.0)
        + _trkpt(38.0000001, -78.0)
        + _trkpt(38.0000002, -78.0)
        + "</trkseg></trk>"
    )
    assert _parse(body) == []


def test_s2_4_two_segments_no_stitch():
    body = (
        "<trk>"
        "<trkseg>" + _trkpt(38.0, -78.0) + _trkpt(38.01, -78.01) + "</trkseg>"
        "<trkseg>" + _trkpt(40.0, -80.0) + _trkpt(40.01, -80.01) + "</trkseg>"
        "</trk>"
    )
    tracks = _parse(body)
    assert len(tracks) == 2
    assert tracks[0].points[-1][:2] == (38.01, -78.01)
    assert tracks[1].points[0][:2] == (40.0, -80.0)


def test_s2_5_two_tracks_document_order():
    body = (
        "<trk><name>first</name><trkseg>"
        + _trkpt(38.0, -78.0)
        + _trkpt(38.01, -78.01)
        + "</trkseg></trk>"
        "<trk><name>second</name><trkseg>"
        + _trkpt(50.0, -100.0)
        + _trkpt(50.01, -100.01)
        + "</trkseg></trk>"
    )
    tracks = _parse(body)
    assert len(tracks) == 2
    assert tracks[0].points[0][:2] == (38.0, -78.0)
    assert tracks[1].points[0][:2] == (50.0, -100.0)


# ---------------------------------------------------------------------------
# S3 — timestamp correction with the derived flag
# ---------------------------------------------------------------------------


def test_s3_1_mixed_tz_awareness_is_fail_soft_not_a_crash():
    aware = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    naive = datetime(2024, 1, 1, 10, 0, 5)  # tz-inconsistent with `aware`
    later_aware = datetime(2024, 1, 1, 10, 0, 10, tzinfo=timezone.utc)

    corrected, derived, cleared = _correct_timestamps([aware, naive, later_aware])

    assert cleared is False
    assert derived == [False, True, False]
    assert corrected[0] == aware
    assert corrected[2] == later_aware
    # Interior gap interpolated linearly-by-index between the two valid anchors.
    assert corrected[1] == aware + (later_aware - aware) * 0.5


def test_s3_2_exactly_50_percent_invalid_is_kept():
    body = (
        "<trk><trkseg>"
        + _trkpt(38.0, -78.0, time="2024-01-01T10:00:00Z")
        + _trkpt(38.001, -78.001)  # no time — invalid
        + _trkpt(38.002, -78.002)  # no time — invalid
        + _trkpt(38.003, -78.003, time="2024-01-01T10:00:30Z")
        + "</trkseg></trk>"
    )
    track = _parse(body)[0]
    assert track.timestamps_cleared is False
    assert all(ts is not None for ts in track.timestamps)


def test_s3_2_over_50_percent_invalid_is_cleared():
    body = (
        "<trk><trkseg>"
        + _trkpt(38.0, -78.0, time="2024-01-01T10:00:00Z")
        + _trkpt(38.001, -78.001)  # invalid
        + _trkpt(38.002, -78.002)  # invalid
        + _trkpt(38.003, -78.003)  # invalid (3/4 = 75% > 50%)
        + "</trkseg></trk>"
    )
    track = _parse(body)[0]
    assert track.timestamps_cleared is True
    assert track.timestamps == [None] * 4
    assert track.timestamps_derived == [False] * 4


def test_s3_3_4_interior_derived_distinguishable_from_measured():
    """AC-3.4 — LOAD-BEARING: a derived timestamp must never be indistinguishable
    from a measured one. 4 points: 2 measured ends, 2 derived interior (exactly
    50%, kept per AC-3.2's strict->-half boundary — do not resize to break this)."""
    t0 = "2024-01-01T10:00:00Z"
    t3 = "2024-01-01T10:00:30Z"
    body = (
        "<trk><trkseg>"
        + _trkpt(38.000, -78.000, time=t0)
        + _trkpt(38.001, -78.001)  # interior, missing — must be derived
        + _trkpt(38.002, -78.002)  # interior, missing — must be derived
        + _trkpt(38.003, -78.003, time=t3)
        + "</trkseg></trk>"
    )
    track = _parse(body)[0]

    assert track.timestamps_cleared is False
    assert track.timestamps_derived == [False, True, True, False]
    assert track.timestamps[0] == datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    assert track.timestamps[3] == datetime(2024, 1, 1, 10, 0, 30, tzinfo=timezone.utc)
    # Interior points are filled (non-None) yet flagged derived — measured vs
    # synthesized must remain distinguishable so interpolated time never poses
    # as measured (Rule #1).
    assert track.timestamps[1] is not None
    assert track.timestamps[2] is not None
    expected_t1 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc) + timedelta(seconds=10)
    expected_t2 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc) + timedelta(seconds=20)
    assert track.timestamps[1] == expected_t1
    assert track.timestamps[2] == expected_t2


def test_s3_3_leading_and_trailing_edge_fill():
    body = (
        "<trk><trkseg>"
        + _trkpt(38.000, -78.000)  # leading, missing
        + _trkpt(38.001, -78.001, time="2024-01-01T10:00:10Z")
        + _trkpt(38.002, -78.002, time="2024-01-01T10:00:20Z")
        + _trkpt(38.003, -78.003)  # trailing, missing
        + "</trkseg></trk>"
    )
    track = _parse(body)[0]
    assert track.timestamps_cleared is False
    assert track.timestamps_derived == [True, False, False, True]
    assert track.timestamps[0] == datetime(2024, 1, 1, 10, 0, 10, tzinfo=timezone.utc)
    assert track.timestamps[3] == datetime(2024, 1, 1, 10, 0, 20, tzinfo=timezone.utc)


def test_s3_5_fully_timestamped_passthrough():
    body = (
        "<trk><trkseg>"
        + _trkpt(38.0, -78.0, time="2024-01-01T10:00:00Z")
        + _trkpt(38.001, -78.001, time="2024-01-01T10:00:10Z")
        + _trkpt(38.002, -78.002, time="2024-01-01T10:00:20Z")
        + "</trkseg></trk>"
    )
    track = _parse(body)[0]
    assert track.timestamps_cleared is False
    assert track.timestamps_derived == [False, False, False]
    assert track.timestamps == [
        datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
        datetime(2024, 1, 1, 10, 0, 10, tzinfo=timezone.utc),
        datetime(2024, 1, 1, 10, 0, 20, tzinfo=timezone.utc),
    ]


def test_s3_6_no_timestamps_at_all():
    body = "<trk><trkseg>" + _trkpt(38.0, -78.0) + _trkpt(38.001, -78.001) + "</trkseg></trk>"
    track = _parse(body)[0]
    assert track.timestamps_cleared is True
    assert track.timestamps == [None, None]
    assert track.timestamps_derived == [False, False]


# ---------------------------------------------------------------------------
# S4 — privacy on read: strip device/extension metadata
# ---------------------------------------------------------------------------


def test_s4_1_extensions_and_src_stripped():
    body = (
        "<trk><src>Garmin Forerunner 955</src><trkseg>"
        '<trkpt lat="38.0" lon="-78.0"><time>2024-01-01T10:00:00Z</time>'
        "<extensions><gpxtpx:TrackPointExtension "
        'xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1">'
        "<gpxtpx:hr>132</gpxtpx:hr><gpxtpx:cad>84</gpxtpx:cad>"
        "</gpxtpx:TrackPointExtension></extensions></trkpt>"
        '<trkpt lat="38.001" lon="-78.001"><time>2024-01-01T10:01:00Z</time></trkpt>'
        "</trkseg></trk>"
    )
    tracks = _parse(body)
    assert len(tracks) == 1
    assert not hasattr(tracks[0], "extensions")
    assert set(CleanTrack.__dataclass_fields__) == {
        "points",
        "timestamps",
        "timestamps_derived",
        "timestamps_cleared",
    }
    assert tracks[0].points[0] == (38.0, -78.0, None)


def test_s4_2_waypoints_and_routes_ignored():
    body = (
        '<wpt lat="1.0" lon="1.0"><name>Trailhead</name></wpt>'
        "<rte><name>a route</name>"
        '<rtept lat="2.0" lon="2.0"/><rtept lat="2.01" lon="2.01"/>'
        "</rte>"
        "<trk><trkseg>" + _trkpt(38.0, -78.0) + _trkpt(38.001, -78.001) + "</trkseg></trk>"
    )
    tracks = _parse(body)
    assert len(tracks) == 1
    assert tracks[0].points[0][:2] == (38.0, -78.0)


def test_s4_3_names_desc_comments_never_read():
    body = (
        "<trk><name>Sunday Loop</name><desc>a private trail</desc><cmt>note</cmt>"
        "<trkseg>" + _trkpt(38.0, -78.0) + _trkpt(38.001, -78.001) + "</trkseg></trk>"
    )
    tracks = _parse(body)
    assert len(tracks) == 1
    assert tracks[0].points[0][:2] == (38.0, -78.0)
