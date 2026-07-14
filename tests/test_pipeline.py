"""Tests for ingestion.pipeline (network-free: sources injected via the registry).

Covers the Epic 012 rewire: the C5-closure (no source literal in run_pipeline),
spine-by-declaration generality (S4), the enrichment join point (S5), and the
echo drop-in proof (S6). The consolidate_osm_segments tests cover the connectivity-
aware merge (Lead 2): same-name ways merge only when spatially connected, and
disconnected same-name ways split into separate trails.
"""

from __future__ import annotations

import inspect
import json
import tempfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
from shapely.geometry import LineString, MultiLineString, Point

from graph.load import PruneOutcome
from ingestion import pipeline
from ingestion.conflate.match import Agreement, Feature, Match
from ingestion.elevation import haversine_m
from ingestion.pipeline import (
    LENGTH_SOURCE_GEOM,
    _load_matches,
    _persist_review_band,
    _route_length_mi,
    consolidate_osm_segments,
    load_region,
    run_pipeline,
)
from ingestion.sources.base import (
    ConflationRole,
    CorpusSource,
    EnrichmentFact,
    Region,
    SourceKind,
)
from ingestion.sources.echo import EchoSource
from ingestion.sources.nps import NpsSource
from ingestion.sources.osm import OsmSource
from ingestion.sources.usfs import UsfsSource
from ingestion.transform import to_miles
from orchestration.config import Settings

_REGION = Region(region_id="test-r", bbox=(38.55, -78.45, 38.70, -78.25))
_SETTINGS = Settings.from_env({})


# ── Test doubles (one place; injected by patching registry.enabled_sources) ───


class _StubSource(CorpusSource):
    kind = SourceKind.geometry
    role = ConflationRole.conflate
    authority_tier = 2

    def __init__(self, name, *, role=None, tier=None, features=None):
        self.name = name
        if role is not None:
            self.role = role
        if tier is not None:
            self.authority_tier = tier
        self._features = list(features or [])
        self.fetch_calls = 0
        super().__init__()

    def fetch(self, region):
        self.fetch_calls += 1
        return list(self._features)

    @classmethod
    def from_config(cls, settings):
        return cls("stub")


class _EnrichStub(CorpusSource):
    name = "enrich_stub"
    kind = SourceKind.enrichment
    role = ConflationRole.enrich
    authority_tier = 1

    def __init__(self):
        self.fetch_calls = 0
        self.enrich_calls = 0
        super().__init__()

    def fetch(self, region):
        self.fetch_calls += 1
        raise NotImplementedError("enrichment sources do not fetch")

    @classmethod
    def from_config(cls, settings):
        return cls()

    def enrich(self, canonical):
        self.enrich_calls += 1
        return [EnrichmentFact(source=self.name, attribute="gain_ft", value=1.0)]


def _feat(name: str, source: str, lon: float = -78.28) -> Feature:
    return Feature(
        name=name,
        geom=LineString([[lon, 38.55], [lon + 0.01, 38.56]]),
        source=source,
        ref=f"{source.lower()}/{name}",
    )


def _inject(monkeypatch, sources):
    monkeypatch.setattr(
        pipeline.registry, "enabled_sources", lambda settings, names=None: list(sources)
    )


# ── load_region returns a Region object ───────────────────────────────────────


def test_load_region_parses_bbox(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "regions").mkdir()
    (tmp_path / "regions" / "my-region.geojson").write_text(
        json.dumps(
            {
                "type": "Feature",
                "properties": {"region_id": "my-region", "bbox": [-79.0, 38.0, -78.0, 39.0]},
                "geometry": {"type": "Polygon", "coordinates": [[]]},
            }
        )
    )
    region = load_region("my-region")
    assert isinstance(region, Region)
    assert region.bbox == (38.0, -79.0, 39.0, -78.0)  # (south, west, north, east)
    assert region.region_id == "my-region"


