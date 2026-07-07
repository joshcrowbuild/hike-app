"""Unit tests for `api/gpx.py::build_gpx` (Epic 028 S1).

Covers the GPX 1.1 wire-format ACs (header/footer, one trk/seg, coordinate order +
formatting, XML-escaped name, the D4.3 altitude gate, the optional trailhead `<wpt>`)
and well-formedness. No I/O, no graph — pure serializer tests.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import pytest

from api.gpx import build_gpx

_GPX_NS = "{http://www.topografix.com/GPX/1/1}"

_COORDS = [(-78.30, 38.55), (-78.29, 38.56), (-78.28, 38.57)]


def test_header_and_footer():
    xml = build_gpx("Old Rag Loop", _COORDS, elevations=None, elev_source=None, trailhead=None)
    assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert '<gpx version="1.1" creator="Adventure Planner"' in xml
    assert 'xmlns="http://www.topografix.com/GPX/1/1"' in xml
    assert xml.rstrip().endswith("</gpx>")
    assert "CoMaps" not in xml


def test_one_trk_one_trkseg_points_in_route_order():
    xml = build_gpx("Old Rag Loop", _COORDS, elevations=None, elev_source=None, trailhead=None)
    root = ET.fromstring(xml)
    trks = root.findall(f"{_GPX_NS}trk")
    assert len(trks) == 1
    trksegs = trks[0].findall(f"{_GPX_NS}trkseg")
    assert len(trksegs) == 1
    pts = trksegs[0].findall(f"{_GPX_NS}trkpt")
    assert len(pts) == len(_COORDS)
    for pt, (lon, lat) in zip(pts, _COORDS):
        assert float(pt.get("lat")) == pytest.approx(lat)
        assert float(pt.get("lon")) == pytest.approx(lon)


def test_coordinate_formatting_has_no_scientific_notation():
    xml = build_gpx(
        "Trail", [(-0.000001234, 38.0000001)], elevations=None, elev_source=None, trailhead=None
    )
    assert not re.search(r"[eE][+-]\d", xml)


def test_name_is_xml_escaped():
    xml = build_gpx(
        "Ridge & River <Loop>", _COORDS, elevations=None, elev_source=None, trailhead=None
    )
    assert "<Loop>" not in xml.split("<trkseg>")[0].split("<name>")[1]
    root = ET.fromstring(xml)  # would raise if the name broke well-formedness
    name_el = root.find(f"{_GPX_NS}trk/{_GPX_NS}name")
    assert name_el.text == "Ridge & River <Loop>"


def test_altitude_present_when_source_and_length_match():
    xml = build_gpx(
        "Old Rag Loop",
        _COORDS,
        elevations=[600.0, 680.0, 900.0],
        elev_source="usgs-3dep",
        trailhead=None,
    )
    root = ET.fromstring(xml)
    pts = root.findall(f"{_GPX_NS}trk/{_GPX_NS}trkseg/{_GPX_NS}trkpt")
    eles = [pt.find(f"{_GPX_NS}ele") for pt in pts]
    assert all(e is not None for e in eles)
    assert [float(e.text) for e in eles] == [600.0, 680.0, 900.0]


def test_altitude_absent_when_no_elev_source():
    xml = build_gpx(
        "Trail", _COORDS, elevations=[600.0, 680.0, 900.0], elev_source=None, trailhead=None
    )
    root = ET.fromstring(xml)
    pts = root.findall(f"{_GPX_NS}trk/{_GPX_NS}trkseg/{_GPX_NS}trkpt")
    assert all(pt.find(f"{_GPX_NS}ele") is None for pt in pts)


def test_altitude_absent_when_length_mismatch_never_partial():
    xml = build_gpx(
        "Trail", _COORDS, elevations=[600.0, 680.0], elev_source="usgs-3dep", trailhead=None
    )
    root = ET.fromstring(xml)
    pts = root.findall(f"{_GPX_NS}trk/{_GPX_NS}trkseg/{_GPX_NS}trkpt")
    assert all(pt.find(f"{_GPX_NS}ele") is None for pt in pts)


def test_altitude_absent_when_elevations_none():
    xml = build_gpx("Trail", _COORDS, elevations=None, elev_source="usgs-3dep", trailhead=None)
    root = ET.fromstring(xml)
    pts = root.findall(f"{_GPX_NS}trk/{_GPX_NS}trkseg/{_GPX_NS}trkpt")
    assert all(pt.find(f"{_GPX_NS}ele") is None for pt in pts)


def test_wpt_present_with_name_when_trailhead_given():
    xml = build_gpx(
        "Old Rag Loop",
        _COORDS,
        elevations=None,
        elev_source=None,
        trailhead=(-78.2861, 38.5707),
    )
    root = ET.fromstring(xml)
    wpts = root.findall(f"{_GPX_NS}wpt")
    assert len(wpts) == 1
    assert float(wpts[0].get("lat")) == pytest.approx(38.5707)
    assert float(wpts[0].get("lon")) == pytest.approx(-78.2861)
    name_el = wpts[0].find(f"{_GPX_NS}name")
    assert name_el.text == "Old Rag Loop trailhead"


def test_wpt_absent_when_no_trailhead():
    xml = build_gpx("Trail", _COORDS, elevations=None, elev_source=None, trailhead=None)
    root = ET.fromstring(xml)
    assert root.findall(f"{_GPX_NS}wpt") == []


def test_well_formed_and_no_forbidden_substrings():
    xml = build_gpx(
        "Old Rag Loop",
        _COORDS,
        elevations=[600.0, 680.0, 900.0],
        elev_source="usgs-3dep",
        trailhead=(-78.2861, 38.5707),
    )
    ET.fromstring(xml)  # raises on malformed XML
    for forbidden in ("gpxx:", "gpx_style:", "xsi:", "<time>", "owner_id", "episode"):
        assert forbidden not in xml
