"""Live-Neo4j integration for the maps/elevation backend (Epic 016 S1 + Epic 017).

Behind `@pytest.mark.neo4j` (Epic 015 pattern): the fast legs skip these; CI's
integration job runs them against a real database. They prove the round-trips the
DB-free tests can only fake — enrichment facts persist + read back, and the
ingest → enrich → trail_detail path yields the served contract from real nodes.
"""

from __future__ import annotations

import pytest
from shapely.geometry import LineString

from api.app import _trip_detail_response
from graph.load import load_canonical_trail, load_enrichment_facts
from graph.queries import trail_detail
from ingestion.conflate.match import Feature
from ingestion.pipeline import _canonical_nodes, _load_matches
from ingestion.sources.base import CanonicalNode, EnrichmentFact
from ingestion.sources.usgs_3dep import UsgsThreeDEPSource


def _runner(sess):
    def run(cypher, params):
        return sess.run((cypher, params))

    return run


class _Ramp:
    """A monotonic climb keyed on longitude — a deterministic stand-in for the DEM."""

    def sample(self, lon: float, lat: float) -> float | None:
        return (lon + 78.30) * 1000.0


@pytest.mark.neo4j
def test_enrichment_loader_round_trips(clean_graph):
    sess = clean_graph.scoped_session("ingest")
    runner = _runner(sess)
    load_canonical_trail(runner, "ct:test", "Test Trail", lat=38.5, lon=-78.3)

    facts = [
        EnrichmentFact("3dep", "profile_distances_m", [0.0, 10.0, 20.0], "ct:test"),
        EnrichmentFact("3dep", "profile_elevations_m", [100.0, 110.0, 130.0], "ct:test"),
        EnrichmentFact("3dep", "total_gain_m", 30.0, "ct:test"),
        EnrichmentFact("3dep", "elev_source", "usgs-3dep", "ct:test"),
    ]
    assert load_enrichment_facts(runner, facts) == 1

    rows = sess.run(
        (
            "MATCH (t:CanonicalTrail {canonical_id: 'ct:test'}) "
            "RETURN t.profile_distances_m AS d, t.profile_elevations_m AS e, "
            "       t.total_gain_m AS g, t.elev_source AS s",
            {},
        )
    )
    row = rows[0]
    assert row["d"] == [0.0, 10.0, 20.0]
    assert row["e"] == [100.0, 110.0, 130.0]
    assert row["g"] == 30.0
    assert row["s"] == "usgs-3dep"

    # Idempotent re-run: still one node, values unchanged.
    assert load_enrichment_facts(runner, facts) == 1
    count = sess.run(("MATCH (t:CanonicalTrail) RETURN count(t) AS c", {}))
    assert count[0]["c"] == 1


@pytest.mark.neo4j
def test_ingest_enrich_then_trail_detail_serves_contract(clean_graph):
    sess = clean_graph.scoped_session("ingest")
    runner = _runner(sess)
    feat = Feature(
        name="Old Rag",
        geom=LineString([(-78.30, 38.55), (-78.29, 38.56), (-78.28, 38.57)]),
        source="OSM",
        ref="r1",
    )
    _load_matches(runner, [], [feat], tier_by_name={"osm": 2}, iv="t")

    nodes = _canonical_nodes([], [feat])
    src = UsgsThreeDEPSource(sampler=_Ramp(), resolution_m=100.0, min_coverage=0.0)
    facts: list[EnrichmentFact] = []
    for node in nodes:
        facts.extend(src.enrich(node))
    load_enrichment_facts(runner, facts)

    cid = nodes[0].canonical_id
    rows = sess.run(trail_detail(cid))
    assert rows, "trail_detail returned no row for the just-loaded trail"
    row = rows[0]
    assert row["route_geom_wkt"].startswith("LINESTRING")
    assert row["segment_wkts"]  # at least one Segment persisted
    assert row["profile_distances_m"] and row["profile_elevations_m"]
    assert row["total_gain_m"] > 0

    # The API serializer turns the row into the frozen contract.
    resp = _trip_detail_response(cid, row)
    assert resp.geometry is not None and resp.geometry.type in ("LineString", "MultiLineString")
    assert resp.geometry_confidence in ("stated", "hedged")
    assert resp.elevation_profile is not None
    assert resp.elevation_profile.total_gain_m > 0
    assert resp.trailhead is not None  # trail point fallback (no Trailhead node here)


@pytest.mark.neo4j
def test_no_coverage_trail_yields_null_profile(clean_graph):
    sess = clean_graph.scoped_session("ingest")
    runner = _runner(sess)
    feat = Feature(
        name="No DEM Trail",
        geom=LineString([(-78.30, 38.55), (-78.29, 38.56)]),
        source="OSM",
        ref="r2",
    )
    _load_matches(runner, [], [feat], tier_by_name={"osm": 2}, iv="t")

    # An enrichment source that covers nothing emits no facts → profile stays null.
    class _NoCoverage:
        def sample(self, lon: float, lat: float) -> float | None:
            return None

    src = UsgsThreeDEPSource(sampler=_NoCoverage())
    nodes = _canonical_nodes([], [feat])
    facts: list[EnrichmentFact] = []
    for node in nodes:
        facts.extend(
            src.enrich(CanonicalNode(node.canonical_id, node.name, geom_wkt=node.geom_wkt))
        )
    assert facts == []  # source-or-silence

    cid = nodes[0].canonical_id
    row = sess.run(trail_detail(cid))[0]
    resp = _trip_detail_response(cid, row)
    assert resp.geometry is not None  # geometry present
    assert resp.elevation_profile is None  # but no profile — null, not faked
