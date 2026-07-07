"""Epic 036 — deterministic OSM PBF transport (pyosmium) tests.

S1 (`ingestion/fetch/osm_pbf.py`): the local-file transport, unit-tested against
small ad hoc PBFs built with `tests/fixtures/build_synthetic_pbf.write_pbf` —
network-free, file-free where possible (a real temp file is unavoidable for the
transport itself, but nothing here touches `data/osm/` or the real Geofabrik
download).

S5 (this file's namesake): the anti-drift parity guard. It builds the Overpass
equivalent of the committed `tests/fixtures/synthetic_trails.osm.pbf` fixture
(matching OSM ids) and asserts `osm.fetch` (via `httpx.MockTransport`) and
`osm_pbf.fetch` (over the committed fixture) emit the identical `Feature` set —
same classify + gate + ref + geometry (AC-5.2/5.3). No network, no state-PBF
download, no `@pytest.mark.neo4j` (AC-5.4).
"""

from __future__ import annotations

import json

import httpx
from shapely.geometry import LineString

from ingestion.fetch import osm as osm_fetch
from ingestion.fetch import osm_pbf as osm_pbf_fetch
from tests.fixtures.build_synthetic_pbf import FIXTURE_PATH, WAYS, write_pbf

_BBOX = (38.0, -79.0, 39.0, -78.0)  # (south, west, north, east) — covers all 5 ways


def _osm_response(elements: list[dict]) -> httpx.Response:
    body = json.dumps({"elements": elements}).encode()
    return httpx.Response(200, content=body, headers={"content-type": "application/json"})


def _osm_element(way_id: int, tags: dict, coords: list[tuple[float, float]]) -> dict:
    return {
        "type": "way",
        "id": way_id,
        "tags": tags,
        "geometry": [{"lon": c[0], "lat": c[1]} for c in coords],
    }


def _overpass_elements_for(ways) -> list[dict]:
    """Build the Overpass-equivalent elements for a `WaySpec` list — same OSM ids,
    same tags, same coords (AC-5.2's "matching OSM ids")."""
    return [
        _osm_element(way_id, tags, [(lon, lat) for _n, lon, lat in nodes])
        for way_id, tags, nodes in ways
    ]


# ── S1 AC-1.1 — missing file degrades to [] ────────────────────────────────────


def test_missing_pbf_file_returns_empty(tmp_path):
    missing = tmp_path / "nope.osm.pbf"
    assert osm_pbf_fetch.fetch(_BBOX, pbf_path=missing) == []