@pytest.mark.parametrize(
    "region_id",
    [
        "../secrets",
        "..%2Fsecrets",  # literal chars, not URL-decoded — still contains ".."
        "sub/dir",
        "sub\\dir",
        "..",
    ],
)
def test_load_region_rejects_path_traversal(tmp_path, monkeypatch, region_id):
    """AM4: --region flows straight into Path(f"regions/{region_id}.geojson"); a value
    escaping regions/ must exit loudly, never resolve outside the region directory."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "regions").mkdir()
    with pytest.raises(SystemExit):
        load_region(region_id)


# ── Pipeline counts: per-source keys derive from source.name (no literals) ────


def test_pipeline_dry_run_returns_counts(monkeypatch, tmp_path):
    spine = _StubSource("osm", role=ConflationRole.spine, features=[_feat("Old Rag Loop", "OSM")])
    agency = _StubSource("nps", features=[_feat("Old Rag", "NPS")])
    _inject(monkeypatch, [spine, agency])
    settings = replace(_SETTINGS, review_band_dir=str(tmp_path / "review"))

    counts = run_pipeline(_REGION, dry_run=True, settings=settings)

    assert counts["osm"] == 1
    assert counts["osm_consolidated"] == 1
    assert counts["nps"] == 1
    assert "auto_accept" in counts and "loaded" in counts


def test_pipeline_counts_all_sources(monkeypatch):
    spine = _StubSource("osm", role=ConflationRole.spine, features=[_feat("A", "OSM")])
    nps = _StubSource("nps", features=[_feat("B", "NPS")])
    usfs = _StubSource("usfs", features=[_feat("C", "USFS")])
    _inject(monkeypatch, [spine, nps, usfs])

    counts = run_pipeline(_REGION, dry_run=True, settings=_SETTINGS)
    assert counts["osm"] == 1 and counts["nps"] == 1 and counts["usfs"] == 1


# ── AC-2.5 — C5 closure: no source literal in run_pipeline / CLI choices ───────


def test_ac2_5_no_source_string_literals_in_run_pipeline():
    src = inspect.getsource(run_pipeline)
    for lit in ("osm", "nps", "usfs"):
        assert f'"{lit}"' not in src, f'run_pipeline names "{lit}" literally'
        assert f"'{lit}'" not in src, f"run_pipeline names '{lit}' literally"
    # nps/usfs do not even appear as bare tokens; osm only via the kept function
    # name consolidate_osm_segments (an identifier, not a source literal).
    assert "nps" not in src and "usfs" not in src


def test_ac2_5_cli_choices_derive_from_registry():
    src = inspect.getsource(pipeline.main)
    assert "known_source_names()" in src
    for lit in ("osm", "nps", "usfs"):
        assert f'"{lit}"' not in src and f"'{lit}'" not in src


# ── AC-3.5 — run_pipeline no longer imports ingestion.fetch.{osm,nps,usfs} ─────


def test_ac3_5_pipeline_does_not_import_fetch_submodules():
    src = inspect.getsource(pipeline)
    for sub in ("ingestion.fetch.osm", "ingestion.fetch.nps", "ingestion.fetch.usfs"):
        assert sub not in src, f"{sub} import still present in pipeline"
    assert "from ingestion.fetch import" not in src
    # It imports only the registry seam now.
    assert "from ingestion.sources import registry" in src


# ── AC-5.2 / DoD — default config end-to-end through the REAL adapters ─────────


def _e2e_osm_client() -> httpx.Client:
    def handler(_r: httpx.Request) -> httpx.Response:
        body = json.dumps(
            {
                "elements": [
                    {
                        "type": "way",
                        "id": 1,
                        "tags": {"name": "Old Rag Loop", "highway": "path"},
                        "geometry": [{"lon": -78.28, "lat": 38.55}, {"lon": -78.27, "lat": 38.56}],
                    }
                ]
            }
        ).encode()
        return httpx.Response(200, content=body, headers={"content-type": "application/json"})

    return httpx.Client(transport=httpx.MockTransport(handler))


def _e2e_nps_client() -> httpx.Client:
    def handler(r: httpx.Request) -> httpx.Response:
        offset = r.url.params.get("resultOffset", "0")
        # Same geometry as OSM → strong overlap → the pair auto-accepts.
        feats = (
            [
                {
                    "type": "Feature",
                    "properties": {"TRLNAME": "Old Rag"},
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[-78.28, 38.55], [-78.27, 38.56]],
                    },
                }
            ]
            if offset in ("0", 0)
            else []
        )
        body = json.dumps({"type": "FeatureCollection", "features": feats}).encode()
        return httpx.Response(200, content=body, headers={"content-type": "application/json"})

    return httpx.Client(transport=httpx.MockTransport(handler))


def _e2e_usfs_file() -> Path:
    # A far-away, differently-named trail → no conflation with the OSM spine.
    f = tempfile.NamedTemporaryFile(suffix=".geojson", mode="w", delete=False)
    json.dump(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"TRAIL_NAME": "Jones Run Trail", "TRAIL_NO": "1"},
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[-78.40, 38.62], [-78.39, 38.63]],
                    },
                }
            ],
        },
        f,
    )
    f.close()
    return Path(f.name)


def test_ac5_2_default_config_counts_through_real_adapters(monkeypatch, tmp_path):
    """End-to-end behavior-preservation golden: the real OsmSource/NpsSource/
    UsfsSource (only their transports mocked) flow through the reworked
    fetch→consolidate→conflate→count glue under the default config, producing the
    expected counts for this fixture (the OSM×NPS pair routes to REVIEW because their
    names differ by a discriminating "loop" suffix; USFS present but unmatched)."""
    usfs_path = _e2e_usfs_file()
    try:
        real_sources = [
            OsmSource(client=_e2e_osm_client()),
            NpsSource(client=_e2e_nps_client()),
            UsfsSource(geojson_path=usfs_path),
        ]
        _inject(monkeypatch, real_sources)
        settings = replace(_SETTINGS, review_band_dir=str(tmp_path / "review"))

        counts = run_pipeline(_REGION, dry_run=True, settings=settings)

        assert counts["osm"] == 1
        assert counts["osm_consolidated"] == 1
        assert counts["nps"] == 1
        assert counts["usfs"] == 1
        # Matcher redesign: OSM 'Old Rag Loop' × NPS 'Old Rag' share geometry but their
        # names differ by a DISCRIMINATING suffix ("loop"), which the matcher keeps distinct
        # (a loop is a distinct route from its base name). Geometry is strong, so the pair is
        # not dropped — it routes to REVIEW rather than auto-stamping the loop's name. (Under
        # the old suffix-stripping scorer this auto-accepted; the redesign trades that recall
        # for precision by design — see ingestion/conflate/match.py note #1.)
        assert counts["auto_accept"] == 0
        assert counts["review"] == 1
        assert counts["skipped_hygiene"] == 0
    finally:
        usfs_path.unlink(missing_ok=True)


# ── AC-4.1 — spine is a declaration: swapping role re-points conflation ────────


def _spy_match(monkeypatch, captured):
    real = pipeline.match

    def spy(a, b, *, thresholds=None):
        captured.append(a[0].source if a else None)
        return real(a, b, thresholds=thresholds)

    monkeypatch.setattr(pipeline, "match", spy)


def test_ac4_1_spine_declaration_drives_conflation_a_side(monkeypatch):
    a = _StubSource("a", role=ConflationRole.spine, tier=2, features=[_feat("Old Rag", "A")])
    b = _StubSource("b", role=ConflationRole.conflate, tier=1, features=[_feat("Old Rag", "B")])

    captured: list[str] = []
    _spy_match(monkeypatch, captured)
    _inject(monkeypatch, [a, b])
    run_pipeline(_REGION, dry_run=True, settings=_SETTINGS)
    assert captured == ["A"]  # spine A's features are the match() first arg

    # Swap the spine declaration; NO run_pipeline edit — conflation re-points to B.
    a.role = ConflationRole.conflate
    b.role = ConflationRole.spine
    captured.clear()
    _inject(monkeypatch, [a, b])
    run_pipeline(_REGION, dry_run=True, settings=_SETTINGS)
    assert captured == ["B"]


# ── AC-4.3 — load loop reads authority_tier from the source (no OSM literal) ───


def test_ac4_3_load_records_authority_tier_from_source():
    from ingestion.conflate.match import Agreement, Match

    spine_feat = _feat("Old Rag", "NPS")  # non-OSM spine proves de-literaling
    agency_feat = _feat("Old Rag", "USFS")
    m = Match(spine_feat, agency_feat, 95, Agreement(0.9, 10.0), "auto-accept")

    calls: list[tuple] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731
    _load_matches(runner, [m], [spine_feat], tier_by_name={"nps": 1, "usfs": 1}, iv="t")

    # Canonical id is built from the spine source generically, not a hardcoded "osm".
    canonical_params = [p for c, p in calls if "CanonicalTrail" in c]
    assert canonical_params and canonical_params[0]["cid"].startswith("ct:nps:")
    # Each SourceRecord carries the per-source authority_tier floor (via extra).
    sr_params = [p for c, p in calls if "MERGE (r:SourceRecord" in c]
    assert sr_params and all("ex_authority_tier" in p for p in sr_params)


# ── Phase 2 — spatial park-boundary flag persisted through the load loop ───────


def test_load_persists_outside_boundary_from_region_polygon():
    from shapely.geometry import Polygon

    # An L-shaped "park": the SE corner (lon>-78.1, lat<39.0) is the missing notch —
    # outside the boundary though inside its bbox. A fire road inside the park KEEPs
    # (outside_boundary=False); a way in the notch is flagged outside (True).
    boundary = Polygon(
        [(-78.3, 38.8), (-78.1, 38.8), (-78.1, 39.0), (-78.0, 39.0), (-78.0, 39.1), (-78.3, 39.1)]
    )
    inside = Feature(  # centroid ~(-78.245, 38.905) — inside the park
        name="Compton Gap Road",
        geom=LineString([[-78.25, 38.90], [-78.24, 38.91]]),
        source="OSM",
        ref="way/1",
        way_type="track",
    )
    outside = Feature(  # centroid ~(-78.045, 38.855) — in the notch, outside the park
        name="Andreae Wellness Path",
        geom=LineString([[-78.05, 38.85], [-78.04, 38.86]]),
        source="OSM",
        ref="way/2",
        way_type="footway",
    )

    calls: list[tuple] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731
    _load_matches(runner, [], [inside, outside], tier_by_name={"osm": 1}, iv="t", boundary=boundary)

    flags = {
        p["name"]: p.get("outside_boundary") for c, p in calls if "MERGE (t:CanonicalTrail" in c
    }
    assert flags["Compton Gap Road"] is False  # inside the park → kept
    assert flags["Andreae Wellness Path"] is True  # outside → demote candidate


def test_load_no_boundary_degrades_flag_to_none():
    # No region boundary (today's placeholder-bbox regions) → the flag is None, so
    # nothing is demoted: behaviour is never worse than the name-only filter.
    feat = _feat("Some Track", "OSM")
    calls: list[tuple] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731
    _load_matches(runner, [], [feat], tier_by_name={"osm": 1}, iv="t", boundary=None)
    flags = [p.get("outside_boundary") for c, p in calls if "MERGE (t:CanonicalTrail" in c]
    assert flags == [None]


# ── S5 — flag-on-ambiguous merge at load (CDP-14) ──────────────────────────────


def test_s5_warns_on_same_source_same_name_reflless_features(caplog):
    import logging

    a = Feature(
        name="Ridge Trail", geom=LineString([[-78.28, 38.55], [-78.27, 38.56]]), source="OSM"
    )
    b = Feature(
        name="Ridge Trail", geom=LineString([[-78.30, 38.60], [-78.29, 38.61]]), source="OSM"
    )
    calls: list[tuple] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731

    with caplog.at_level(logging.WARNING, logger="ingestion.pipeline"):
        _load_matches(runner, [], [a, b], tier_by_name={"osm": 1}, iv="t")

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("Ridge Trail" in r.message and "osm" in r.message for r in warnings)
    # Non-destructive: both features still loaded, nothing raised.
    canonical_writes = [p for c, p in calls if "MERGE (t:CanonicalTrail" in c]
    assert len(canonical_writes) == 2


def test_s5_no_warning_on_cross_source_same_trail(caplog):
    import logging

    osm_feat = Feature(
        name="Old Rag Loop", geom=LineString([[-78.28, 38.55], [-78.27, 38.56]]), source="OSM"
    )
    nps_feat = Feature(
        name="Old Rag Loop", geom=LineString([[-78.28, 38.55], [-78.27, 38.56]]), source="NPS"
    )
    calls: list[tuple] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731

    with caplog.at_level(logging.WARNING, logger="ingestion.pipeline"):
        _load_matches(runner, [], [osm_feat, nps_feat], tier_by_name={"osm": 1, "nps": 1}, iv="t")

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert not warnings


def test_s5_no_warning_on_auto_accept_cross_source_match(caplog):
    import logging

    from ingestion.conflate.match import Agreement, Match

    spine_feat = Feature(
        name="Old Rag Loop", geom=LineString([[-78.28, 38.55], [-78.27, 38.56]]), source="OSM"
    )
    agency_feat = Feature(
        name="Old Rag", geom=LineString([[-78.28, 38.55], [-78.27, 38.56]]), source="NPS"
    )
    m = Match(spine_feat, agency_feat, 90, Agreement(0.9, 10.0), "auto-accept")
    calls: list[tuple] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731

    with caplog.at_level(logging.WARNING, logger="ingestion.pipeline"):
        _load_matches(runner, [m], [spine_feat], tier_by_name={"osm": 1, "nps": 1}, iv="t")

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert not warnings


def test_s5_no_warning_when_one_spine_feature_matches_two_agencies(caplog):
    """A single OSM spine feature legitimately corroborated by two different
    agencies (NPS and USFS) produces two auto-accept Matches sharing the same
    `m.a` Feature object — that is corroboration, not an ambiguous same-source
    merge, and must stay silent (regression for the id(feature) dedup)."""
    import logging

    from ingestion.conflate.match import Agreement, Match

    spine_feat = Feature(
        name="Old Rag Loop", geom=LineString([[-78.28, 38.55], [-78.27, 38.56]]), source="OSM"
    )
    nps_feat = Feature(
        name="Old Rag", geom=LineString([[-78.28, 38.55], [-78.27, 38.56]]), source="NPS"
    )
    usfs_feat = Feature(
        name="Old Rag Trail", geom=LineString([[-78.28, 38.55], [-78.27, 38.56]]), source="USFS"
    )
    m1 = Match(spine_feat, nps_feat, 90, Agreement(0.9, 10.0), "auto-accept")
    m2 = Match(spine_feat, usfs_feat, 85, Agreement(0.85, 12.0), "auto-accept")
    calls: list[tuple] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731

    with caplog.at_level(logging.WARNING, logger="ingestion.pipeline"):
        _load_matches(
            runner, [m1, m2], [spine_feat], tier_by_name={"osm": 1, "nps": 1, "usfs": 1}, iv="t"
        )

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert not warnings


# ── S1 — per-record validity drop in the load path (Epic 025) ─────────────────


def test_s1_empty_geometry_dropped_without_aborting_region(caplog):
    """An empty LineString (e.g. a degenerate OSM way) must be dropped per-record —
    never crash the region. This is the exact case that would raise GEOSException
    from _safe_geom_centroid if geometry were not validated before the centroid."""
    import logging

    good_a = _feat("Compton Gap Road", "OSM", lon=-78.28)
    bad = Feature(name="Broken Way", geom=LineString(), source="OSM", ref="osm/broken")
    good_b = _feat("Salt Pond Road", "OSM", lon=-78.20)

    calls: list[tuple] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731

    with caplog.at_level(logging.WARNING, logger="ingestion.pipeline"):
        counts = _load_matches(runner, [], [good_a, bad, good_b], tier_by_name={"osm": 1}, iv="t")

    assert counts["skipped_hygiene"] == 1
    canonical_writes = [p for c, p in calls if "MERGE (t:CanonicalTrail" in c]
    assert len(canonical_writes) == 2
    assert any("osm/broken" in r.message and "geometry" in r.message for r in caplog.records)


def test_s1_null_island_centroid_dropped():
    """A feature with an otherwise-valid geometry whose centroid lands exactly on
    (0,0) — the classic null-island sentinel for missing/corrupt coordinate data —
    must be dropped, not persisted. The geometry itself is valid and non-empty
    (a straight line from (-1,-1) to (1,1)), so this exercises the valid_lonlat
    branch specifically, distinct from the geometry_valid branch."""
    good = _feat("Compton Gap Road", "OSM", lon=-78.28)
    null_island = Feature(
        name="Null Island Way",
        geom=LineString([[-1.0, -1.0], [1.0, 1.0]]),
        source="OSM",
        ref="osm/null",
    )

    calls: list[tuple] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731
    counts = _load_matches(runner, [], [good, null_island], tier_by_name={"osm": 1}, iv="t")

    assert counts["skipped_hygiene"] == 1
    canonical_writes = [p for c, p in calls if "MERGE (t:CanonicalTrail" in c]
    assert len(canonical_writes) == 1
    assert canonical_writes[0]["name"] == "Compton Gap Road"


def test_s1_all_valid_batch_skips_nothing():
    a = _feat("Compton Gap Road", "OSM", lon=-78.28)
    b = _feat("Salt Pond Road", "OSM", lon=-78.20)

    calls: list[tuple] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731
    counts = _load_matches(runner, [], [a, b], tier_by_name={"osm": 1}, iv="t")

    assert counts["skipped_hygiene"] == 0
    assert counts["loaded"] == 2
    canonical_writes = [p for c, p in calls if "MERGE (t:CanonicalTrail" in c]
    assert len(canonical_writes) == 2


def test_s1_invalid_features_never_raise():
    """Per-record drop, never a region abort: a batch mixing an empty geometry and
    a null-island centroid among valid features must not raise."""
    good = _feat("Compton Gap Road", "OSM", lon=-78.28)
    empty_geom = Feature(name="Broken Way", geom=LineString(), source="OSM", ref="osm/broken")
    null_island = Feature(
        name="Null Island Way",
        geom=LineString([[-1.0, -1.0], [1.0, 1.0]]),
        source="OSM",
        ref="osm/null",
    )

    calls: list[tuple] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731
    counts = _load_matches(
        runner, [], [good, empty_geom, null_island], tier_by_name={"osm": 1}, iv="t"
    )

    assert counts["skipped_hygiene"] == 2
    canonical_writes = [p for c, p in calls if "MERGE (t:CanonicalTrail" in c]
    assert len(canonical_writes) == 1


def test_s1_canonical_nodes_also_gated_by_hygiene():
    """_canonical_nodes (the enrichment-node derivation, run BEFORE _load_matches
    in run_pipeline — see run_pipeline's `canonical_nodes = _canonical_nodes(...)`
    call ahead of the dry-run branch) must apply the same hygiene floor as the
    load loop. It calls _safe_geom_centroid directly on the same Features; if it
    isn't gated, an empty-geometry feature crashes here — one call site earlier
    than the load loop's own guard — defeating the point of the hygiene fix."""
    from ingestion.pipeline import _canonical_nodes

    good = _feat("Compton Gap Road", "OSM", lon=-78.28)
    empty_geom = Feature(name="Broken Way", geom=LineString(), source="OSM", ref="osm/broken")

    nodes = _canonical_nodes([], [good, empty_geom])  # must not raise GEOSException

    assert [n.name for n in nodes] == ["Compton Gap Road"]


