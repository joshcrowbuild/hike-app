"""Settings configuration tests — defaults, overrides, and secret handling."""

from __future__ import annotations

from orchestration.config import Settings, TierConfig


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
