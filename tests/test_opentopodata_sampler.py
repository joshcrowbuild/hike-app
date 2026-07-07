"""Tests for the OpenTopoData network `ElevationSampler` (Epic 033).

All HTTP is mocked via `httpx.MockTransport` — no network, no `@pytest.mark.neo4j`,
no DB (AC-3.3). Two layers, matching `test_usgs_3dep.py`'s style: the sampler's
request/response contract in isolation (S1), then selection + disclosure through
`UsgsThreeDEPSource.from_config`/`enrich` (S2), then a full profile end-to-end
through a MockTransport ramp (S3).
"""

from __future__ import annotations

import httpx

from graph.load import load_enrichment_facts
from ingestion.elevation import ElevationSampler, build_profile_from_wkt
from ingestion.sources.base import CanonicalNode
from ingestion.sources.opentopodata import OpenTopoDataSampler
from ingestion.sources.usgs_3dep import ELEV_SOURCE, RasterioDEMSampler, UsgsThreeDEPSource
from orchestration.config import Settings

_WKT = "LINESTRING(-78.30 38.50, -78.20 38.50)"  # ~8.7 km west→east at 38.5°N


def _ok_response(elevation: float | None, dataset: str = "ned10m") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "results": [
                {"elevation": elevation, "location": {"lat": 0, "lng": 0}, "dataset": dataset}
            ],
            "status": "OK",
        },
    )


def _ramp_handler(request: httpx.Request) -> httpx.Response:
    lat_str, lon_str = request.url.params["locations"].split(",")
    lon = float(lon_str)
    return _ok_response((lon + 78.30) * 10_000.0)


def _null_handler(request: httpx.Request) -> httpx.Response:
    return _ok_response(None)


# ── AC-1.1: structural Protocol compatibility ─────────────────────────────────


def test_satisfies_elevation_sampler_protocol():
    sampler: ElevationSampler = OpenTopoDataSampler(base_url="http://host:5000")
    assert sampler is not None


# ── AC-1.2: exact request path + query, lat,lon order, trailing-slash safety ──


def test_sample_issues_expected_request():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _ok_response(1611.0)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    sampler = OpenTopoDataSampler(base_url="http://host:5000", dataset="ned10m", client=client)
    result = sampler.sample(-105.5, 39.7)  # lon, lat

    assert result == 1611.0
    assert len(captured) == 1
    req = captured[0]
    assert req.method == "GET"
    assert req.url.path == "/v1/ned10m"
    assert req.url.params["locations"] == "39.7,-105.5"  # lat,lon order


def test_sample_normalizes_trailing_slash_base_url():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _ok_response(1611.0)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    sampler = OpenTopoDataSampler(base_url="http://host:5000/", dataset="ned10m", client=client)
    sampler.sample(-105.5, 39.7)

    assert captured[0].url.path == "/v1/ned10m"
    assert "//v1" not in str(captured[0].url)


# ── AC-1.3: success path ───────────────────────────────────────────────────────


def test_sample_returns_float_elevation_on_success():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: _ok_response(1611.0)))
    sampler = OpenTopoDataSampler(base_url="http://host:5000", client=client)
    assert sampler.sample(-105.5, 39.7) == 1611.0


# ── AC-1.4: source-or-silence — every miss returns None, never a guess ────────


def test_sample_returns_none_on_null_elevation():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: _ok_response(None)))
    sampler = OpenTopoDataSampler(base_url="http://host:5000", client=client)
    assert sampler.sample(-105.5, 39.7) is None


def test_sample_returns_none_on_empty_results():
    body = {"results": [], "status": "OK"}
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body)))
    sampler = OpenTopoDataSampler(base_url="http://host:5000", client=client)
    assert sampler.sample(-105.5, 39.7) is None


def test_sample_returns_none_on_non_ok_status():
    body = {"results": [{"elevation": 1611.0}], "status": "INVALID_REQUEST"}
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body)))
    sampler = OpenTopoDataSampler(base_url="http://host:5000", client=client)
    assert sampler.sample(-105.5, 39.7) is None


def test_sample_returns_none_on_non_200():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    sampler = OpenTopoDataSampler(base_url="http://host:5000", client=client)
    assert sampler.sample(-105.5, 39.7) is None


def test_sample_returns_none_on_malformed_body():
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text="not json"))
    )
    sampler = OpenTopoDataSampler(base_url="http://host:5000", client=client)
    assert sampler.sample(-105.5, 39.7) is None


def test_sample_returns_none_on_valid_json_wrong_shape():
    # A 200 with valid JSON that isn't the expected {"results": [...], "status": ...}
    # dict shape (e.g. a misrouted base_url hitting an unrelated JSON API) must
    # degrade to None, not raise past sample() (source-or-silence, AC-1.4).
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=["unexpected"]))
    )
    sampler = OpenTopoDataSampler(base_url="http://host:5000", client=client)
    assert sampler.sample(-105.5, 39.7) is None


def test_sample_returns_none_on_raised_exception():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("simulated timeout")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    sampler = OpenTopoDataSampler(base_url="http://host:5000", client=client)
    assert sampler.sample(-105.5, 39.7) is None


# ── AC-1.5: single reused client; close() only closes an owned client ────────


def test_sample_reuses_one_client_across_calls():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _ok_response(100.0)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    sampler = OpenTopoDataSampler(base_url="http://host:5000", client=client)
    sampler.sample(-105.5, 39.7)
    sampler.sample(-105.6, 39.8)
    assert calls == 2
    assert sampler._client is client