def test_s1_hygiene_drop_on_matched_spine_not_double_counted(caplog):
    """A hygiene-dropped auto-accept spine feature (m.a) must not be re-processed
    in the unmatched-spine loop as if it were never seen — it's a matched feature,
    just an invalid one. Regression: matched_spine_ids must be updated before the
    hygiene continue, or the feature is double-dropped and double-counted."""
    import logging

    from ingestion.conflate.match import Agreement, Match

    bad_spine = Feature(name="Broken Way", geom=LineString(), source="OSM", ref="osm/broken")
    agency_feat = Feature(
        name="Broken Way", geom=LineString([[-78.28, 38.55], [-78.27, 38.56]]), source="NPS"
    )
    m = Match(bad_spine, agency_feat, 95, Agreement(0.9, 10.0), "auto-accept")

    calls: list[tuple] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731

    with caplog.at_level(logging.WARNING, logger="ingestion.pipeline"):
        counts = _load_matches(runner, [m], [bad_spine], tier_by_name={"osm": 1, "nps": 1}, iv="t")

    assert counts["skipped_hygiene"] == 1  # not 2 — dropped once, not reprocessed
    drop_warnings = [r for r in caplog.records if "osm/broken" in r.message]
    assert len(drop_warnings) == 1
    canonical_writes = [p for c, p in calls if "MERGE (t:CanonicalTrail" in c]
    assert len(canonical_writes) == 0


# ── AC-5.2 / AC-5.3 — enrichment join point: post-conflation, never the matcher ─


def test_ac5_2_default_no_enrichment_is_noop(monkeypatch):
    spine = _StubSource("osm", role=ConflationRole.spine, features=[_feat("X", "OSM")])
    _inject(monkeypatch, [spine])
    # No enrichment source enabled → run completes; counts unaffected by enrichment.
    counts = run_pipeline(_REGION, dry_run=True, settings=_SETTINGS)
    assert counts["osm"] == 1


def test_ac5_3_enrichment_invoked_post_conflation_not_in_matcher(monkeypatch):
    spine = _StubSource("osm", role=ConflationRole.spine, features=[_feat("X", "OSM")])
    enrich = _EnrichStub()
    captured: list[str] = []
    _spy_match(monkeypatch, captured)
    _inject(monkeypatch, [spine, enrich])

    run_pipeline(_REGION, dry_run=True, settings=_SETTINGS)

    assert enrich.enrich_calls > 0, "enrichment source's enrich was never called"
    assert enrich.fetch_calls == 0, "enrichment source must never be fetched"
    assert "enrich_stub" not in captured  # never a conflation argument


# ── Elevation survives a re-ingest (root-cause fix) ────────────────────────────
#
# usgs-3dep is now a default corpus source (Settings.corpus_sources), so every
# re-ingest re-runs it through the real config-driven registry — the exact path
# that silently dropped elevation before (Shenandoah, twice) because usgs-3dep
# wasn't in the default list. These exercise the real `UsgsThreeDEPSource` (not a
# stub) through `enabled_sources`, proving both halves of the guarantee: it
# re-enriches when a DEM is configured, and it degrades to a harmless no-op
# (never an error, never a wipe) when the region has none.


def test_reingest_with_dem_reenriches(monkeypatch, tmp_path):
    from ingestion.sources.usgs_3dep import UsgsThreeDEPSource

    class _Ramp:
        """A monotonic climb keyed on longitude — mirrors test_usgs_3dep.py."""

        def sample(self, lon, lat):
            return (lon + 78.30) * 10_000.0

    spine = _StubSource(
        "osm",
        role=ConflationRole.spine,
        features=[
            Feature(
                name="Old Rag Loop",
                geom=LineString([[-78.30, 38.50], [-78.20, 38.50]]),
                source="OSM",
                ref="osm/old-rag-loop",
            )
        ],
    )
    dem = UsgsThreeDEPSource(sampler=_Ramp(), resolution_m=200.0)
    _inject(monkeypatch, [spine, dem])

    counts = run_pipeline(_REGION, dry_run=True, settings=_SETTINGS)

    # 8 facts (profile_distances_m, profile_elevations_m, total_gain_m, total_loss_m,
    # max_grade_pct, elev_source, elev_resolution_m, elev_version) for the one trail.
    assert counts["enrichment_facts"] == 8


