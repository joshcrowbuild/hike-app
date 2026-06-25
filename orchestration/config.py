"""Runtime configuration loaded from the environment.

Secrets live only in `.env` (git-ignored) or a real secrets store — never in the
repo (CLAUDE.md rule #10). This module reads them; it holds no secret defaults.
See `.env.example` for the shape.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class TierConfig:
    """A capability tier's default provider + model, plus the local model to fall
    back to when sensitivity routing forces on-device inference."""

    provider: str  # "local" | "anthropic"
    model: str  # default model id for this tier (provider-specific)
    local_model: str  # model id used when forced local for the private overlay


@dataclass(frozen=True)
class Settings:
    """Resolved runtime settings. Build with `Settings.from_env()`."""

    # Graph (local Neo4j Community for dev). Secrets carry repr=False so the
    # dataclass auto-repr / tracebacks never dump credentials (rule #10).
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str = field(repr=False)

    # Model providers (provider-agnostic, local-first — Decision Log §29).
    local_openai_base_url: str
    anthropic_api_key: str | None = field(repr=False)
    tiers: Mapping[str, TierConfig] = field()

    # Geographic scope (Stage 3: polygon-bounded region).
    region: str = field()

    # Live-data source credentials (Stage 1 catalog; most free/keyless).
    nws_user_agent: str | None = None
    airnow_api_key: str | None = field(repr=False, default=None)
    firms_map_key: str | None = field(repr=False, default=None)
    ridb_api_key: str | None = field(repr=False, default=None)

    # Device-integration seam (Epic 004). Comma-separated vendor names from
    # ADVENTURE_WATCH_ADAPTERS; empty = no devices, pipeline still runs (rule #6).
    # Per-vendor secrets are read here but never defaulted to a real value (#10).
    watch_adapters: tuple[str, ...] = ()
    garmin_email: str | None = None
    garmin_password: str | None = field(repr=False, default=None)
    coros_client_id: str | None = None
    coros_client_secret: str | None = field(repr=False, default=None)

    # CorpusSource seam (Epic 012). Comma-separated source names from
    # ADVENTURE_CORPUS_SOURCES; defaults to the three Stage-3 sources so today's
    # behavior is preserved when the env var is absent. The registry resolves each
    # name to an adapter via its `from_config` (ingestion/sources/registry.py).
    # `usfs_geojson_path` is the one source-specific path a corpus adapter reads
    # from config (rule #10); None = the USFS transport's own default path.
    corpus_sources: tuple[str, ...] = ("osm", "nps", "usfs")
    usfs_geojson_path: str | None = None

    @staticmethod
    def from_env(env: Mapping[str, str] | None = None) -> "Settings":
        e = os.environ if env is None else env

        def tier(name: str) -> TierConfig:
            up = name.upper()
            return TierConfig(
                provider=e.get(f"ADVENTURE_PROVIDER_{up}", "local"),  # local-first default
                model=e.get(f"ADVENTURE_MODEL_{up}", ""),
                local_model=e.get(f"ADVENTURE_LOCAL_MODEL_{up}", ""),
            )

        watch_raw = e.get("ADVENTURE_WATCH_ADAPTERS", "")
        watch_adapters = tuple(s.strip() for s in watch_raw.split(",") if s.strip())

        # Default to the three Stage-3 sources when the env var is absent; reuse
        # the ADVENTURE_WATCH_ADAPTERS comma-split idiom (AC-2.4).
        corpus_raw = e.get("ADVENTURE_CORPUS_SOURCES", "osm,nps,usfs")
        corpus_sources = tuple(s.strip() for s in corpus_raw.split(",") if s.strip())

        return Settings(
            neo4j_uri=e.get("NEO4J_URI", "bolt://localhost:7687"),
            neo4j_user=e.get("NEO4J_USER", "neo4j"),
            neo4j_password=e.get("NEO4J_PASSWORD", ""),
            local_openai_base_url=e.get("LOCAL_OPENAI_BASE_URL", "http://localhost:11434/v1"),
            anthropic_api_key=e.get("ANTHROPIC_API_KEY") or None,
            tiers={"mechanical": tier("mechanical"), "judgment": tier("judgment")},
            region=e.get("ADVENTURE_REGION", "shenandoah-gwj"),
            nws_user_agent=e.get("NWS_USER_AGENT") or None,
            airnow_api_key=e.get("AIRNOW_API_KEY") or None,
            firms_map_key=e.get("FIRMS_MAP_KEY") or None,
            ridb_api_key=e.get("RIDB_API_KEY") or None,
            watch_adapters=watch_adapters,
            garmin_email=e.get("GARMIN_EMAIL") or None,
            garmin_password=e.get("GARMIN_PASSWORD") or None,
            coros_client_id=e.get("COROS_CLIENT_ID") or None,
            coros_client_secret=e.get("COROS_CLIENT_SECRET") or None,
            corpus_sources=corpus_sources,
            # Kept raw (no `or None`): an explicitly-blank value must reach
            # UsfsSource.from_config so it can fail loud (AC-3.2); unset → None →
            # the USFS transport's default path.
            usfs_geojson_path=e.get("ADVENTURE_USFS_GEOJSON"),
        )
