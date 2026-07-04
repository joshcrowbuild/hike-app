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
from pathlib import Path

import httpx
import pytest
from shapely.geometry import LineString

from ingestion import pipeline
from ingestion.conflate.match import Feature
from ingestion.pipeline import _load_matches, consolidate_osm_segments, load_region, run_pipeline
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


def test_pipeline_dry_run_returns_counts(monkeypatch):
    spine = _StubSource("osm", role=ConflationRole.spine, features=[_feat("Old Rag Loop", "OSM")])
    agency = _StubSource("nps", features=[_feat("Old Rag", "NPS")])
    _inject(monkeypatch, [spine, agency])

    counts = run_pipeline(_REGION, dry_run=True, settings=_SETTINGS)

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


def test_ac5_2_default_config_counts_through_real_adapters(monkeypatch):
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

        counts = run_pipeline(_REGION, dry_run=True, settings=_SETTINGS)

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


def test_reingest_without_dem_does_not_error_or_wipe(monkeypatch):
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

        counts = run_pipeline(_REGION, dry_run=True, settings=_SETTINGS)

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