def test_reingest_without_dem_does_not_error_or_wipe(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # hermetic: dev-box data/dem rasters must not leak in
    # No ADVENTURE_3DEP_DEM configured for this region — the real registry resolves
    # usgs-3dep via `from_config`, which must degrade to a no-op sampler rather than
    # raising (finding: a re-ingest of a DEM-less region must complete cleanly).
    settings = Settings.from_env({})
    assert settings.dem_path is None
    spine = _StubSource("osm", role=ConflationRole.spine, features=[_feat("X", "OSM")])
    real_sources = pipeline.registry.enabled_sources(settings, names=["osm", "usgs-3dep"])
    _inject(monkeypatch, [spine] + [s for s in real_sources if s.name == "usgs-3dep"])

    counts = run_pipeline(_REGION, dry_run=True, settings=settings)

    assert counts["osm"] == 1
    assert counts["enrichment_facts"] == 0  # degraded to no-op, not an error


def test_default_corpus_sources_include_usgs_3dep():
    assert "usgs-3dep" in Settings.from_env({}).corpus_sources


# ── AC-6.3 — echo drop-in: zero source-naming code in run_pipeline ────────────


def test_ac6_3_run_pipeline_has_no_echo_literal():
    assert "echo" not in inspect.getsource(run_pipeline)
    assert "echo" not in inspect.getsource(pipeline.main)


def test_ac6_3_echo_flows_through_unchanged_pipeline(monkeypatch):
    spine = _StubSource(
        "osm", role=ConflationRole.spine, features=[_feat("Echo Ridge Trail", "OSM")]
    )
    _inject(monkeypatch, [spine, EchoSource()])  # echo appended, real adapter

    counts = run_pipeline(_REGION, dry_run=True, settings=_SETTINGS)
    # The same body that handles osm/nps/usfs fetched + conflated echo's features.
    assert counts["echo"] == 2  # EchoSource returns two fixed features


# ── elevation-coverage visibility (Epic 017 durability) ──────────────────────


class _NamedSource:
    """Minimal stand-in for `_log_elevation_coverage`'s `.name` duck-type."""

    def __init__(self, name: str) -> None:
        self.name = name


def test_log_elevation_coverage_warns_when_3dep_active_but_zero(caplog):
    import logging

    from ingestion.pipeline import _log_elevation_coverage

    with caplog.at_level(logging.WARNING, logger="ingestion.pipeline"):
        _log_elevation_coverage([_NamedSource("usgs-3dep")], [], n_nodes=100)
    assert any("0/100" in r.message for r in caplog.records)


def test_log_elevation_coverage_reports_partial(caplog):
    import logging

    from ingestion.pipeline import _log_elevation_coverage

    facts = [
        EnrichmentFact(
            source="usgs-3dep", attribute="total_gain_m", value=1.0, canonical_id="ct:a"
        ),
        EnrichmentFact(
            source="usgs-3dep", attribute="total_gain_m", value=2.0, canonical_id="ct:b"
        ),
    ]
    with caplog.at_level(logging.INFO, logger="ingestion.pipeline"):
        _log_elevation_coverage([_NamedSource("usgs-3dep")], facts, n_nodes=4)
    assert any("2/4" in r.message for r in caplog.records)


def test_log_elevation_coverage_noop_without_3dep(caplog):
    import logging

    from ingestion.pipeline import _log_elevation_coverage

    with caplog.at_level(logging.INFO, logger="ingestion.pipeline"):
        _log_elevation_coverage([_NamedSource("nps")], [], n_nodes=100)
    assert not any("3DEP profile" in r.message for r in caplog.records)


def test_elevation_coverage_counts_dedupe_by_canonical_id():
    # Regression for the verify-gate false-trip: an ambiguous same-source merge stamps two
    # features onto one canonical_id, so `canonical_nodes` holds duplicate ids. The eligible
    # denominator must count DISTINCT ids (like the covered numerator), else a fully-covered
    # corpus reads <100% and the gate falsely skips the prune (PWF: 93 nodes → 64 distinct,
    # all covered, was read as 64/93 = 69%).
    from ingestion.pipeline import _elevation_coverage_counts
    from ingestion.sources.base import CanonicalNode, EnrichmentFact

    nodes = [
        CanonicalNode(canonical_id="ct:a", name="A", geom_wkt="LINESTRING(0 0,1 1)"),
        CanonicalNode(canonical_id="ct:a", name="A (dup feature)", geom_wkt="LINESTRING(0 0,1 1)"),
        CanonicalNode(canonical_id="ct:b", name="B", geom_wkt="LINESTRING(2 2,3 3)"),
        CanonicalNode(canonical_id="ct:c", name="C point-only"),  # no geom → not eligible
    ]
    facts = [
        EnrichmentFact(
            source="usgs-3dep", attribute="total_gain_m", value=1.0, canonical_id="ct:a"
        ),
        EnrichmentFact(
            source="usgs-3dep", attribute="total_gain_m", value=2.0, canonical_id="ct:b"
        ),
    ]
    eligible, covered = _elevation_coverage_counts(nodes, facts)
    assert eligible == 2  # ct:a deduped + ct:b; point-only ct:c excluded
    assert covered == 2  # 100% coverage, NOT 2/3 from the duplicate node


# ── consolidate_osm_segments (connectivity-aware — Lead 2) ────────────────────


def _chain(name: str, n: int, *, source: str = "OSM", start: tuple[float, float] = (-78.28, 38.55)):
    """`n` end-to-end-connected same-name segments (each starts where the prior ends)
    → one spatially-connected trail. refs are way/100, way/101, …"""
    segs = []
    lon, lat = start
    for i in range(n):
        segs.append(
            Feature(
                name=name,
                geom=LineString([[lon, lat], [lon + 0.01, lat + 0.01]]),
                source=source,
                ref=f"way/{100 + i}",
            )
        )
        lon, lat = lon + 0.01, lat + 0.01
    return segs


def _seg(name: str, lon_start: float, ref: str | None = None) -> Feature:
    return Feature(
        name=name,
        geom=LineString([[lon_start, 38.55], [lon_start + 0.01, 38.56]]),
        source="OSM",
        ref=ref or f"way/{abs(int(lon_start * 1000))}",
    )


def test_consolidate_merges_connected_same_name_segments():
    result = consolidate_osm_segments(_chain("Old Rag Loop", 3))
    assert len(result) == 1
    assert result[0].name == "Old Rag Loop"
    assert result[0].source == "OSM"
    # Merged → stable, unique ref = min member way id (NOT None — avoids slug collision).
    assert result[0].ref == "way/100"


def test_consolidate_splits_disconnected_same_name_ways():
    # Same name, far apart (~7 km) → two separate trails, each keeps its own ref.
    segs = [_seg("Ridge Trail", -78.28, ref="way/1"), _seg("Ridge Trail", -78.35, ref="way/2")]
    result = consolidate_osm_segments(segs)
    assert len(result) == 2
    assert {f.ref for f in result} == {"way/1", "way/2"}
    assert all(f.name == "Ridge Trail" for f in result)


def test_consolidate_keeps_distinct_names():
    segs = [_seg("Old Rag Loop", -78.28), _seg("Stony Man Trail", -78.30)]
    result = consolidate_osm_segments(segs)
    assert len(result) == 2
    assert {f.name for f in result} == {"Old Rag Loop", "Stony Man Trail"}


def test_consolidate_normalizes_before_grouping():
    # Two connected segments whose names normalize equal ("Old Rag Trail" ~ "Old Rag").
    segs = _chain("Old Rag Trail", 1) + _chain("Old Rag", 1, start=(-78.27, 38.56))
    result = consolidate_osm_segments(segs)
    assert len(result) == 1
    assert result[0].name == "Old Rag Trail"  # longest raw name wins


def test_consolidate_combined_geometry_contains_all_coords():
    result = consolidate_osm_segments(_chain("Ridge Trail", 3))
    assert len(result) == 1
    bounds = result[0].geom.bounds
    assert bounds[0] <= -78.28 and bounds[2] >= -78.25  # spans the whole chain


def test_consolidate_single_segment_preserved():
    seg = _seg("Lone Trail", -78.28)
    result = consolidate_osm_segments([seg])
    assert len(result) == 1
    assert result[0].ref == seg.ref  # ref kept when no merge happened


def test_consolidate_merge_preserves_real_source():
    """A multi-segment merge keeps the group's real `source` (not a hardcoded "OSM"),
    so a non-OSM spine keeps its authority tier + provenance."""
    segs = _chain("Skyline Trail", 2, source="NPS")
    result = consolidate_osm_segments(segs)
    assert len(result) == 1
    assert result[0].source == "NPS"  # real provenance preserved on merge
    assert result[0].ref == "way/100"  # stable min-member ref


# ── way_type persistence (feed-quality de-rank input) ─────────────────────────


def _typed_seg(name: str, lon_start: float, way_type: str, ref: str) -> Feature:
    return Feature(
        name=name,
        geom=LineString([[lon_start, 38.55], [lon_start + 0.01, 38.56]]),
        source="OSM",
        ref=ref,
        way_type=way_type,
    )


def test_consolidate_single_preserves_way_type():
    seg = _typed_seg("Fire Road", -78.28, "track", "way/1")
    result = consolidate_osm_segments([seg])
    assert result[0].way_type == "track"


def test_consolidate_merge_takes_dominant_way_type():
    # Three end-to-end-connected "Old Rag" ways (a `_chain`-style contiguous trail); the
    # dominant (majority) way_type wins on merge.
    segs = _chain("Old Rag", 3)
    types = ["path", "path", "track"]
    segs = [
        Feature(name=s.name, geom=s.geom, source=s.source, ref=s.ref, way_type=t)
        for s, t in zip(segs, types)
    ]
    result = consolidate_osm_segments(segs)
    assert len(result) == 1
    assert result[0].way_type == "path"  # 2×path beats 1×track


def test_way_type_flows_to_canonical_trail_load():
    from ingestion.conflate.match import Agreement, Match

    spine = _feat("Compton Gap Road", "OSM")
    spine = Feature(name=spine.name, geom=spine.geom, source="OSM", ref=spine.ref, way_type="track")
    agency = _feat("Compton Gap Road", "USFS")
    m = Match(spine, agency, 96, Agreement(0.9, 10.0), "auto-accept")

    calls: list[tuple] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731
    _load_matches(runner, [m], [spine], tier_by_name={"osm": 2, "usfs": 1}, iv="t")

    canonical = [p for c, p in calls if "CanonicalTrail" in c and "SET" in c]
    assert canonical and canonical[0].get("way_type") == "track"


def test_unmatched_spine_way_type_flows_to_load():
    # An unmatched spine feature also carries its way_type onto the node.
    spine = Feature(
        name="Service Access",
        geom=LineString([[-78.28, 38.55], [-78.27, 38.56]]),
        source="OSM",
        ref="way/9",
        way_type="track",
    )
    calls: list[tuple] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731
    _load_matches(runner, [], [spine], tier_by_name={"osm": 2}, iv="t")
    canonical = [p for c, p in calls if "CanonicalTrail" in c and "SET" in c]
    assert canonical and canonical[0].get("way_type") == "track"


# ── Distance activation: haversine length_mi (task: activate distance) ──────────


def test_route_length_mi_matches_known_synthetic_geometry():
    # A pure north-south line: haversine reduces to an exact R*dlat great-circle
    # distance, so this is a real analytic oracle, not a hand-typed magic number.
    coords = [(-78.0, 38.00), (-78.0, 38.01), (-78.0, 38.02)]
    line = LineString(coords)
    expected_m = sum(haversine_m(a, b) for a, b in zip(coords, coords[1:]))

    got = _route_length_mi(line)

    assert got == pytest.approx(to_miles(expected_m))
    assert got == pytest.approx(1.382, rel=1e-2)  # ~1.38 mi sanity anchor


def test_route_length_mi_none_geometry_is_none():
    assert _route_length_mi(None) is None


def test_route_length_mi_sums_within_part_not_across_the_gap():
    # Two disconnected parts (a MultiLineString): length is the sum of each part's
    # own ground distance — the gap BETWEEN parts is not real trail and must not
    # be counted (same discipline as the elevation profile's part bridging).
    part_a = LineString([(-78.00, 38.00), (-78.00, 38.01)])
    part_b = LineString([(-77.00, 39.00), (-77.00, 39.01)])  # far away, disconnected
    multi = MultiLineString([part_a, part_b])
    expected_m = haversine_m((-78.00, 38.00), (-78.00, 38.01)) + haversine_m(
        (-77.00, 39.00), (-77.00, 39.01)
    )

    assert _route_length_mi(multi) == pytest.approx(to_miles(expected_m))


def test_matched_length_falls_back_to_haversine_when_no_side_states_one():
    from ingestion.conflate.match import Agreement, Match

    coords = [(-78.00, 38.00), (-78.00, 38.01)]
    spine = Feature(name="Compton Gap Road", geom=LineString(coords), source="OSM", ref="osm/1")
    agency = _feat("Compton Gap Road", "USFS")
    m = Match(spine, agency, 96, Agreement(0.9, 10.0), "auto-accept")

    calls: list[tuple] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731
    _load_matches(runner, [m], [spine], tier_by_name={"osm": 2, "usfs": 1}, iv="t")

    canonical = [p for c, p in calls if "CanonicalTrail" in c and "SET" in c]
    expected_mi = to_miles(haversine_m(*coords))
    assert canonical and canonical[0]["length_mi"] == pytest.approx(expected_mi)
    assert canonical[0]["length_source"] == LENGTH_SOURCE_GEOM


def test_unmatched_spine_length_mi_flows_to_load():
    coords = [(-78.28, 38.55), (-78.27, 38.56)]
    spine = Feature(name="Service Access", geom=LineString(coords), source="OSM", ref="way/9")
    calls: list[tuple] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731
    _load_matches(runner, [], [spine], tier_by_name={"osm": 2}, iv="t")
    canonical = [p for c, p in calls if "CanonicalTrail" in c and "SET" in c]
    expected_mi = to_miles(haversine_m(*coords))
    assert canonical and canonical[0]["length_mi"] == pytest.approx(expected_mi)
    assert canonical[0]["length_source"] == LENGTH_SOURCE_GEOM


def test_point_only_spine_feature_gets_no_length_and_does_not_crash():
    # A point-only trail (no line geometry) must degrade to null length_mi — never
    # crash, never fabricate a distance (source-or-silence). It's passed through as an
    # explicit None (not omitted), so a re-ingest that loses geometry actively clears
    # any length_mi a prior ingest_version had computed, rather than leaving it stale.
    spine = Feature(name="Trailhead Only", geom=Point(-78.28, 38.55), source="OSM", ref="way/10")
    calls: list[tuple] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731
    _load_matches(runner, [], [spine], tier_by_name={"osm": 2}, iv="t")
    canonical = [p for c, p in calls if "CanonicalTrail" in c and "SET" in c]
    assert canonical
    assert canonical[0]["length_mi"] is None
    assert canonical[0]["length_source"] == ""


# ── classified-tag merge on consolidation (Epic 026 AC-3.4/3.5) ───────────────


def test_consolidate_merge_takes_most_severe_path_grade():
    segs = _chain("Old Rag", 2)
    segs = [
        Feature(name=s.name, geom=s.geom, source=s.source, ref=s.ref, path_grade=g)
        for s, g in zip(segs, ["", "difficult"])
    ]
    result = consolidate_osm_segments(segs)
    assert len(result) == 1
    assert result[0].path_grade == "difficult"


def test_consolidate_merge_takes_most_restrictive_foot_access():
    segs = _chain("Old Rag", 3)
    segs = [
        Feature(name=s.name, geom=s.geom, source=s.source, ref=s.ref, foot_access=a)
        for s, a in zip(segs, ["yes", "private", "permit"])
    ]
    result = consolidate_osm_segments(segs)
    assert len(result) == 1
    assert result[0].foot_access == "private"


def test_consolidate_merge_takes_worst_quality_psurface():
    segs = _chain("Old Rag", 2)
    segs = [
        Feature(name=s.name, geom=s.geom, source=s.source, ref=s.ref, psurface=p)
        for s, p in zip(segs, ["paved_good", "unpaved_bad"])
    ]
    result = consolidate_osm_segments(segs)
    assert len(result) == 1
    assert result[0].psurface == "unpaved_bad"


def test_end_to_end_classified_tags_flow_to_canonical_trail_load():
    # Two connected same-named ways — one plain hiking scale (path_grade=""), one
    # demanding_mountain_hiking (path_grade="difficult") — consolidate into one
    # Feature carrying the worse grade, then load_canonical_trail persists it.
    segs = _chain("Difficult Ridge", 2)
    segs = [
        Feature(name=s.name, geom=s.geom, source=s.source, ref=s.ref, path_grade=g)
        for s, g in zip(segs, ["", "difficult"])
    ]
    consolidated = consolidate_osm_segments(segs)
    assert len(consolidated) == 1
    spine = consolidated[0]
    assert spine.path_grade == "difficult"

    calls: list[tuple] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731
    _load_matches(runner, [], [spine], tier_by_name={"osm": 2}, iv="t")

    canonical = [p for c, p in calls if "CanonicalTrail" in c and "SET" in c]
    assert canonical and canonical[0].get("path_grade") == "difficult"


# ── length/gain flow-through (Epic 023 S4) — agency-first cross-side copy ─────


def test_matched_length_gain_copied_from_agency_side_m_b():
    from ingestion.conflate.match import Agreement, Match

    spine = _feat("Old Rag Trail", "OSM")  # m.a — today's spine, carries no length
    agency = Feature(
        name="Old Rag",
        geom=spine.geom,
        source="USFS",
        ref="usfs/1",
        length_mi=4.2,
        length_source="USFS",
        gain_ft=1200.0,
        gain_source="USFS",
    )
    m = Match(spine, agency, 95, Agreement(0.9, 10.0), "auto-accept")

    calls: list[tuple] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731
    _load_matches(runner, [m], [spine], tier_by_name={"osm": 2, "usfs": 1}, iv="t")

    canonical = [p for c, p in calls if "CanonicalTrail" in c and "SET" in c]
    assert canonical[0]["length_mi"] == pytest.approx(4.2)
    assert canonical[0]["length_source"] == "USFS"
    assert canonical[0]["gain_ft"] == pytest.approx(1200.0)
    assert canonical[0]["gain_source"] == "USFS"


def test_matched_length_prefers_m_a_when_agency_is_the_spine():
    # Latent case (AC-4.2): an agency source IS the region spine (m.a), so its
    # length must not be silently dropped by a bare m.b read.
    from ingestion.conflate.match import Agreement, Match

    agency_spine = Feature(
        name="Old Rag Trail",
        geom=LineString([[-78.28, 38.55], [-78.27, 38.56]]),
        source="USFS",
        ref="usfs/1",
        length_mi=3.0,
        length_source="USFS",
    )
    osm_side = _feat("Old Rag", "OSM")  # m.b — no length
    m = Match(agency_spine, osm_side, 95, Agreement(0.9, 10.0), "auto-accept")

    calls: list[tuple] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731
    _load_matches(runner, [m], [agency_spine], tier_by_name={"osm": 2, "usfs": 1}, iv="t")

    canonical = [p for c, p in calls if "CanonicalTrail" in c and "SET" in c]
    assert canonical[0]["length_mi"] == pytest.approx(3.0)
    assert canonical[0]["length_source"] == "USFS"


def test_unmatched_spine_length_gain_flows_through():
    feat = Feature(
        name="Solo Trail",
        geom=LineString([[-78.28, 38.55], [-78.27, 38.56]]),
        source="USFS",
        ref="usfs/2",
        length_mi=5.5,
        length_source="USFS",
        gain_ft=800.0,
        gain_source="USFS",
    )
    calls: list[tuple] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731
    _load_matches(runner, [], [feat], tier_by_name={"usfs": 1}, iv="t")
    canonical = [p for c, p in calls if "CanonicalTrail" in c and "SET" in c]
    assert canonical[0]["length_mi"] == pytest.approx(5.5)
    assert canonical[0]["length_source"] == "USFS"
    assert canonical[0]["gain_ft"] == pytest.approx(800.0)
    assert canonical[0]["gain_source"] == "USFS"


def test_absent_stated_length_falls_back_to_geometry_never_a_fabricated_zero():
    # Supersedes 023's AC-4.3/4.4 "write nothing" once the distance activation
    # landed: with no stated (agency) length but real line geometry, the honest
    # geometry-derived haversine fills in — labelled LENGTH_SOURCE_GEOM, never a
    # fabricated 0.0 and never posing as an agency figure. Gains have no derived
    # fallback, so absent gains still write nothing (the loader's None-guard).
    feat = _feat("No Length Trail", "OSM")
    calls: list[tuple] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731
    _load_matches(runner, [], [feat], tier_by_name={"osm": 2}, iv="t")
    canonical = [p for c, p in calls if "CanonicalTrail" in c and "SET" in c]
    assert canonical[0]["length_mi"] is not None and canonical[0]["length_mi"] > 0
    assert canonical[0]["length_source"] == LENGTH_SOURCE_GEOM
    assert "gain_ft" not in canonical[0]
    assert "gain_source" not in canonical[0]


# ── multipart collapse (Epic 023 S3) — one canonical node, full geometry ──────


def test_multipart_feature_yields_one_canonical_node_with_full_geometry():
    from shapely.geometry import MultiLineString

    from ingestion.route import line_parts, parse_wkt

    # Two disconnected parts sharing one source identity (mirrors a collapsed NPS
    # MultiLineString Feature) — must load as ONE canonical node with BOTH parts,
    # not the last-fragment-wins overwrite this epic fixes.
    parts = MultiLineString(
        [
            [(-78.30, 38.60), (-78.29, 38.61)],
            [(-78.10, 38.80), (-78.09, 38.81)],
        ]
    )
    feat = Feature(name="Fragmented Trail", geom=parts, source="NPS", ref="42")

    calls: list[tuple] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731
    _load_matches(runner, [], [feat], tier_by_name={"nps": 1}, iv="t")

    canonical_calls = [(c, p) for c, p in calls if "MERGE (t:CanonicalTrail" in c]
    assert len(canonical_calls) == 1  # one canonical node, not N

    route_wkt = canonical_calls[0][1].get("route_geom_wkt")
    assert route_wkt is not None
    parsed_lines = line_parts(parse_wkt(route_wkt))
    total_coords = sum(len(list(line.coords)) for line in parsed_lines)
    assert total_coords == 4  # both 2-point parts survived, not just one


# ── Per-source fetch sanity (task 3): a truncated/partial fetch aborts pre-load ──


def _region_with_floors(**floors: int) -> Region:
    return Region(
        region_id="test-r", bbox=(38.55, -78.45, 38.70, -78.25), props={"min_fetch_counts": floors}
    )


def test_fetch_sanity_aborts_on_truncated_spine_via_region_floor(monkeypatch):
    # The region declares OSM must fetch ≥5; the (truncated) run fetched 1 → abort BEFORE
    # any load/prune, so a partial fetch can't later read as healthy and self-wipe.
    region = _region_with_floors(osm=5)
    spine = _StubSource("osm", role=ConflationRole.spine, features=[_feat("A", "OSM")])
    _inject(monkeypatch, [spine])
    with pytest.raises(pipeline.FetchSanityError):
        run_pipeline(region, dry_run=True, settings=_SETTINGS)


def test_fetch_sanity_aborts_on_truncated_conflate_source(monkeypatch):
    # Truncation in a NON-spine source is caught too (it wouldn't shrink the canonical
    # count, so the collapse gate alone would miss it).
    region = _region_with_floors(nps=3)
    spine = _StubSource("osm", role=ConflationRole.spine, features=[_feat("A", "OSM")])
    nps = _StubSource("nps", features=[_feat("B", "NPS")])  # 1 < 3
    _inject(monkeypatch, [spine, nps])
    with pytest.raises(pipeline.FetchSanityError):
        run_pipeline(region, dry_run=True, settings=_SETTINGS)


def test_fetch_sanity_env_floor_overrides_region(monkeypatch):
    monkeypatch.setenv("ADVENTURE_FETCH_MIN_OSM", "3")
    spine = _StubSource("osm", role=ConflationRole.spine, features=[_feat("A", "OSM")])
    _inject(monkeypatch, [spine])
    with pytest.raises(pipeline.FetchSanityError):
        run_pipeline(_REGION, dry_run=True, settings=_SETTINGS)


def test_fetch_sanity_noop_when_unconfigured(monkeypatch):
    # No floor configured → no check; a small fetch is allowed to proceed.
    spine = _StubSource("osm", role=ConflationRole.spine, features=[_feat("A", "OSM")])
    _inject(monkeypatch, [spine])
    counts = run_pipeline(_REGION, dry_run=True, settings=_SETTINGS)
    assert counts["osm"] == 1


def test_fetch_sanity_passes_when_at_or_above_floor(monkeypatch):
    region = _region_with_floors(osm=2)
    spine = _StubSource(
        "osm",
        role=ConflationRole.spine,
        features=[_feat("A", "OSM"), _feat("B", "OSM", lon=-78.30)],
    )
    _inject(monkeypatch, [spine])
    counts = run_pipeline(region, dry_run=True, settings=_SETTINGS)
    assert counts["osm"] == 2


# ── verify_before_prune (task 2): the gate that must pass before the prune ────────


def _verify_runner(n_cur: int, n_prev: int):
    """A fake Runner answering `count_region_versions`' two count queries."""

    def runner(cypher: str, params: dict):
        if "RETURN count(cur)" in cypher:
            return [{"n": n_cur}]
        if "RETURN count(node)" in cypher:
            return [{"n": n_prev}]
        return None

    return runner


def test_verify_before_prune_aborts_on_collapse():
    # Current-version count collapsed to 100 of a prior corpus total 1500 (< 50%) → abort.
    runner = _verify_runner(n_cur=100, n_prev=1400)
    with pytest.raises(pipeline.IngestVerificationError, match="collapsed"):
        pipeline.verify_before_prune(
            _REGION, {}, runner, iv="test-r", elevation_expected=False, pre_load_count=1500
        )


def test_verify_before_prune_aborts_on_half_partial_reingest():
    # The collapse-gate correction: a 50% partial makes n_cur == n_prev (complementary
    # halves of one total). Comparing against the post-load n_prev (700) would PASS
    # (700 !< 350) and let the prune wipe the stragglers; comparing against the pre-load
    # total (1500) aborts (700 < 750). This is the exact silent-half-wipe the fix closes.
    runner = _verify_runner(n_cur=700, n_prev=700)
    with pytest.raises(pipeline.IngestVerificationError, match="collapsed"):
        pipeline.verify_before_prune(
            _REGION, {}, runner, iv="test-r", elevation_expected=False, pre_load_count=1500
        )


def test_verify_before_prune_passes_on_healthy_reingest():
    # Full re-ingest: 1490 of a prior 1500 refresh (10 missed) — well above 50%.
    runner = _verify_runner(n_cur=1490, n_prev=10)
    n_cur, n_prev = pipeline.verify_before_prune(
        _REGION, {}, runner, iv="test-r", elevation_expected=False, pre_load_count=1500
    )
    assert (n_cur, n_prev) == (1490, 10)


def test_verify_before_prune_passes_first_ever_ingest():
    # pre_load_count == 0 → no denominator → collapse check can't fire.
    runner = _verify_runner(n_cur=3, n_prev=0)
    pipeline.verify_before_prune(
        _REGION, {}, runner, iv="test-r", elevation_expected=False, pre_load_count=0
    )


def test_verify_before_prune_ratio_env_configurable(monkeypatch):
    # 200/1500 = 0.133: aborts at the default 0.5 ratio, passes at a relaxed 0.1 ratio.
    runner = _verify_runner(n_cur=200, n_prev=1300)
    with pytest.raises(pipeline.IngestVerificationError):
        pipeline.verify_before_prune(
            _REGION, {}, runner, iv="test-r", elevation_expected=False, pre_load_count=1500
        )
    monkeypatch.setenv("ADVENTURE_PRUNE_MIN_RATIO", "0.1")
    pipeline.verify_before_prune(
        _REGION, {}, runner, iv="test-r", elevation_expected=False, pre_load_count=1500
    )


def test_verify_before_prune_aborts_on_zero_elevation_when_expected():
    # Elevation expected (3DEP active + DEM resolved) but 0/100 covered → abort (this is
    # the "silent 0% warning" promoted to a loud failure).
    runner = _verify_runner(n_cur=100, n_prev=100)
    counts = {"elev_nodes": 100, "elev_covered": 0}
    with pytest.raises(pipeline.IngestVerificationError, match="elevation coverage"):
        pipeline.verify_before_prune(
            _REGION, counts, runner, iv="test-r", elevation_expected=True, pre_load_count=100
        )


def test_verify_before_prune_passes_with_adequate_elevation():
    runner = _verify_runner(n_cur=100, n_prev=100)
    counts = {"elev_nodes": 100, "elev_covered": 90}
    pipeline.verify_before_prune(
        _REGION, counts, runner, iv="test-r", elevation_expected=True, pre_load_count=100
    )


def test_verify_before_prune_ignores_elevation_when_not_expected():
    # Same 0% coverage, but elevation NOT expected (DEM-less region degrades by design)
    # → must NOT abort.
    runner = _verify_runner(n_cur=100, n_prev=100)
    counts = {"elev_nodes": 100, "elev_covered": 0}
    pipeline.verify_before_prune(
        _REGION, counts, runner, iv="test-r", elevation_expected=False, pre_load_count=100
    )


def test_verify_before_prune_elev_coverage_env_configurable(monkeypatch):
    runner = _verify_runner(n_cur=100, n_prev=100)
    counts = {"elev_nodes": 100, "elev_covered": 70}  # 70% < default 80%
    with pytest.raises(pipeline.IngestVerificationError):
        pipeline.verify_before_prune(
            _REGION, counts, runner, iv="test-r", elevation_expected=True, pre_load_count=100
        )
    monkeypatch.setenv("ADVENTURE_ELEV_MIN_COVERAGE", "0.6")  # relax to 60% → passes
    pipeline.verify_before_prune(
        _REGION, counts, runner, iv="test-r", elevation_expected=True, pre_load_count=100
    )


# ── Filter-drift fix: the gate + load loop go run-marker-aware ─────────────────────
#
# With a constant per-region `ingest_version` (production reality — no region geojson
# sets the optional suffix), the version-keyed `n_cur` counted the WHOLE region no
# matter what the run actually touched, so the collapse gate could never trip and the
# prune never saw a stale candidate (`verify_n_prev: 0` every run). Run-marker mode
# counts what THIS RUN stamped, so a truncated fetch finally reads as a collapse.


def test_verify_before_prune_run_marker_truncated_ingest_trips():
    # A truncated fetch stamps 100 of a prior 1500 — under the constant-iv scheme
    # n_cur would still read 1500 (whole region) and the gate would pass straight
    # into a 1400-node wipe. Run-marker n_cur reads 100 → loud abort.
    seen: list[tuple[str, dict]] = []

    def runner(cypher: str, params: dict):
        seen.append((cypher, params))
        if "RETURN count(cur)" in cypher:
            return [{"n": 100}]
        if "RETURN count(node)" in cypher:
            return [{"n": 1400}]
        return None

    with pytest.raises(pipeline.IngestVerificationError, match="collapsed"):
        pipeline.verify_before_prune(
            _REGION,
            {},
            runner,
            iv="test-r",
            elevation_expected=False,
            pre_load_count=1500,
            run_id="test-r@20260713T000000Z-abc",
        )

    # The gate really keyed its current-count on the per-run marker, not the version.
    cur_cypher, cur_params = seen[0]
    assert "cur.ingest_run_id = $run_id" in cur_cypher
    assert cur_params["run_id"] == "test-r@20260713T000000Z-abc"


def test_verify_before_prune_run_marker_healthy_run_passes():
    def runner(cypher: str, params: dict):
        if "RETURN count(cur)" in cypher:
            return [{"n": 1490}]
        if "RETURN count(node)" in cypher:
            return [{"n": 10}]
        return None

    n_cur, n_prev = pipeline.verify_before_prune(
        _REGION,
        {},
        runner,
        iv="test-r",
        elevation_expected=False,
        pre_load_count=1500,
        run_id="test-r@20260713T000000Z-abc",
    )
    assert (n_cur, n_prev) == (1490, 10)


def test_load_matches_threads_run_id_to_loaders():
    # Every node the load loop writes must carry this run's marker — an unstamped
    # write would make the node look stale to its OWN run's prune.
    feat = _feat("Old Rag", "OSM")
    calls: list[tuple] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731

    _load_matches(runner, [], [feat], tier_by_name={"osm": 1}, iv="t", run_id="t@run1")

    trail_params = [p for c, p in calls if "MERGE (t:CanonicalTrail" in c]
    sr_params = [p for c, p in calls if "MERGE (r:SourceRecord" in c]
    assert trail_params and all(p["run_id"] == "t@run1" for p in trail_params)
    assert sr_params and all(p["run_id"] == "t@run1" for p in sr_params)


# ── Source-construction seam (task 4): the ingest region drives DEM/source resolve ─


def test_for_region_resolves_target_region_dem_not_ambient(monkeypatch, tmp_path):
    # The Richmond-got-0-elevation bug: `from_env` resolved the DEM against the ambient
    # region. `for_region` must re-resolve against the region being ingested — region A
    # has a DEM on disk, region B does not.
    from orchestration import config as cfg

    monkeypatch.setattr(cfg, "DEM_DIR", str(tmp_path))
    (tmp_path / "region-a.tif").write_bytes(b"")  # A has a DEM; B does not
    base = Settings.from_env({})
    a = base.for_region("region-a", env={})
    b = base.for_region("region-b", env={})
    assert a.region == "region-a" and a.dem_path == str(tmp_path / "region-a.tif")
    assert b.region == "region-b" and b.dem_path is None


def test_region_with_dem_enables_3dep_and_dem_less_does_not(monkeypatch, tmp_path):
    from ingestion.pipeline import _elevation_expected
    from orchestration import config as cfg

    monkeypatch.setattr(cfg, "DEM_DIR", str(tmp_path))
    (tmp_path / "region-a.tif").write_bytes(b"")  # DEM present for A only

    settings_a = Settings.from_env({}).for_region("region-a", env={})
    sources_a = pipeline.registry.enabled_sources(settings_a, names=["usgs-3dep"])
    # A region that expects elevation actually enables usgs-3dep with a resolved DEM.
    assert _elevation_expected(sources_a, settings_a) is True

    settings_b = Settings.from_env({}).for_region("region-b", env={})
    sources_b = pipeline.registry.enabled_sources(settings_b, names=["usgs-3dep"])
    # B (no DEM) degrades silently — elevation is NOT expected, so it won't trip the gate.
    assert _elevation_expected(sources_b, settings_b) is False


# ── Golden-region regression (task 5): quality regressions must fail CI ───────────


def _write_golden_dem(path) -> None:
    """A tiny north-up 3DEP-like ramp covering the OSM fixture geometry (lon
    -78.30…-78.20, lat 38.50…38.60), elevation rising west→east so a real profile builds."""
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    width = height = 10
    res = 0.01
    transform = from_origin(-78.30, 38.60, res, res)
    data = np.zeros((height, width), dtype="float32")
    for col in range(width):
        data[:, col] = col * 10.0
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
    ) as dataset:
        dataset.write(data, 1)


