"""Runtime configuration loaded from the environment.

Secrets live only in `.env` (git-ignored) or a real secrets store — never in the
repo (CLAUDE.md rule #10). This module reads them; it holds no secret defaults.
See `.env.example` for the shape.
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Mapping

logger = logging.getLogger(__name__)

# Conventional per-region DEM location (Epic 017 durability). `scripts/fetch_dem.py`
# writes the fetched/merged raster here, and — when ADVENTURE_3DEP_DEM is unset — this
# is where `Settings.from_env` looks, so a standard ingest ALWAYS re-applies 3DEP once
# the region's DEM has been fetched, without needing the env var set. Under gitignored
# `data/`, so the raster is never committed (rule: never commit data/).
DEM_DIR = "data/dem"

# Conflation review-band artifacts (DQ follow-up). The pipeline writes matches that
# fell between auto-accept and no-match here as one JSONL file per region — a
# reviewable file, NEVER a graph node (CLAUDE.md rule #3: fast/derived data isn't
# persisted as structural graph state). Under gitignored `data/`, so it never commits.
REVIEW_BAND_DIR = "data/review"


def _finite_positive(name: str, raw: str, default: float, *, allow_zero: bool = False) -> float:
    """Parse an env-sourced float, falling back to `default` unless the value is finite
    and positive (2026-07-12 review). `float()` happily accepts "inf"/"nan", and a bare
    `float(...)` crashed the process on any typo — a config knob must degrade to its
    documented default with a warning, never boot with inf/NaN in a timeout/TTL/speed.
    `allow_zero=True` is for the kill-switch knobs (feed cache TTL / warm interval)
    where 0 is a documented, valid operator value."""
    try:
        value = float(raw)
    except ValueError:
        logger.warning("%s=%r is not a number; using default %s", name, raw, default)
        return default
    if not math.isfinite(value) or value < 0 or (value == 0 and not allow_zero):
        logger.warning(
            "%s=%r is not a finite %s number; using default %s",
            name,
            raw,
            "non-negative" if allow_zero else "positive",
            default,
        )
        return default
    return value


def default_dem_path(region: str) -> str | None:
    """The conventional DEM path for `region` (`data/dem/{region}.tif`) if it exists on
    disk, else None. Lets a fetched DEM be picked up automatically (no env var) while a
    missing one degrades to no-op elevation enrichment rather than an error (rule #6)."""
    path = Path(DEM_DIR) / f"{region}.tif"
    return str(path) if path.is_file() else None


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
    nps_api_key: str | None = field(repr=False, default=None)

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
    # Cap on concurrent (point, kind) probes in the Verifier's live fan-out
    # (`verify_batch` — latency follow-up to Epic 018 S6). Bounds how hard a single
    # `/plan` can hit a rate-limited third-party source regardless of k; tune down if
    # a source starts rate-limiting, up if the fan-out is still latency-bound.
    live_probe_max_workers: int = 8
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
    # ADVENTURE_CORPUS_SOURCES; defaults to four sources so a re-ingest always
    # re-applies elevation enrichment (finding: elevation was silently wiped when
    # a re-ingest ran without `usgs-3dep` in the list — the enrichment source must
    # be a default member, not opt-in, so no re-ingest can "forget" it). The
    # registry resolves each name to an adapter via its `from_config`
    # (ingestion/sources/registry.py). `usfs_geojson_path` is the one source-
    # specific path a corpus adapter reads from config (rule #10); None = the
    # USFS transport's own default path.
    corpus_sources: tuple[str, ...] = ("osm", "nps", "usfs", "usgs-3dep")
    usfs_geojson_path: str | None = None
    # Deterministic OSM-PBF spine (Epic 036, additive — NOT in the default tuple
    # above; "osm" (Overpass) stays the default spine this sprint). The local
    # `.osm.pbf` path a `osm-pbf`-named source reads, from ADVENTURE_OSM_PBF; None
    # = the transport's own default path (data/osm/region.osm.pbf).
    osm_pbf_path: str | None = None
    # USGS-3DEP elevation enrichment (Epic 017). `dem_path` is the local 3DEP DEM
    # raster the adapter samples (rule #10: from config, never the repo). A DEM is
    # per-region (only `shenandoah-gwj` has one downloaded as of this writing —
    # Richmond/OBX need theirs before either will ever carry elevation); absent →
    # `usgs-3dep.from_config` degrades to a no-op source (log + skip) rather than
    # failing loud, since it's now a default corpus source and must be safe to
    # enable in every region (rule #6). `elev_resolution_m` is the along-route
    # sampling spacing.
    dem_path: str | None = None
    elev_resolution_m: float = 20.0
    # OpenTopoData fallback transport (Epic 033 — degrade-and-disclose when no local
    # DEM raster/rasterio is available, e.g. Render). Selected by `usgs_3dep.from_config`
    # only when `dem_path` is absent (local raster stays primary — never overrides it).
    # Self-hosted OpenTopoData Docker is the supported ingest path; the public
    # `api.opentopodata.org` is light-use only (~1 req/s, 1000 calls/day) and will fail
    # a full re-ingest — do not point a real ingest run at it.
    opentopodata_url: str | None = None
    opentopodata_dataset: str = "ned10m"

    # Conflation review-band persistence (DQ follow-up). Directory the pipeline
    # writes `{region}.jsonl` review-band matches under; override via
    # ADVENTURE_REVIEW_BAND_DIR (tests redirect this so no test writes into the
    # real repo tree). Defaults to the conventional gitignored path.
    review_band_dir: str = REVIEW_BAND_DIR

    # API startup warm-up budget (seconds) for one round over /plan's dependency
    # stack — chiefly how long the graph connectivity check may retry before the
    # round reports failure. /health stays 503 until a round succeeds, so this is
    # the ceiling on how long a deploy waits for a slow-but-alive Aura, not a hang:
    # past it the failure is surfaced in /health instead.
    warmup_deadline_s: float = 30.0

    # Engine-layer anonymous ranked-plan cache (Epic 039 S2). Caches `CachedPlan`
    # (facts + absolute `fetched_at`), re-rendering freshness per serve — never the
    # rendered Feed (see `orchestration/feed_cache.py`'s module docstring). Gated to
    # `viewer_id == "anonymous"` at the engine (Rule #5). 0 disables the cache
    # entirely (`Runtime.feed_cache` stays None) — a full, reversible kill switch.
    feed_cache_ttl_s: float = 300.0
    feed_cache_max_entries: int = 512

    # Default-frame feed warmer (Epic 039 mitigation ladder B5). Seconds between
    # in-process warm rounds over each region's default frame, so the anonymous
    # feed cache is never cold for the common path. 0 disables the warmer entirely
    # (same kill-switch convention as feed_cache_ttl_s). Default sits below the
    # feed-cache TTL (300s), and each round re-primes any entry that would expire
    # before the NEXT round (FeedCache.peek's horizon), so the frame stays warm
    # continuously rather than in on/off windows.
    feed_warm_interval_s: float = 240.0

    # Two-phase render (Epic 040 D6): the SERVER kill switch. When False, `/plan`
    # with phase:"cards" serves today's full single-pass response (the client
    # detects completeness and skips the conditions call) and no phase-1 holding
    # pen is wired. The client-side twin is the build-time VITE_TWO_PHASE flag;
    # either side alone fully reverts the flow.
    two_phase_enabled: bool = True

    def for_region(self, region_id: str, env: Mapping[str, str] | None = None) -> "Settings":
        """A copy of these settings bound to the region actually being ingested.

        The source registry resolves per-region assets (chiefly the 3DEP DEM) off
        `settings.region`/`settings.dem_path`. `from_env` resolves those against the
        *ambient* `ADVENTURE_REGION`, so ingesting region B while the environment
        still names region A silently handed B's trails A's DEM (or none) — the
        "Richmond got 0 elevation" bug. The pipeline calls this with its `--region`
        so `enabled_sources`/`from_config` receive the ingest region, never the
        ambient one. The explicit `ADVENTURE_3DEP_DEM` override still wins (operator
        intent); only the conventional-path fallback is re-resolved for `region_id`.
        """
        e = os.environ if env is None else env
        dem = e.get("ADVENTURE_3DEP_DEM") or default_dem_path(region_id)
        return replace(self, region=region_id, dem_path=dem)

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
        # Default includes usgs-3dep (elevation enrichment) so a re-ingest never
        # forgets it; reuse the ADVENTURE_WATCH_ADAPTERS comma-split idiom (AC-2.4).
        corpus_raw = e.get("ADVENTURE_CORPUS_SOURCES", "osm,nps,usfs,usgs-3dep")
        corpus_sources = tuple(s.strip() for s in corpus_raw.split(",") if s.strip())

        cors_raw = e.get("ADVENTURE_CORS_ALLOW_ORIGINS", "")
        cors_allow_origins = tuple(o.strip() for o in cors_raw.split(",") if o.strip())

        # Resolved once so the DEM fallback below can key off the same value the
        # Settings carries.
        region = e.get("ADVENTURE_REGION", "shenandoah-gwj")

        return Settings(
            neo4j_uri=e.get("NEO4J_URI", "bolt://localhost:7687"),
            neo4j_user=e.get("NEO4J_USER", "neo4j"),
            neo4j_password=e.get("NEO4J_PASSWORD", ""),
            local_openai_base_url=e.get("LOCAL_OPENAI_BASE_URL", "http://localhost:11434/v1"),
            anthropic_api_key=e.get("ANTHROPIC_API_KEY") or None,
            tiers={"mechanical": tier("mechanical"), "judgment": tier("judgment")},
            region=region,
            dev_viewer_secret=e.get("ADVENTURE_DEV_VIEWER_SECRET") or None,
            cors_allow_origins=cors_allow_origins,
            nws_user_agent=e.get("NWS_USER_AGENT") or None,
            airnow_api_key=e.get("AIRNOW_API_KEY") or None,
            firms_map_key=e.get("FIRMS_MAP_KEY") or None,
            ridb_api_key=e.get("RIDB_API_KEY") or None,
            nps_api_key=e.get("NPS_API_KEY") or None,
            live_adapters=live_adapters,
            live_region=e.get("ADVENTURE_LIVE_REGION", "US"),
            valhalla_base_url=e.get("VALHALLA_BASE_URL") or None,
            drive_speed_kmh=_finite_positive(
                "DRIVE_SPEED_KMH", e.get("DRIVE_SPEED_KMH", "60.0"), 60.0
            ),
            live_probe_max_workers=int(e.get("ADVENTURE_LIVE_PROBE_MAX_WORKERS", "8")),
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
            # Same raw-kept treatment as usfs_geojson_path above, verbatim: a
            # blank ADVENTURE_OSM_PBF must reach OsmPbfSource.from_config to fail
            # loud; unset → None → the osm_pbf transport's default path.
            osm_pbf_path=e.get("ADVENTURE_OSM_PBF"),
            # Explicit env override wins; otherwise fall back to the conventional
            # per-region path so a fetched DEM is applied automatically (durability
            # fix — the DEM no longer has to live in a hand-set env var that gets
            # lost). Absent both → None → 3DEP degrades to a no-op (rule #6).
            dem_path=e.get("ADVENTURE_3DEP_DEM") or default_dem_path(region),
            elev_resolution_m=_finite_positive(
                "ADVENTURE_3DEP_RESOLUTION_M", e.get("ADVENTURE_3DEP_RESOLUTION_M", "20.0"), 20.0
            ),
            opentopodata_url=e.get("ADVENTURE_OPENTOPODATA_URL") or None,
            opentopodata_dataset=e.get("ADVENTURE_OPENTOPODATA_DATASET", "ned10m"),
            # allow_zero: 0 is an established operator value — "report a down
            # dependency immediately, no retry window" — not a typo to correct.
            warmup_deadline_s=_finite_positive(
                "ADVENTURE_WARMUP_DEADLINE_S",
                e.get("ADVENTURE_WARMUP_DEADLINE_S", "30.0"),
                30.0,
                allow_zero=True,
            ),
            review_band_dir=e.get("ADVENTURE_REVIEW_BAND_DIR", REVIEW_BAND_DIR),
            # allow_zero: 0 is these two knobs' documented kill switch, not a typo.
            feed_cache_ttl_s=_finite_positive(
                "ADVENTURE_ANON_FEED_CACHE_TTL_S",
                e.get("ADVENTURE_ANON_FEED_CACHE_TTL_S", "300"),
                300.0,
                allow_zero=True,
            ),
            feed_cache_max_entries=int(e.get("ADVENTURE_ANON_FEED_CACHE_MAX_ENTRIES", "512")),
            # "0"/"false"/"no"/"off" disable; anything else (incl. unset) keeps the
            # two-phase flow on — D6's documented convention is =0.
            two_phase_enabled=e.get("ADVENTURE_TWO_PHASE_ENABLED", "1").strip().lower()
            not in {"0", "false", "no", "off"},
            feed_warm_interval_s=_finite_positive(
                "ADVENTURE_FEED_WARM_INTERVAL_S",
                e.get("ADVENTURE_FEED_WARM_INTERVAL_S", "240"),
                240.0,
                allow_zero=True,
            ),
        )
