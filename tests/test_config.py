"""Settings configuration tests — defaults, overrides, and secret handling."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from orchestration.config import Settings, TierConfig, default_dem_path


def test_settings_env_defaults() -> None:
    s = Settings.from_env({})
    assert s.neo4j_uri == "bolt://localhost:7687"
    assert s.neo4j_user == "neo4j"
    assert s.neo4j_password == ""
    assert s.local_openai_base_url == "http://localhost:11434/v1"
    assert s.anthropic_api_key is None
    assert s.region == "shenandoah-gwj"
    assert s.nws_user_agent is None
    assert s.watch_adapters == ()
    assert s.garmin_email is None


def test_settings_env_overrides() -> None:
    s = Settings.from_env(
        {
            "NEO4J_URI": "bolt://db:7687",
            "NEO4J_USER": "admin",
            "NEO4J_PASSWORD": "secret",
            "LOCAL_OPENAI_BASE_URL": "http://local:1234/v1",
            "ANTHROPIC_API_KEY": "key-123",
            "ADVENTURE_REGION": "olympic",
            "NWS_USER_AGENT": "test-agent",
            "ADVENTURE_COMMONS_WRITER_SALT": "salt",
        }
    )
    assert s.neo4j_uri == "bolt://db:7687"
    assert s.neo4j_user == "admin"
    assert s.neo4j_password == "secret"
    assert s.local_openai_base_url == "http://local:1234/v1"
    assert s.anthropic_api_key == "key-123"
    assert s.region == "olympic"
    assert s.nws_user_agent == "test-agent"
    assert s.commons_writer_salt == "salt"


def test_settings_tiers_default_to_local() -> None:
    s = Settings.from_env({})
    assert set(s.tiers) == {"mechanical", "judgment"}
    assert s.tiers["mechanical"] == TierConfig(provider="local", model="", local_model="")
    assert s.tiers["judgment"] == TierConfig(provider="local", model="", local_model="")


def test_settings_tiers_env_override() -> None:
    s = Settings.from_env(
        {
            "ADVENTURE_PROVIDER_MECHANICAL": "anthropic",
            "ADVENTURE_MODEL_MECHANICAL": "claude-sonnet-4",
            "ADVENTURE_LOCAL_MODEL_MECHANICAL": "qwen2.5",
            "ADVENTURE_PROVIDER_JUDGMENT": "anthropic",
            "ADVENTURE_MODEL_JUDGMENT": "claude-opus-4",
            "ADVENTURE_LOCAL_MODEL_JUDGMENT": "llama3.3",
        }
    )
    assert s.tiers["mechanical"] == TierConfig(
        provider="anthropic", model="claude-sonnet-4", local_model="qwen2.5"
    )
    assert s.tiers["judgment"] == TierConfig(
        provider="anthropic", model="claude-opus-4", local_model="llama3.3"
    )


def test_settings_secrets_are_hidden_from_repr() -> None:
    s = Settings.from_env(
        {
            "NEO4J_PASSWORD": "should-not-appear",
            "ANTHROPIC_API_KEY": "also-hidden",
            "AIRNOW_API_KEY": "air-key",
        }
    )
    r = repr(s)
    assert "should-not-appear" not in r
    assert "also-hidden" not in r
    assert "air-key" not in r
    # repr=True fields do appear; repr=False fields (and their names) are omitted.
    assert "neo4j_uri" in r


def test_settings_optional_api_keys_present_when_set() -> None:
    s = Settings.from_env(
        {
            "AIRNOW_API_KEY": "air",
            "FIRMS_MAP_KEY": "firms",
            "RIDB_API_KEY": "ridb",
        }
    )
    assert s.airnow_api_key == "air"
    assert s.firms_map_key == "firms"
    assert s.ridb_api_key == "ridb"


def test_settings_watch_adapters_parsing() -> None:
    s = Settings.from_env({"ADVENTURE_WATCH_ADAPTERS": "garmin, coros, "})
    assert s.watch_adapters == ("garmin", "coros")
    assert s.garmin_email is None
    assert s.coros_client_id is None


def test_settings_watch_adapters_empty_means_none() -> None:
    s = Settings.from_env({"ADVENTURE_WATCH_ADAPTERS": "", "GARMIN_EMAIL": "a@b.com"})
    assert s.watch_adapters == ()
    assert s.garmin_email == "a@b.com"


def test_settings_env_var_is_not_mutated() -> None:
    env = {"NEO4J_URI": "bolt://x:7687"}
    Settings.from_env(env)
    assert env == {"NEO4J_URI": "bolt://x:7687"}


# ── DEM path resolution (elevation durability) ──────────────────────────────


def test_default_dem_path_missing_is_none() -> None:
    # No fetched DEM → None (3DEP degrades to a no-op, never an error — rule #6).
    assert default_dem_path("no-such-region-xyz") is None


def test_default_dem_path_present_when_file_exists(tmp_path: Any, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    dem = Path("data/dem/olympic.tif")
    dem.parent.mkdir(parents=True)
    dem.write_bytes(b"raster")
    assert default_dem_path("olympic") == "data/dem/olympic.tif"


def test_settings_dem_path_env_override_wins(tmp_path: Any, monkeypatch: Any) -> None:
    # An explicit ADVENTURE_3DEP_DEM overrides the conventional path.
    monkeypatch.chdir(tmp_path)
    Path("data/dem").mkdir(parents=True)
    Path("data/dem/olympic.tif").write_bytes(b"raster")
    s = Settings.from_env({"ADVENTURE_REGION": "olympic", "ADVENTURE_3DEP_DEM": "/elsewhere/x.tif"})
    assert s.dem_path == "/elsewhere/x.tif"


def test_settings_dem_path_falls_back_to_convention(tmp_path: Any, monkeypatch: Any) -> None:
    # Unset env + a fetched DEM at the conventional path → picked up automatically, so a
    # standard ingest re-applies 3DEP without any env var (the durability fix).
    monkeypatch.chdir(tmp_path)
    Path("data/dem").mkdir(parents=True)
    Path("data/dem/olympic.tif").write_bytes(b"raster")
    s = Settings.from_env({"ADVENTURE_REGION": "olympic"})
    assert s.dem_path == "data/dem/olympic.tif"


def test_settings_dem_path_none_when_neither_present(tmp_path: Any, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)  # no data/dem here
    s = Settings.from_env({"ADVENTURE_REGION": "olympic"})
    assert s.dem_path is None


def test_settings_cors_origins_default_deny() -> None:
    # Absent env var → empty allow-list → default-deny (no wildcard, fail closed).
    assert Settings.from_env({}).cors_allow_origins == ()


def test_settings_cors_origins_parsed_from_env() -> None:
    s = Settings.from_env(
        {"ADVENTURE_CORS_ALLOW_ORIGINS": "https://hike-app.vercel.app, https://staging.test , "}
    )
    # Comma-split, trimmed, blanks dropped — same idiom as the adapter lists.
    assert s.cors_allow_origins == ("https://hike-app.vercel.app", "https://staging.test")


def test_settings_live_probe_max_workers_default_and_override() -> None:
    # Default caps the live-fan-out concurrency (verify_batch) even when unset.
    assert Settings.from_env({}).live_probe_max_workers == 8
    s = Settings.from_env({"ADVENTURE_LIVE_PROBE_MAX_WORKERS": "4"})
    assert s.live_probe_max_workers == 4


# ── Epic 036 AC-3.2/AC-3.3 — osm_pbf_path: additive, blank survives raw ────────


def test_osm_pbf_path_none_when_unset() -> None:
    assert Settings.from_env({}).osm_pbf_path is None


def test_osm_pbf_path_read_from_settings() -> None:
    s = Settings.from_env({"ADVENTURE_OSM_PBF": "/data/virginia-latest.osm.pbf"})
    assert s.osm_pbf_path == "/data/virginia-latest.osm.pbf"


def test_osm_pbf_path_blank_survives_raw_for_from_config_to_reject() -> None:
    # Kept raw (no `or None`) so OsmPbfSource.from_config can fail loud on an
    # explicitly-blank value (SS-10), verbatim the usfs_geojson_path treatment.
    s = Settings.from_env({"ADVENTURE_OSM_PBF": ""})
    assert s.osm_pbf_path == ""


def test_corpus_sources_default_spine_is_still_osm() -> None:
    # AC-3.3: additive-default-not-flipped — "osm-pbf" is registered but the
    # default ADVENTURE_CORPUS_SOURCES tuple's geometry spine name is unchanged.
    s = Settings.from_env({})
    assert s.corpus_sources == ("osm", "nps", "usfs", "usgs-3dep")
    assert "osm-pbf" not in s.corpus_sources


# ── Epic 039 S2: engine-layer anonymous plan cache ──


def test_s2_ac10_feed_cache_settings_default() -> None:
    s = Settings.from_env({})
    assert s.feed_cache_ttl_s == 300.0
    assert s.feed_cache_max_entries == 512


def test_s2_ac10_feed_cache_settings_env_override() -> None:
    s = Settings.from_env(
        {
            "ADVENTURE_ANON_FEED_CACHE_TTL_S": "120",
            "ADVENTURE_ANON_FEED_CACHE_MAX_ENTRIES": "64",
        }
    )
    assert s.feed_cache_ttl_s == 120.0
    assert s.feed_cache_max_entries == 64


def test_s2_ac10_feed_cache_ttl_zero_disables() -> None:
    # 0 is the operator kill switch — engine.build_runtime reads this to leave
    # Runtime.feed_cache at None (a byte-identical no-op).
    s = Settings.from_env({"ADVENTURE_ANON_FEED_CACHE_TTL_S": "0"})
    assert s.feed_cache_ttl_s == 0.0


# ── Epic 039 B5: default-frame feed warmer cadence ──


def test_b5_feed_warm_interval_default_and_override() -> None:
    assert Settings.from_env({}).feed_warm_interval_s == 240.0
    s = Settings.from_env({"ADVENTURE_FEED_WARM_INTERVAL_S": "600"})
    assert s.feed_warm_interval_s == 600.0


def test_b5_feed_warm_interval_zero_disables() -> None:
    # 0 is the warmer's kill switch — FeedWarmer.start() then never spawns a thread.
    assert Settings.from_env({"ADVENTURE_FEED_WARM_INTERVAL_S": "0"}).feed_warm_interval_s == 0.0