def _e2e_osm_client_with_junk() -> httpx.Client:
    """OSM mock: one real trail + one TIGER-misimported numbered state route ("Snake
    Road", ref=SR 650) — the known junk `is_trail_worthy` must drop."""

    def handler(_r: httpx.Request) -> httpx.Response:
        body = json.dumps(
            {
                "elements": [
                    {
                        "type": "way",
                        "id": 1,
                        "tags": {"name": "Old Rag Loop", "highway": "path"},
                        "geometry": [{"lon": -78.28, "lat": 38.55}, {"lon": -78.27, "lat": 38.56}],
                    },
                    {
                        "type": "way",
                        "id": 2,
                        "tags": {"name": "Snake Road", "highway": "track", "ref": "SR 650"},
                        "geometry": [{"lon": -78.26, "lat": 38.55}, {"lon": -78.25, "lat": 38.56}],
                    },
                ]
            }
        ).encode()
        return httpx.Response(200, content=body, headers={"content-type": "application/json"})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_golden_region_regression(monkeypatch, tmp_path):
    """The one behavioral golden: real OSM/NPS/USFS adapters (transports mocked) + a real
    3DEP source over a cropped DEM fixture. Asserts the expected corpus SHAPE so a quality
    regression fails CI — the known real trail PRESENT and conflated, the known junk state
    route ABSENT (filtered), and elevation PRESENT for the DEM'd region."""
    pytest.importorskip("rasterio")
    pytest.importorskip("numpy")
    from ingestion.sources.usgs_3dep import RasterioDEMSampler, UsgsThreeDEPSource

    dem = tmp_path / "golden.tif"
    _write_golden_dem(dem)
    usfs_path = _e2e_usfs_file()
    try:
        real_sources = [
            OsmSource(client=_e2e_osm_client_with_junk()),
            NpsSource(client=_e2e_nps_client()),
            UsfsSource(geojson_path=usfs_path),
            UsgsThreeDEPSource(sampler=RasterioDEMSampler(str(dem)), resolution_m=50.0),
        ]
        _inject(monkeypatch, real_sources)
        settings = replace(_SETTINGS, review_band_dir=str(tmp_path / "review"))

        counts = run_pipeline(_REGION, dry_run=True, settings=settings)

        # Trail count + junk ABSENT: only the real trail survives; "Snake Road" (SR 650)
        # is dropped by the trail_filter. If a regression lets the junk through this is 2.
        assert counts["osm"] == 1
        assert counts["osm_consolidated"] == 1
        # A known real trail PRESENT and conflated with its NPS record. The OSM name
        # ('Old Rag Loop') differs from the NPS name ('Old Rag') by a DISCRIMINATING
        # "loop" suffix, so the redesigned matcher routes the pair to REVIEW rather than
        # auto-stamping the loop's name — precision over recall by design (matcher note #1).
        assert counts["auto_accept"] == 0
        assert counts["review"] == 1
        # Elevation PRESENT for the DEM'd region: 8 profile facts for the one trail.
        assert counts["enrichment_facts"] == 8
    finally:
        usfs_path.unlink(missing_ok=True)