def test_close_does_not_close_an_injected_client():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: _ok_response(1.0)))
    sampler = OpenTopoDataSampler(base_url="http://host:5000", client=client)
    sampler.close()
    assert client.is_closed is False


def test_close_closes_an_owned_client():
    sampler = OpenTopoDataSampler(base_url="http://host:5000")
    owned = sampler._ensure_client()
    sampler.close()
    assert owned.is_closed is True


# ── AC-1.6: disclosure ─────────────────────────────────────────────────────────


def test_source_discloses_dataset():
    sampler = OpenTopoDataSampler(base_url="http://host:5000", dataset="ned10m")
    assert sampler.source == "opentopodata:ned10m"


# ── S2: config (AC-2.1) ────────────────────────────────────────────────────────


def test_settings_from_env_reads_opentopodata_config():
    s = Settings.from_env(
        {
            "ADVENTURE_OPENTOPODATA_URL": "http://host:5000",
            "ADVENTURE_OPENTOPODATA_DATASET": "ned10m",
        }
    )
    assert s.opentopodata_url == "http://host:5000"
    assert s.opentopodata_dataset == "ned10m"


def test_settings_from_env_defaults_opentopodata_config():
    s = Settings.from_env({})
    assert s.opentopodata_url is None
    assert s.opentopodata_dataset == "ned10m"


# ── S2: selection precedence (AC-2.2 / 2.3 / 2.4) ─────────────────────────────


def test_local_raster_wins_when_present_even_with_url_set(tmp_path):
    dem = tmp_path / "dem.tif"
    dem.write_bytes(b"not a real raster, just needs to exist")
    s = Settings.from_env(
        {"ADVENTURE_3DEP_DEM": str(dem), "ADVENTURE_OPENTOPODATA_URL": "http://host:5000"}
    )
    src = UsgsThreeDEPSource.from_config(s)
    assert isinstance(src._sampler, RasterioDEMSampler)


def test_network_fallback_selected_when_dem_path_is_none():
    s = Settings.from_env({"ADVENTURE_OPENTOPODATA_URL": "http://host:5000"})
    src = UsgsThreeDEPSource.from_config(s)
    assert isinstance(src._sampler, OpenTopoDataSampler)


def test_network_fallback_selected_when_dem_path_does_not_exist(tmp_path):
    s = Settings.from_env(
        {
            "ADVENTURE_3DEP_DEM": str(tmp_path / "missing.tif"),
            "ADVENTURE_OPENTOPODATA_URL": "http://host:5000",
        }
    )
    src = UsgsThreeDEPSource.from_config(s)
    assert isinstance(src._sampler, OpenTopoDataSampler)


def test_no_sampler_when_neither_raster_nor_url_configured():
    src = UsgsThreeDEPSource.from_config(Settings.from_env({}))
    assert src._sampler is None
    assert src.enrich(CanonicalNode("ct:1", "X", geom_wkt=_WKT)) == []


# ── S2: disclosure through to facts (AC-2.5) ──────────────────────────────────


def test_enrich_discloses_opentopodata_source():
    client = httpx.Client(transport=httpx.MockTransport(_ramp_handler))
    sampler = OpenTopoDataSampler(base_url="http://host:5000", dataset="ned10m", client=client)
    src = UsgsThreeDEPSource(sampler=sampler, resolution_m=50.0, elev_source=sampler.source)

    facts = src.enrich(CanonicalNode(canonical_id="ct:1", name="X", geom_wkt=_WKT))
    by = {f.attribute: f.value for f in facts}

    assert by["elev_source"] == "opentopodata:ned10m"
    assert by["elev_source"] != ELEV_SOURCE
    assert by["total_gain_m"] > 900.0

    n = load_enrichment_facts(lambda c, p: None, facts)
    assert n == 1


def test_from_config_threads_opentopodata_source_into_facts():
    client = httpx.Client(transport=httpx.MockTransport(_ramp_handler))
    s = Settings.from_env({"ADVENTURE_OPENTOPODATA_URL": "http://host:5000"})
    src = UsgsThreeDEPSource.from_config(s)
    src._sampler._client = client  # swap the lazily-built client for the mocked one

    facts = src.enrich(CanonicalNode(canonical_id="ct:1", name="X", geom_wkt=_WKT))
    by = {f.attribute: f.value for f in facts}
    assert by["elev_source"] == "opentopodata:ned10m"
    assert by["elev_version"] == "ned10m"


# ── S3: end-to-end profile through the network sampler (AC-3.1 / AC-3.2) ─────


def test_profile_end_to_end_through_mocked_opentopodata():
    client = httpx.Client(transport=httpx.MockTransport(_ramp_handler))
    sampler = OpenTopoDataSampler(base_url="http://host:5000", dataset="ned10m", client=client)

    profile = build_profile_from_wkt(_WKT, sampler, source="opentopodata:ned10m")

    assert profile is not None
    assert profile.total_gain_m > 0
    assert profile.source == "opentopodata:ned10m"


def test_profile_is_none_when_out_of_coverage():
    client = httpx.Client(transport=httpx.MockTransport(_null_handler))
    sampler = OpenTopoDataSampler(base_url="http://host:5000", dataset="ned10m", client=client)

    assert build_profile_from_wkt(_WKT, sampler, source="opentopodata:ned10m") is None
