"""Epic 012 — CorpusSource contract (S1) + the three refactored adapters (S3) + the
enrichment join contract (S5). Network-free: injectable httpx clients + temp files.

The conformance suite (every source held to one contract) lives in
test_corpus_source_conformance.py; this file covers the contract's *validation*
rules and the adapter↔old-fetcher regression equality.
"""

from __future__ import annotations

import abc
import json
import tempfile
from pathlib import Path

import httpx
import pytest

from ingestion.conflate.match import Feature as MatchFeature
from ingestion.fetch import nps as nps_fetch
from ingestion.fetch import osm as osm_fetch
from ingestion.fetch import usfs as usfs_fetch
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
from ingestion.sources.usfs import UsfsSource
from orchestration.config import Settings

_REGION = Region(region_id="test-r", bbox=(38.55, -78.45, 38.70, -78.25))


# ── AC-1.1 / AC-1.2 / AC-1.3 — types + Feature identity ───────────────────────


def test_ac1_1_exports_and_abc():
    assert issubclass(CorpusSource, abc.ABC)
    # fetch is the declared @abstractmethod (AC-1.1).
    assert "fetch" in CorpusSource.__abstractmethods__


def test_ac1_2_enum_membership_exact():
    assert {k.name for k in SourceKind} == {"geometry", "enrichment"}
    assert {r.name for r in ConflationRole} == {"spine", "conflate", "enrich"}


def test_ac1_3_feature_is_match_feature():
    # The seam reuses the proven Feature by name, never redefining it.
    assert Feature is MatchFeature


def test_ac1_3_fetch_takes_region_returns_features():
    feats = EchoSource().fetch(_REGION)
    assert isinstance(feats, list)
    assert all(isinstance(f, Feature) for f in feats)


# ── AC-1.4 / AC-1.5 — construction validation (fail loud at the boundary) ──────


def _good_geometry(tier: int = 2, role: ConflationRole = ConflationRole.conflate):
    class _Src(CorpusSource):
        name = "good"
        kind = SourceKind.geometry
        authority_tier = tier

        def fetch(self, region):
            return []

    _Src.role = role
    return _Src


def test_ac1_4_bad_tier_raises():
    Bad = _good_geometry(tier=9)
    with pytest.raises(ValueError, match="authority_tier"):
        Bad()


@pytest.mark.parametrize("tier", [1, 2, 3])
def test_ac1_4_valid_tiers_ok(tier):
    _good_geometry(tier=tier)()  # does not raise


def test_ac1_5_geometry_with_enrich_role_raises():
    Bad = _good_geometry(role=ConflationRole.enrich)
    with pytest.raises(ValueError, match="geometry source"):
        Bad()


def test_ac1_5_enrichment_with_spine_role_raises():
    class Bad(CorpusSource):
        name = "bad"
        kind = SourceKind.enrichment
        role = ConflationRole.spine
        authority_tier = 1

        def fetch(self, region):
            return []

        def enrich(self, canonical):
            return []

    with pytest.raises(ValueError, match="enrichment source"):
        Bad()


def test_ac1_5_enrichment_not_implementing_enrich_raises():
    class Bad(CorpusSource):
        name = "bad"
        kind = SourceKind.enrichment
        role = ConflationRole.enrich
        authority_tier = 1

        def fetch(self, region):
            return []

    with pytest.raises(ValueError, match="does not implement enrich"):
        Bad()


def test_ac1_5_geometry_implementing_only_enrich_raises_at_definition():
    # Leaving fetch abstract while implementing enrich on a geometry source is a
    # mis-declaration surfaced at class definition (ValueError, not a later TypeError).
    with pytest.raises(ValueError, match="implements enrich, not fetch"):

        class Bad(CorpusSource):
            name = "bad"
            kind = SourceKind.geometry
            role = ConflationRole.conflate
            authority_tier = 2

            def enrich(self, canonical):
                return []


# ── AC-1.6 — from_config always returns (no | None); base default is explicit ─


def test_ac1_6_base_from_config_not_implemented():
    with pytest.raises(NotImplementedError):
        CorpusSource.from_config(Settings.from_env({}))


def test_ac1_6_real_sources_from_config_return_instances():
    s = Settings.from_env({})
    for cls in (OsmSource, NpsSource, UsfsSource, EchoSource):
        src = cls.from_config(s)
        assert isinstance(src, CorpusSource)


# ── AC-3.1 — adapter ⇄ old-fetcher regression (identical Feature lists) ────────


def _norm(feats: list[Feature]) -> list[tuple]:
    return [(f.name, f.source, f.ref, f.geom.wkt) for f in feats]