# ── Review-band persistence (DQ follow-up: adjudicate the middle tier later) ──


def _review_match(osm_name: str, agency_name: str, agency_source: str, score: int = 70) -> Match:
    return Match(
        a=_feat(osm_name, "osm"),
        b=_feat(agency_name, agency_source),
        name_score=score,
        agreement=Agreement(overlap=0.1, hausdorff_m=120.0),
        verdict="review",
    )


def test_persist_review_band_writes_one_line_per_match_with_expected_fields(tmp_path):
    review = [
        _review_match("Old Rag Loop", "Old Rag", "nps", score=72),
        _review_match("Snake Hollow Trail", "Snake Hollow", "usfs", score=65),
    ]

    written = _persist_review_band(review, "test-r", str(tmp_path))

    assert written == 2
    out = tmp_path / "test-r.jsonl"
    lines = [json.loads(line) for line in out.read_text().splitlines()]
    assert lines == [
        {
            "osm_name": "Old Rag Loop",
            "agency_name": "Old Rag",
            "name_score": 72,
            "source": "nps",
            "region": "test-r",
        },
        {
            "osm_name": "Snake Hollow Trail",
            "agency_name": "Snake Hollow",
            "name_score": 65,
            "source": "usfs",
            "region": "test-r",
        },
    ]


