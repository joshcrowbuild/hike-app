"""Settings configuration tests — defaults, overrides, and secret handling."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from orchestration.config import RoleOverride, Settings, TierConfig, default_dem_path


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


# ── Epic 040 operator-lever seam: per-role overrides on top of tier config ──


def test_settings_role_overrides_default_to_unset() -> None:
    s = Settings.from_env({})
    assert set(s.role_overrides) == {"extract", "normalize", "judge", "curate"}
    for role in s.role_overrides:
        assert s.role_overrides[role] == RoleOverride(provider=None, model=None, local_model=None)


def test_settings_role_overrides_env_parses_per_role() -> None:
    s = Settings.from_env(
        {
            "ADVENTURE_MODEL_CURATE": "fast-model",
            "ADVENTURE_PROVIDER_CURATE": "anthropic",
            "ADVENTURE_LOCAL_MODEL_CURATE": "local-fallback",
            "ADVENTURE_MODEL_JUDGE": "judge-model",
        }
    )
    assert s.role_overrides["curate"] == RoleOverride(
        provider="anthropic", model="fast-model", local_model="local-fallback"
    )
    assert s.role_overrides["judge"] == RoleOverride(
        provider=None, model="judge-model", local_model=None
    )
    # Unrelated roles stay fully unset — no cross-role leakage at the parse layer.
    assert s.role_overrides["extract"] == RoleOverride()
    assert s.role_overrides["normalize"] == RoleOverride()
    # tiers dict is unaffected by role overrides (still the existing SSOT for tier defaults).
    assert s.tiers["judgment"] == TierConfig(provider="local", model="", local_model="")


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


# ── Epic 043 — managed auth config (fail-closed by default) ──


def test_settings_supabase_auth_absent_by_default() -> None:
    s = Settings.from_env({})
    # No JWKS URL wired → managed auth fails closed; anonymous browsing needs no env.
    assert s.supabase_jwks_url is None
    assert s.supabase_issuer is None
    assert s.allow_dev_viewer_secret is False


def test_settings_supabase_jwks_derived_from_supabase_url() -> None:
    s = Settings.from_env({"SUPABASE_URL": "https://proj.supabase.co/"})
    assert s.supabase_jwks_url == "https://proj.supabase.co/auth/v1/.well-known/jwks.json"
    assert s.supabase_issuer == "https://proj.supabase.co/auth/v1"


def test_settings_supabase_jwks_explicit_override_wins() -> None:
    s = Settings.from_env(
        {
            "SUPABASE_URL": "https://proj.supabase.co",
            "ADVENTURE_SUPABASE_JWKS_URL": "https://cdn.example/jwks.json",
        }
    )
    assert s.supabase_jwks_url == "https://cdn.example/jwks.json"


def test_settings_allow_dev_viewer_secret_gate_parsing() -> None:
    for on in ("1", "true", "TRUE", "yes", "on"):
        assert Settings.from_env({"ADVENTURE_ALLOW_DEV_VIEWER_SECRET": on}).allow_dev_viewer_secret
    for off in ("", "0", "false", "no", "off", "nonsense"):
        assert not Settings.from_env(
            {"ADVENTURE_ALLOW_DEV_VIEWER_SECRET": off}
        ).allow_dev_viewer_secret


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


# ── 2026-07-12 review: numeric env knobs must be finite — inf/NaN/negative → default ──
#
# `float()` happily parses "inf"/"nan", and any typo crashed from_env outright; each
# knob must instead degrade to its documented default (rule #6 at the config layer).

_FLOAT_KNOBS = [
    # (env var, settings attr, documented default, zero is a valid kill switch)
    ("DRIVE_SPEED_KMH", "drive_speed_kmh", 60.0, False),
    ("ADVENTURE_3DEP_RESOLUTION_M", "elev_resolution_m", 20.0, False),
    # zero_ok: a 0 deadline means "report a down dependency immediately" (the warmup
    # tests exercise it) — an established valid value, not a typo.
    ("ADVENTURE_WARMUP_DEADLINE_S", "warmup_deadline_s", 30.0, True),
    ("ADVENTURE_ANON_FEED_CACHE_TTL_S", "feed_cache_ttl_s", 300.0, True),
    ("ADVENTURE_FEED_WARM_INTERVAL_S", "feed_warm_interval_s", 240.0, True),
]


def test_settings_float_knobs_fall_back_on_nonfinite_or_negative() -> None:
    for env_var, attr, default, _ in _FLOAT_KNOBS:
        for bad in ("inf", "-inf", "nan", "-5", "not-a-number"):
            s = Settings.from_env({env_var: bad})
            assert getattr(s, attr) == default, f"{env_var}={bad!r}"


def test_settings_float_knobs_zero_only_valid_for_kill_switches() -> None:
    for env_var, attr, default, zero_ok in _FLOAT_KNOBS:
        s = Settings.from_env({env_var: "0"})
        expected = 0.0 if zero_ok else default
        assert getattr(s, attr) == expected, f"{env_var}=0"


def test_settings_float_knobs_valid_overrides_unchanged() -> None:
    for env_var, attr, _, _ in _FLOAT_KNOBS:
        s = Settings.from_env({env_var: "42.5"})
        assert getattr(s, attr) == 42.5, f"{env_var}=42.5"
