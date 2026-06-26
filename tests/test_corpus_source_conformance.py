"""Epic 012 S6 — shared CorpusSource conformance suite + the echo drop-in proof.

A parametrized contract test EVERY registered geometry source must satisfy (driven
by a mocked client / fixture file — no live calls). Adding a new source = add it to
the registry and wire a fixture here, and it is automatically held to the contract.
EchoSource (AC-6.2) is a registered source like any other, so it flows through the
same suite unmodified — the empirical proof the seam doesn't leak (SS-12).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import httpx
import pytest

from ingestion.pipeline import _load_matches
from ingestion.sources.base import (
    CanonicalNode,
    ConflationRole,
    CorpusSource,
    EnrichmentFact,
    Feature,
    Region,
    SourceKind,
)
from ingestion.sources.echo import EchoSource
from ingestion.sources.nps import NpsSource
from ingestion.sources.osm import OsmSource
from ingestion.sources.registry import SOURCE_REGISTRY
from ingestion.sources.usfs import UsfsSource

_REGION = Region(region_id="test-r", bbox=(38.55, -78.45, 38.70, -78.25))


# ── Mock transports / fixture file (no live source) ───────────────────────────


def _ok_osm_client() -> httpx.Client:
    def handler(_r: httpx.Request) -> httpx.Response:
        body = json.dumps(
            {
                "elements": [
                    {
                        "type": "way",
                        "id": 1,
                        "tags": {"name": "Conf Trail", "highway": "path"},
                        "geometry": [{"lon": -78.28, "lat": 38.55}, {"lon": -78.27, "lat": 38.56}],
                    }
                ]
            }
        ).encode()
        return httpx.Response(200, content=body, headers={"content-type": "application/json"})

    return httpx.Client(transport=httpx.MockTransport(handler))


def _ok_nps_client() -> httpx.Client:
    def handler(r: httpx.Request) -> httpx.Response:
        offset = r.url.params.get("resultOffset", "0")
        feats = (
            [
                {
                    "type": "Feature",
                    "properties": {"TRLNAME": "Conf Trail"},
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


def _fail_client() -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))


_USFS_FILE = Path(tempfile.mkdtemp()) / "trails.geojson"
_USFS_FILE.write_text(
    json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"TRAIL_NAME": "Conf Trail", "TRAIL_NO": "9"},
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[-78.30, 38.60], [-78.29, 38.61]],
                    },
                }
            ],
        }
    )
)


def _valid_sources() -> list[CorpusSource]:
    """Every registered geometry source, each wired with a working fixture."""
    return [
        OsmSource(client=_ok_osm_client()),
        NpsSource(client=_ok_nps_client()),
        UsfsSource(geojson_path=_USFS_FILE),
        EchoSource(),
    ]


def _failing_sources() -> list[CorpusSource]:
    """Geometry sources with an injectable transport failure (echo is a fixed stub
    with no failure mode, so it is exercised only by the valid + idempotency cases)."""
    return [
        OsmSource(client=_fail_client()),
        NpsSource(client=_fail_client()),
        UsfsSource(geojson_path=Path("nope.geojson")),
    ]


def test_every_registered_geometry_source_is_covered():
    """Guard: the conformance fixtures cover every registered geometry source, so a
    newly-registered source can't silently skip the suite."""
    registered = {name for name, cls in SOURCE_REGISTRY.items() if cls.kind is SourceKind.geometry}
    covered = {s.name for s in _valid_sources()}
    assert registered <= covered, f"uncovered geometry sources: {registered - covered}"


# ── AC-6.1(a) — fetch(region) → list[Feature] with non-empty provenance ───────


@pytest.mark.parametrize("source", _valid_sources(), ids=lambda s: s.name)
def test_ac6_1a_fetch_returns_features_with_provenance(source):
    feats = source.fetch(_REGION)
    assert isinstance(feats, list) and feats, f"{source.name} returned no features"
    for f in feats:
        assert isinstance(f, Feature)
        assert f.source, "Feature.source must be set (provenance)"
        assert f.name or f.ref, "Feature must carry a name or a ref (provenance)"


# ── AC-6.1(b) — fetch returns [] (never raises) on injected failure ───────────


@pytest.mark.parametrize("source", _failing_sources(), ids=lambda s: s.name)
def test_ac6_1b_fetch_degrades_to_empty(source):
    assert source.fetch(_REGION) == []


# ── AC-6.1(c) — produced Features are idempotent under the load MERGE ──────────


@pytest.mark.parametrize("source", _valid_sources(), ids=lambda s: s.name)
def test_ac6_1c_load_is_idempotent(source):
    feats = source.fetch(_REGION)
    tier_by_name = {source.name: source.authority_tier}

    # A fake graph that emulates MERGE dedup by the node/edge merge key, so
    # re-running the load against the SAME state must add zero nodes/edges.
    graph: set[tuple] = set()
    statements: list[str] = []

    def runner(cypher: str, params: dict) -> None:
        statements.append(cypher)
        if "MERGE (t:CanonicalTrail" in cypher:
            graph.add(("CanonicalTrail", params["cid"]))
        elif "MERGE (r:SourceRecord" in cypher:
            graph.add(("SourceRecord", params["sr_uid"]))
        elif "SAME_AS" in cypher:
            graph.add(("SAME_AS", params["cid"], params["sr_uid"], params["source"]))

    _load_matches(runner, [], feats, tier_by_name=tier_by_name, iv="conf")
    size_after_first = len(graph)
    _load_matches(runner, [], feats, tier_by_name=tier_by_name, iv="conf")
    size_after_second = len(graph)

    assert size_after_first > 0, "load produced no nodes/edges"
    assert size_after_second == size_after_first  # second load adds nothing (MERGE)
    # Every write is MERGE-idempotent; the per-trail segment clear (DETACH DELETE,
    # Epic 016 S1 re-ingest hygiene) is likewise idempotent — clear-then-MERGE yields
    # the same final state on a re-run.
    assert all(("MERGE" in s) or ("DETACH DELETE" in s) for s in statements)


# ── AC-6.2 — EchoSource passes the suite as a registered source (above) ───────


def test_ac6_2_echo_is_registered_and_conformant():
    assert SOURCE_REGISTRY.get("echo") is EchoSource
    assert "echo" in {s.name for s in _valid_sources()}


# ── AC-6.4 — enrichment conformance: enrich → list[EnrichmentFact] ────────────


class _EnrichStub(CorpusSource):
    name = "enrich_stub"
    kind = SourceKind.enrichment
    role = ConflationRole.enrich
    authority_tier = 1

    def fetch(self, region):  # never called for an enrichment source (AC-5.3)
        raise NotImplementedError("enrichment sources do not fetch")

    @classmethod
    def from_config(cls, settings):
        return cls()

    def enrich(self, canonical):
        return [
            EnrichmentFact(
                source=self.name,
                attribute="gain_ft",
                value=1234.0,
                canonical_id=canonical.canonical_id,
                recorded_resolution="10m",
            )
        ]


def test_ac6_4_enrichment_returns_enrichment_facts():
    facts = _EnrichStub().enrich(CanonicalNode(canonical_id="ct:x", name="X"))
    assert facts and all(isinstance(f, EnrichmentFact) for f in facts)
    assert facts[0].canonical_id == "ct:x"