def test_persist_review_band_noop_on_empty_review(tmp_path):
    written = _persist_review_band([], "test-r", str(tmp_path))

    assert written == 0
    assert not (tmp_path / "test-r.jsonl").exists()


def test_persist_review_band_creates_missing_dir(tmp_path):
    out_dir = tmp_path / "nested" / "review"

    written = _persist_review_band([_review_match("A", "B", "nps")], "test-r", str(out_dir))

    assert written == 1
    assert (out_dir / "test-r.jsonl").exists()


def test_persist_review_band_overwrites_rather_than_appends(tmp_path):
    _persist_review_band([_review_match("A", "B", "nps")], "test-r", str(tmp_path))
    _persist_review_band([_review_match("C", "D", "usfs")], "test-r", str(tmp_path))

    lines = (tmp_path / "test-r.jsonl").read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["osm_name"] == "C"


def test_persist_review_band_scopes_file_by_region(tmp_path):
    _persist_review_band([_review_match("A", "B", "nps")], "region-a", str(tmp_path))
    _persist_review_band([_review_match("C", "D", "usfs")], "region-b", str(tmp_path))

    assert (tmp_path / "region-a.jsonl").exists()
    assert (tmp_path / "region-b.jsonl").exists()


def test_persist_review_band_degrades_on_write_failure(tmp_path, caplog):
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory")  # a file, not a dir — mkdir under it must fail

    with caplog.at_level("WARNING"):
        written = _persist_review_band(
            [_review_match("A", "B", "nps")], "test-r", str(blocked / "review")
        )

    assert written == 0
    assert "Review-band persistence failed" in caplog.text


def test_run_pipeline_persists_review_band(monkeypatch, tmp_path):
    """Integration: run_pipeline wires the review list it already computes (line ~695)
    through to disk — the file exists, matches counts['review'], and never touches
    the graph (dry_run means no Neo4j import even happens)."""
    a = _StubSource("osm", role=ConflationRole.spine, features=[_feat("Old Rag Loop", "OSM")])
    b = _StubSource("nps", features=[_feat("Old Rag", "NPS")])
    _inject(monkeypatch, [a, b])
    settings = replace(_SETTINGS, review_band_dir=str(tmp_path / "review"))

    counts = run_pipeline(_REGION, dry_run=True, settings=settings)

    assert counts["review"] == 1
    assert counts["review_persisted"] == 1
    out = tmp_path / "review" / f"{_REGION.region_id}.jsonl"
    assert out.exists()
    record = json.loads(out.read_text().splitlines()[0])
    assert record["osm_name"] == "Old Rag Loop"
    assert record["agency_name"] == "Old Rag"
    assert record["source"] == "NPS"
    assert record["region"] == _REGION.region_id


# ── Epic 027 S3 — facet-diff gate wired into the live (non-dry-run) path ───────
#
# run_pipeline's live path imports `graph.client.GraphClient` and several
# `graph.load` functions LOCALLY (inside the function body), so patching the
# attributes on the already-imported `graph.client`/`graph.load` modules is
# picked up by that local `from ... import ...` at call time — no real Neo4j
# needed. `graph.load.make_runner` is patched to return our fake runner directly
# (ignoring the fake session), so the fake session/driver/client only need to
# satisfy the `with gc._ensure_driver().session() as session:` protocol.


class _FakeSessionCM:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeDriver:
    def session(self):
        return _FakeSessionCM()


class _FakeGraphClient:
    def __init__(self, *args, **kwargs):
        pass

    def _ensure_driver(self):
        return _FakeDriver()

    def close(self):
        pass


def _verify_ok_runner():
    """Answers `verify_before_prune`'s `count_region_versions` queries with counts
    that clear the (default 0.5) ratio gate, so verify never raises — the facet
    gate is what these tests exercise."""

    def runner(cypher: str, params: dict):
        if "RETURN count(cur)" in cypher:
            return [{"n": 990}]
        if "RETURN count(node)" in cypher:
            return [{"n": 10}]
        return []

    return runner


def _wire_fake_graph(
    monkeypatch,
    *,
    pre_load_count: int,
    pre_facets: dict,
    post_facets: dict,
    prune_outcome: PruneOutcome | None = None,
):
    """Install the fake GraphClient + monkeypatched graph.load functions the live
    path needs, and return the `prune_stale_trails` MagicMock so a test can assert
    on whether/how it was called."""
    monkeypatch.setattr("graph.client.GraphClient", _FakeGraphClient)
    monkeypatch.setattr("graph.load.make_runner", lambda session: _verify_ok_runner())
    monkeypatch.setattr(
        "graph.load.count_region_trails", lambda runner, *, region_id: pre_load_count
    )
    monkeypatch.setattr(
        "graph.load.count_region_facets", lambda runner, *, region_id: dict(pre_facets)
    )
    monkeypatch.setattr(
        "graph.load.count_version_facets",
        lambda runner, iv, *, region_id: dict(post_facets),
    )
    monkeypatch.setattr("graph.load.load_enrichment_facts", lambda runner, facts: 0)
    prune_mock = MagicMock(
        return_value=prune_outcome or PruneOutcome(pruned=True, n_cur=990, n_prev=10, deleted=10)
    )
    monkeypatch.setattr("graph.load.prune_stale_trails", prune_mock)
    return prune_mock


