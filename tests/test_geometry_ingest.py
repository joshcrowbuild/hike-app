"""Tests for the ingest-time route precompute (Epic 016 S1) + enrichment degrade.

The pipeline assembles each trail's route from its (spine feature) geometry and
stores it ready-to-serve: `route_geom_wkt` on the CanonicalTrail + one `Segment`
per route part. A feature with no line yields no geometry — never a fabricated one
(Rule #1). Enrichment isolates a failing source (degrade-and-disclose, AC-1.2).
Network-free: a fake runner captures the emitted (cypher, params).
"""

from __future__ import annotations

from shapely.geometry import LineString, Point

from ingestion.conflate.match import Agreement, Feature, Match
from ingestion.pipeline import _canonical_nodes, _load_matches, run_pipeline
from ingestion.sources.base import ConflationRole, CorpusSource, EnrichmentFact, Region, SourceKind
from orchestration.config import Settings

_REGION = Region(region_id="test-r", bbox=(38.55, -78.45, 38.70, -78.25))
_SETTINGS = Settings.from_env({})


def _line_feat(name: str, source: str, ref: str = "r1") -> Feature:
    return Feature(
        name=name,
        geom=LineString([(-78.28, 38.55), (-78.27, 38.56)]),
        source=source,
        ref=ref,
    )


# ── route_geom_wkt + segments persisted at load (AC-1.1) ──────────────────────


def test_unmatched_spine_stores_route_geom_and_segment():
    calls: list[tuple[str, dict]] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731
    _load_matches(runner, [], [_line_feat("Old Rag", "OSM")], tier_by_name={"osm": 2}, iv="t")

    ct = [p for c, p in calls if "MERGE (t:CanonicalTrail" in c]
    assert ct and ct[0]["route_geom_wkt"].startswith("LINESTRING")
    seg = [p for c, p in calls if "MERGE (s:Segment" in c]
    assert seg and seg[0]["geom_wkt"].startswith("LINESTRING")
    assert any("HAS_SEGMENT" in c for c, _ in calls)


def test_auto_accept_spine_stores_route_geom():
    a = _line_feat("Old Rag", "OSM", "osm/1")
    b = _line_feat("Old Rag", "NPS", "nps/1")
    m = Match(a, b, 95, Agreement(0.9, 10.0), "auto-accept")
    calls: list[tuple[str, dict]] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731
    _load_matches(runner, [m], [a], tier_by_name={"osm": 2, "nps": 1}, iv="t")

    ct = [p for c, p in calls if "MERGE (t:CanonicalTrail" in c]
    assert ct and ct[0].get("route_geom_wkt", "").startswith("LINESTRING")


def test_line_only_segments_have_valid_wkt_assembling_back():
    from ingestion.route import parse_wkt

    calls: list[tuple[str, dict]] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731
    _load_matches(runner, [], [_line_feat("Old Rag", "OSM")], tier_by_name={"osm": 2}, iv="t")
    seg = [p for c, p in calls if "MERGE (s:Segment" in c][0]
    assert parse_wkt(seg["geom_wkt"]) is not None  # round-trips


# ── source-or-silence: a no-line feature gets no geometry, no segment (Rule #1) ─


def test_point_only_feature_has_no_geometry_no_fabrication():
    pt = Feature(name="Blip", geom=Point(-78.28, 38.55), source="OSM", ref="r2")
    calls: list[tuple[str, dict]] = []
    runner = lambda c, p: calls.append((c, p))  # noqa: E731
    _load_matches(runner, [], [pt], tier_by_name={"osm": 2}, iv="t")

    ct = [p for c, p in calls if "MERGE (t:CanonicalTrail" in c]
    assert ct and ct[0]["route_geom_wkt"] is None  # geometry explicitly cleared, never faked
    assert not any("MERGE (s:Segment" in c for c, _ in calls)  # no fabricated segment


# ── CanonicalNode carries the assembled route for geometry-consuming enrichment ─


def test_canonical_nodes_carry_assembled_route_wkt():
    nodes = _canonical_nodes([], [_line_feat("Old Rag", "OSM")])
    assert len(nodes) == 1
    assert nodes[0].geom_wkt and nodes[0].geom_wkt.startswith("LINESTRING")


def test_canonical_node_no_geometry_for_point_feature():
    pt = Feature(name="Blip", geom=Point(-78.28, 38.55), source="OSM", ref="r2")
    nodes = _canonical_nodes([], [pt])
    assert nodes and nodes[0].geom_wkt is None


# ── Enrichment degrade-and-disclose: one failing source never aborts (AC-1.2) ──


class _GoodEnrich(CorpusSource):
    name = "good_enrich"
    kind = SourceKind.enrichment
    role = ConflationRole.enrich
    authority_tier = 1

    def fetch(self, region):
        raise NotImplementedError

    @classmethod
    def from_config(cls, settings):
        return cls()

    def enrich(self, canonical):
        return [EnrichmentFact(source=self.name, attribute="total_gain_m", value=1.0)]


class _FailingEnrich(CorpusSource):
    name = "bad_enrich"
    kind = SourceKind.enrichment
    role = ConflationRole.enrich
    authority_tier = 1

    def fetch(self, region):
        raise NotImplementedError

    @classmethod
    def from_config(cls, settings):
        return cls()

    def enrich(self, canonical):
        raise RuntimeError("boom")


class _SpineStub(CorpusSource):
    kind = SourceKind.geometry
    role = ConflationRole.spine
    authority_tier = 2

    def __init__(self, name, features):
        self.name = name
        self._features = list(features)
        super().__init__()

    def fetch(self, region):
        return list(self._features)

    @classmethod
    def from_config(cls, settings):
        return cls("osm", [])


def test_failing_enrichment_source_degrades_run_continues(monkeypatch):
    spine = _SpineStub("osm", [_line_feat("X", "OSM")])
    sources = [spine, _FailingEnrich(), _GoodEnrich()]
    monkeypatch.setattr(
        "ingestion.pipeline.registry.enabled_sources",
        lambda settings, names=None: list(sources),
    )
    counts = run_pipeline(_REGION, dry_run=True, settings=_SETTINGS)
    # The good source's fact survived; the bad source degraded without aborting.
    assert counts["enrichment_facts"] == 1