def _osm_handler(_request: httpx.Request) -> httpx.Response:
    body = json.dumps(
        {
            "elements": [
                {
                    "type": "way",
                    "id": 123,
                    "tags": {"name": "Old Rag Loop", "highway": "path"},
                    "geometry": [{"lon": -78.28, "lat": 38.55}, {"lon": -78.27, "lat": 38.56}],
                }
            ]
        }
    ).encode()
    return httpx.Response(200, content=body, headers={"content-type": "application/json"})


def test_ac3_1_osm_adapter_matches_old_fetcher():
    client = httpx.Client(transport=httpx.MockTransport(_osm_handler))
    old = osm_fetch.fetch(_REGION.bbox, client=client)
    new = OsmSource(client=client).fetch(_REGION)
    assert _norm(old) == _norm(new)
    assert new and new[0].source == "OSM"


def _nps_handler(request: httpx.Request) -> httpx.Response:
    # Stateless pagination: page-0 has a feature, any later offset is empty (stop).
    offset = request.url.params.get("resultOffset", "0")
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


def test_ac3_1_nps_adapter_matches_old_fetcher():
    client = httpx.Client(transport=httpx.MockTransport(_nps_handler))
    old = nps_fetch.fetch(_REGION.bbox, client=client)
    new = NpsSource(client=client).fetch(_REGION)
    assert _norm(old) == _norm(new)
    assert new and new[0].source == "NPS"


def _usfs_file() -> Path:
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"TRAIL_NAME": "Jones Run Trail", "TRAIL_NO": "1"},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[-78.30, 38.60], [-78.29, 38.61]],
                },
            }
        ],
    }
    f = tempfile.NamedTemporaryFile(suffix=".geojson", mode="w", delete=False)
    json.dump(geojson, f)
    f.close()
    return Path(f.name)


def test_ac3_1_usfs_adapter_matches_old_fetcher():
    path = _usfs_file()
    try:
        old = usfs_fetch.fetch(_REGION.bbox, geojson_path=path)
        new = UsfsSource(geojson_path=path).fetch(_REGION)
        assert _norm(old) == _norm(new)
        assert new and new[0].source == "USFS"
    finally:
        path.unlink(missing_ok=True)


# ── AC-3.2 — USFS from_config: blank path fails loud, missing file degrades ────


def test_ac3_2_usfs_blank_path_raises():
    s = Settings.from_env({"ADVENTURE_USFS_GEOJSON": "   "})
    with pytest.raises(ValueError, match="ADVENTURE_USFS_GEOJSON"):
        UsfsSource.from_config(s)


def test_ac3_2_usfs_unset_path_uses_default_and_degrades(tmp_path, monkeypatch):
    # Unset path → from_config succeeds; a missing file degrades to [] (not raise).
    monkeypatch.chdir(tmp_path)  # default data/usfs/trails.geojson is absent here
    s = Settings.from_env({})
    src = UsfsSource.from_config(s)
    assert src.fetch(_REGION) == []


def test_ac3_2_usfs_configured_path_used(tmp_path):
    path = _usfs_file()
    try:
        s = Settings.from_env({"ADVENTURE_USFS_GEOJSON": str(path)})
        src = UsfsSource.from_config(s)
        assert src.fetch(_REGION)  # reads the configured file
    finally:
        path.unlink(missing_ok=True)


# ── AC-3.3 — fetch degrades to [] (never raises past the adapter) ─────────────


def test_ac3_3_osm_degrades_on_http_error():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    assert OsmSource(client=client).fetch(_REGION) == []


def test_ac3_3_nps_degrades_on_http_error():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    assert NpsSource(client=client).fetch(_REGION) == []


def test_ac3_3_usfs_degrades_on_missing_file():
    assert UsfsSource(geojson_path=Path("definitely-not-here.geojson")).fetch(_REGION) == []


def test_ac3_3_osm_degrades_on_malformed_200_body():
    # A 200 with a non-JSON body would raise inside the transport's r.json(); the
    # adapter is the degrade boundary, so it still returns [] (never raises).
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"<<not json>>"))
    )
    assert OsmSource(client=client).fetch(_REGION) == []


# ── AC-5.1 / AC-5.4 — geometry sources leave enrich raising; EnrichmentFact ───


def test_ac5_1_geometry_enrich_raises():
    with pytest.raises(NotImplementedError):
        OsmSource().enrich(CanonicalNode(canonical_id="ct:x", name="x"))


def test_ac5_4_enrichment_fact_carries_provenance():
    fact = EnrichmentFact(
        source="3dep", attribute="gain_ft", value=1200.0, recorded_resolution="10m"
    )
    assert fact.source == "3dep"
    assert fact.attribute == "gain_ft"
    assert fact.value == 1200.0
    assert fact.recorded_resolution == "10m"