def _live_region_settings(monkeypatch, tmp_path):
    """An empty-source live-path run: no spine features to load, so `_load_matches`
    writes nothing and the test only exercises the facet-gate wiring."""
    spine = _StubSource("osm", role=ConflationRole.spine, features=[])
    _inject(monkeypatch, [spine])
    return replace(_SETTINGS, review_band_dir=str(tmp_path / "review"))


def test_hard_facet_breach_skips_prune(monkeypatch, tmp_path):
    settings = _live_region_settings(monkeypatch, tmp_path)
    monkeypatch.setenv("ADVENTURE_INGEST_STATS_DIR", str(tmp_path / "stats"))
    prune_mock = _wire_fake_graph(
        monkeypatch,
        pre_load_count=1000,
        pre_facets={"source=nps": 1000, "source=osm": 1000},
        # source=nps collapses 1000 -> 100 (delta=-900, rel_pct=90%) -> breaches
        # 'low' (the coarsest, most severe level) even though source=osm barely
        # moves — the exact class-specific collapse the scalar ratio guard can't see.
        post_facets={"source=nps": 100, "source=osm": 990},
    )

    counts = run_pipeline(_REGION, dry_run=False, settings=settings)

    assert prune_mock.call_count == 0
    assert counts["pruned"] == 0
    assert counts["prune_ran"] == 0
    assert counts["prune_blocked_facets"] == 1


def test_first_ever_ingest_does_not_block_prune_on_appeared_buckets(monkeypatch, tmp_path):
    """Regression: pre_load_count == 0 (first-ever ingest of this region) must skip
    the facet hard-gate exactly like the existing scalar guards' own no-denominator
    pass-through (verify_before_prune, prune_stale_trails' ratio guard) — mirroring
    Design Decision 3's parity with the scalar gate. Without this, EVERY bucket looks
    'brand new' (pre=0 -> rel_pct=100.0 by get_rel's rule) and a healthy first-ever
    region onboarding would spuriously hard-breach on any bucket with >100 trails,
    even though nothing has collapsed — there is no prior baseline to collapse from."""
    settings = _live_region_settings(monkeypatch, tmp_path)
    monkeypatch.setenv("ADVENTURE_INGEST_STATS_DIR", str(tmp_path / "stats"))
    prune_mock = _wire_fake_graph(
        monkeypatch,
        pre_load_count=0,
        pre_facets={},
        post_facets={"source=osm": 500, "way_type=path": 500},
    )

    counts = run_pipeline(_REGION, dry_run=False, settings=settings)

    assert prune_mock.call_count == 1
    assert counts["pruned"] == 10
    assert counts["prune_ran"] == 1
    assert "prune_blocked_facets" not in counts


def test_healthy_reingest_still_prunes(monkeypatch, tmp_path):
    # Falsification of the 2026-07-12 bug: `counts["pruned"] = int(prune_outcome.pruned)`
    # printed `pruned: 1` no matter how many nodes a run actually deleted (a real run
    # deleted 36 in one region, 5 in another; both logged as `pruned: 1`). Pin a prune
    # that deletes N=36 nodes — distinct from `pruned` (a bool) and from `n_cur`/`n_prev`
    # — and assert the pipeline summary reports the TRUE count, not 0-or-1.
    settings = _live_region_settings(monkeypatch, tmp_path)
    monkeypatch.setenv("ADVENTURE_INGEST_STATS_DIR", str(tmp_path / "stats"))
    prune_mock = _wire_fake_graph(
        monkeypatch,
        pre_load_count=1000,
        pre_facets={"source=osm": 1000},
        post_facets={"source=osm": 990},  # tiny, healthy delta -> no breach anywhere
        prune_outcome=PruneOutcome(pruned=True, n_cur=990, n_prev=36, deleted=36),
    )

    counts = run_pipeline(_REGION, dry_run=False, settings=settings)

    assert prune_mock.call_count == 1
    assert counts["pruned"] == 36  # the TRUE deleted-node count, not int(True) == 1
    assert counts["prune_ran"] == 1
    assert "prune_blocked_facets" not in counts


def test_facet_ratio_ignores_healthy_scalar_guards(monkeypatch, tmp_path):
    """AC-3.5: the facet gate is purely additive — a scalar-guard block (ratio/
    verify) is untouched by it, and a healthy scalar pass with a healthy facet diff
    still lets prune_stale_trails' own Guards 1/2 run exactly as before (this test
    just pins that the facet gate itself never overrides prune_stale_trails' own
    return value)."""
    settings = _live_region_settings(monkeypatch, tmp_path)
    monkeypatch.setenv("ADVENTURE_INGEST_STATS_DIR", str(tmp_path / "stats"))
    # prune_stale_trails' OWN guard decides not to prune (e.g. its ratio guard) —
    # the facet gate must not change that outcome when it found no hard breach.
    prune_mock = _wire_fake_graph(
        monkeypatch,
        pre_load_count=1000,
        pre_facets={"source=osm": 1000},
        post_facets={"source=osm": 990},
        prune_outcome=PruneOutcome(pruned=False, n_cur=990, n_prev=10, reason="guard fired"),
    )

    counts = run_pipeline(_REGION, dry_run=False, settings=settings)

    assert prune_mock.call_count == 1
    assert counts["pruned"] == 0
    assert counts["prune_ran"] == 0
    assert "prune_blocked_facets" not in counts


def test_run_pipeline_mints_run_id_and_threads_it(monkeypatch, tmp_path):
    """The live path mints ONE per-run marker and threads it end-to-end: every
    CanonicalTrail/SourceRecord write carries it, and the same value reaches
    `prune_stale_trails` — the stamp and the stale test must agree or the run would
    prune its own writes (or none at all)."""
    spine = _StubSource("osm", role=ConflationRole.spine, features=[_feat("Old Rag Loop", "OSM")])
    _inject(monkeypatch, [spine])
    settings = replace(_SETTINGS, review_band_dir=str(tmp_path / "review"))
    monkeypatch.setenv("ADVENTURE_INGEST_STATS_DIR", str(tmp_path / "stats"))

    writes: list[tuple[str, dict]] = []

    def recording_runner(cypher: str, params: dict):
        if "RETURN count(cur)" in cypher:
            return [{"n": 990}]
        if "RETURN count(node)" in cypher:
            return [{"n": 10}]
        writes.append((cypher, params))
        return []

    monkeypatch.setattr("graph.client.GraphClient", _FakeGraphClient)
    monkeypatch.setattr("graph.load.make_runner", lambda session: recording_runner)
    monkeypatch.setattr("graph.load.count_region_trails", lambda runner, *, region_id: 1000)
    monkeypatch.setattr("graph.load.count_region_facets", lambda runner, *, region_id: {})
    monkeypatch.setattr("graph.load.count_version_facets", lambda runner, iv, *, region_id: {})
    monkeypatch.setattr("graph.load.load_enrichment_facts", lambda runner, facts: 0)
    prune_mock = MagicMock(return_value=PruneOutcome(pruned=True, n_cur=990, n_prev=10))
    monkeypatch.setattr("graph.load.prune_stale_trails", prune_mock)

    run_pipeline(_REGION, dry_run=False, settings=settings)

    assert prune_mock.call_count == 1
    run_id = prune_mock.call_args.kwargs["run_id"]
    assert run_id is not None and run_id.startswith(f"{_REGION.region_id}@")
    trail_params = [p for c, p in writes if "MERGE (t:CanonicalTrail" in c]
    sr_params = [p for c, p in writes if "MERGE (r:SourceRecord" in c]
    assert trail_params and all(p.get("run_id") == run_id for p in trail_params)
    assert sr_params and all(p.get("run_id") == run_id for p in sr_params)


def test_ingest_stats_write_failure_does_not_raise_or_change_prune_outcome(monkeypatch, tmp_path):
    settings = _live_region_settings(monkeypatch, tmp_path)
    _wire_fake_graph(
        monkeypatch,
        pre_load_count=1000,
        pre_facets={"source=osm": 1000},
        post_facets={"source=osm": 990},
    )
    # Force the best-effort stats.json write to fail: point it at a path whose
    # parent already exists as a FILE, so `path.parent.mkdir(exist_ok=True)` raises
    # FileExistsError (an OSError) deterministically, no mocking of `open` needed.
    blocker = tmp_path / "blocked"
    blocker.write_text("occupies the stats-dir path")
    monkeypatch.setattr(
        pipeline, "ingest_stats_path", lambda region_id: blocker / f"{region_id}.json"
    )

    counts = run_pipeline(_REGION, dry_run=False, settings=settings)

    assert counts["pruned"] == 10  # unaffected by the write failure
    assert not (blocker / f"{_REGION.region_id}.json").exists()


def test_stats_json_written_with_expected_schema(monkeypatch, tmp_path):
    settings = _live_region_settings(monkeypatch, tmp_path)
    monkeypatch.setenv("ADVENTURE_INGEST_STATS_DIR", str(tmp_path / "stats"))
    _wire_fake_graph(
        monkeypatch,
        pre_load_count=1000,
        pre_facets={"source=nps": 1000, "source=osm": 1000},
        post_facets={"source=nps": 100, "source=osm": 990},
    )

    run_pipeline(_REGION, dry_run=False, settings=settings)

    out = tmp_path / "stats" / f"{_REGION.region_id}.json"
    assert out.exists()
    payload = json.loads(out.read_text())
    assert payload["region"] == _REGION.region_id
    assert payload["prune_blocked"] is True
    assert payload["buckets"], "expected at least one bucket row"
    # Sorted by |delta| descending (AC-3.7): source=nps (|-900|) before source=osm (|-10|).
    deltas = [abs(b["delta"]) for b in payload["buckets"]]
    assert deltas == sorted(deltas, reverse=True)
    top = payload["buckets"][0]
    assert top["dimension"] == "source"
    assert top["value"] == "nps"
    assert top["breached_level"] == "low"