def test_missing_pbf_file_uses_default_path_when_unset(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no data/osm/region.osm.pbf here
    assert osm_pbf_fetch.fetch(_BBOX) == []


# ── S1 AC-1.2 — a valid way yields a LineString Feature ────────────────────────


def test_valid_way_yields_linestring_feature():
    features = osm_pbf_fetch.fetch(_BBOX, pbf_path=FIXTURE_PATH)
    by_name = {f.name: f for f in features}
    assert "Old Rag Ridge Trail" in by_name
    f = by_name["Old Rag Ridge Trail"]
    assert isinstance(f.geom, LineString)
    assert f.source == "OSM"
    assert f.ref == "way/101"


# ── S1 AC-1.3 — trail filter identical to Overpass: drop residential, unnamed,
# and non-trail-worthy ─────────────────────────────────────────────────────────


def test_residential_and_unnamed_dropped():
    features = osm_pbf_fetch.fetch(_BBOX, pbf_path=FIXTURE_PATH)
    names = {f.name for f in features}
    assert "Random Residential Street" not in names  # (e) highway=residential
    assert len(features) == 3  # (a)/(b)/(c) kept; (d) unnamed + (e) residential dropped


def test_non_trail_worthy_way_dropped(tmp_path):
    # A named highway=path whose name matches the residential-street-suffix
    # denylist (regions/exclusions.json) — trail-worthy gate drops it even
    # though it passes the highway + name checks.
    path = tmp_path / "nontrail.osm.pbf"
    write_pbf(
        path,
        [
            (
                201,
                {"highway": "path", "name": "Foxglove Lane"},
                [(50, -78.5, 38.5), (51, -78.4, 38.6)],
            )
        ],
    )
    assert osm_pbf_fetch.fetch(_BBOX, pbf_path=path) == []


# ── S1 AC-1.4 — classified tags carried onto the Feature ───────────────────────


def test_classified_tags_carried_onto_feature():
    features = osm_pbf_fetch.fetch(_BBOX, pbf_path=FIXTURE_PATH)
    by_name = {f.name: f for f in features}
    f = by_name["Old Rag Ridge Trail"]
    assert f.path_grade == "expert"  # sac_scale=alpine_hiking, highway=path
    assert f.psurface == "unpaved_bad"  # surface=ground
    assert f.foot_access == "yes"  # access=yes


# ── S1 AC-1.5 — bbox clip: bounds-intersect, pure shapely ──────────────────────


def test_bbox_clip_drops_wholly_outside_and_keeps_crossing_with_no_vertex_inside(tmp_path):
    bbox = (38.55, -78.45, 38.70, -78.25)  # south, west, north, east
    ways = [
        # Wholly outside: both vertices east of `east`.
        (
            301,
            {"highway": "path", "name": "Outside Path"},
            [(60, -77.00, 39.00), (61, -76.99, 39.01)],
        ),
        # Crosses the bbox (bounds overlap) but neither vertex is inside it.
        (
            302,
            {"highway": "path", "name": "Crossing Path"},
            [(62, -79.00, 38.60), (63, -78.00, 38.62)],
        ),
    ]
    path = tmp_path / "bboxtest.osm.pbf"
    write_pbf(path, ways)
    features = osm_pbf_fetch.fetch(bbox, pbf_path=path)
    names = {f.name for f in features}
    assert "Outside Path" not in names
    assert "Crossing Path" in names


# ── S5 AC-5.2/5.3 — the parity guard ───────────────────────────────────────────


def _feature_key(f) -> tuple:
    coords = tuple(sorted((round(x, 6), round(y, 6)) for x, y in f.geom.coords))
    return (f.name, f.source, f.ref, f.way_type, f.path_grade, f.psurface, f.foot_access, coords)


def test_pbf_and_overpass_transports_agree_on_kept_features():
    elements = _overpass_elements_for(WAYS)
    transport = httpx.MockTransport(lambda r: _osm_response(elements))
    client = httpx.Client(transport=transport)

    overpass_features = osm_fetch.fetch(_BBOX, client=client)
    pbf_features = osm_pbf_fetch.fetch(_BBOX, pbf_path=FIXTURE_PATH)

    overpass_keys = sorted(_feature_key(f) for f in overpass_features)
    pbf_keys = sorted(_feature_key(f) for f in pbf_features)
    assert overpass_keys == pbf_keys
    assert len(overpass_keys) == 3  # (a) path, (b) track, (c) footway — 2 dropped


def test_pbf_and_overpass_transports_both_drop_unnamed_and_residential():
    elements = _overpass_elements_for(WAYS)
    transport = httpx.MockTransport(lambda r: _osm_response(elements))
    client = httpx.Client(transport=transport)

    overpass_names = {f.name for f in osm_fetch.fetch(_BBOX, client=client)}
    pbf_names = {f.name for f in osm_pbf_fetch.fetch(_BBOX, pbf_path=FIXTURE_PATH)}

    for dropped in (None, "Random Residential Street"):
        assert dropped not in overpass_names
        assert dropped not in pbf_names


# ── AC-5.4 — no network, no state-PBF download, no neo4j marker ───────────────


def test_parity_fixture_is_committed_and_tiny():
    # The unattended-feasibility guard: a committed synthetic fixture, not a
    # 386 MB Geofabrik state download.
    assert FIXTURE_PATH.exists()
    assert FIXTURE_PATH.stat().st_size < 10_000
