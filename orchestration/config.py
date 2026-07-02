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

    # Edge auth (Epic 014 S3). Until the Stage-8 auth/identity system exists, a
    # non-anonymous viewer_id at the API edge must present this shared dev secret.
    # Absent by default (repr=False) so the only out-of-the-box path is the open
    # anonymous world; a misconfigured deploy fails closed, never silently trusting
    # a client-supplied identity (Rule #5 / decision-log §13).
    dev_viewer_secret: str | None = field(repr=False, default=None)

    # Browser CORS allow-list for the hosted API edge (deploy contract). Comma-separated
    # EXACT origins from ADVENTURE_CORS_ALLOW_ORIGINS (e.g. the Vercel frontend). Empty by
    # default = default-deny: no browser origin is allowed and the wildcard is never used,
    # so a misconfigured deploy fails closed rather than exposing the API to any site.
    cors_allow_origins: tuple[str, ...] = ()

    # Live-data source credentials (Stage 1 catalog; most free/keyless).
    nws_user_agent: str | None = None
    airnow_api_key: str | None = field(repr=False, default=None)
    firms_map_key: str | None = field(repr=False, default=None)
    ridb_api_key: str | None = field(repr=False, default=None)

    # LiveAdapter seam (Epic 013). Comma-separated adapter names from
    # ADVENTURE_LIVE_ADAPTERS; position sets primary vs. fallback within a kind.
    # Empty = no live probes (the engine still runs — source-or-silence). live_region
    # is the country/coverage code adapters are gated on (distinct from `region`, the
    # geographic ingest scope); defaults to the pilot's US.
    live_adapters: tuple[str, ...] = ()
    live_region: str = "US"

    # Valhalla drive-time (Epic 013 S5 / Epic 005). Origin-relative, never persisted
    # (Rule #3). Absent base URL = no drive-time line, no pruning (parity with the
    # missing-key probe pattern). drive_speed_kmh sizes the radius→time-budget default.
    valhalla_base_url: str | None = None
    drive_speed_kmh: float = 60.0
    # Commons fork (Epic 010). Secret salt for the one-way writer_hash (HMAC) that
    # makes a contributor's observations findable for revocation without a back-
    # edge to them (Stage 9 §2.3). Never in the repo (#10); absent → fork skipped.
    commons_writer_salt: str | None = field(repr=False, default=None)

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
    # USGS-3DEP elevation enrichment (Epic 017). `dem_path` is the local 3DEP DEM
    # raster the adapter samples (rule #10: from config, never the repo); absent →
    # the `usgs-3dep` source fails loud in `from_config` (a misconfiguration, per
    # the corpus seam). `elev_resolution_m` is the along-route sampling spacing.
    dem_path: str | None = None
    elev_resolution_m: float = 20.0

    # API startup warm-up budget (seconds) for one round over /plan's dependency
    # stack — chiefly how long the graph connectivity check may retry before the
    # round reports failure. /health stays 503 until a round succeeds, so this is
    # the ceiling on how long a deploy waits for a slow-but-alive Aura, not a hang:
    # past it the failure is surfaced in /health instead.
    warmup_deadline_s: float = 30.0

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

        live_raw = e.get("ADVENTURE_LIVE_ADAPTERS", "")
        live_adapters = tuple(s.strip() for s in live_raw.split(",") if s.strip())
        # Default to the three Stage-3 sources when the env var is absent; reuse
        # the ADVENTURE_WATCH_ADAPTERS comma-split idiom (AC-2.4).
        corpus_raw = e.get("ADVENTURE_CORPUS_SOURCES", "osm,nps,usfs")
        corpus_sources = tuple(s.strip() for s in corpus_raw.split(",") if s.strip())

        cors_raw = e.get("ADVENTURE_CORS_ALLOW_ORIGINS", "")
        cors_allow_origins = tuple(o.strip() for o in cors_raw.split(",") if o.strip())

        return Settings(
            neo4j_uri=e.get("NEO4J_URI", "bolt://localhost:7687"),
            neo4j_user=e.get("NEO4J_USER", "neo4j"),
            neo4j_password=e.get("NEO4J_PASSWORD", ""),
            local_openai_base_url=e.get("LOCAL_OPENAI_BASE_URL", "http://localhost:11434/v1"),
            anthropic_api_key=e.get("ANTHROPIC_API_KEY") or None,
            tiers={"mechanical": tier("mechanical"), "judgment": tier("judgment")},
            region=e.get("ADVENTURE_REGION", "shenandoah-gwj"),
            dev_viewer_secret=e.get("ADVENTURE_DEV_VIEWER_SECRET") or None,
            cors_allow_origins=cors_allow_origins,
            nws_user_agent=e.get("NWS_USER_AGENT") or None,
            airnow_api_key=e.get("AIRNOW_API_KEY") or None,
            firms_map_key=e.get("FIRMS_MAP_KEY") or None,
            ridb_api_key=e.get("RIDB_API_KEY") or None,
            live_adapters=live_adapters,
            live_region=e.get("ADVENTURE_LIVE_REGION", "US"),
            valhalla_base_url=e.get("VALHALLA_BASE_URL") or None,
            drive_speed_kmh=float(e.get("DRIVE_SPEED_KMH", "60.0")),
            commons_writer_salt=e.get("ADVENTURE_COMMONS_WRITER_SALT") or None,
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
            dem_path=e.get("ADVENTURE_3DEP_DEM") or None,
            elev_resolution_m=float(e.get("ADVENTURE_3DEP_RESOLUTION_M", "20.0")),
            warmup_deadline_s=float(e.get("ADVENTURE_WARMUP_DEADLINE_S", "30.0")),
        )
