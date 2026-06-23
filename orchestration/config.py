"""Runtime configuration loaded from the environment.

Secrets live only in `.env` (git-ignored) or a real secrets store — never in the
repo (CLAUDE.md rule #10). This module reads them; it holds no secret defaults.
See `.env.example` for the shape.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
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

    # Graph (local Neo4j Community for dev).
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str

    # Model providers (provider-agnostic, local-first — Decision Log §29).
    local_openai_base_url: str
    anthropic_api_key: str | None
    tiers: Mapping[str, TierConfig]

    # Geographic scope (Stage 3: polygon-bounded region).
    region: str

    # Live-data source credentials (Stage 1 catalog; most free/keyless).
    nws_user_agent: str | None = None
    airnow_api_key: str | None = None
    firms_map_key: str | None = None
    ridb_api_key: str | None = None

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
        )
