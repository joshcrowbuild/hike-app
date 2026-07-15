"""Adventure Planner FastAPI application.

Exposes engine.plan() over HTTP. Startup wires the graph client from settings and
warms the whole /plan dependency stack off-thread; /health gates readiness on that
warm-up (Render's healthCheckPath), so traffic only cuts over to an instance whose
first /plan won't eat a cold init. The Runtime is built per-request so viewer_id
can vary.

Run dev server: uvicorn api.app:app --reload --port 8000
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import threading
import time
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Path, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from slowapi.errors import RateLimitExceeded

from api.feed_warmer import FeedWarmer
from api.gpx import build_gpx
from api.observability import (
    PlanMetrics,
    cache_size,
    estimate_tokens,
    probe_stats_snapshot,
    scrub_viewer,
)
from api.ratelimit import (
    detail_limit,
    health_limit,
    limiter,
    outcome_limit,
    plan_limit,
    rate_limit_exceeded_handler,
)
from api.schemas import (
    CANONICAL_ID_PATTERN,
    EPISODE_ID_PATTERN,
    VIEWER_ID_PATTERN,
    CardWarningResponse,
    ConditionPatchResponse,
    ConditionStatusResponse,
    ConditionUnavailableResponse,
    ElevationProfile,
    ElevationSample,
    FeedCardResponse,
    FeedLineResponse,
    FeedResponse,
    GeoJsonGeometry,
    GeoPoint,
    GraphStats,
    HealthResponse,
    IngestDiffBucket,
    IngestDiffResponse,
    OriginResponse,
    OutcomeBody,
    OutcomeResponse,
    PlanConditionsRequest,
    PlanConditionsResponse,
    PlanRequest,
    RegionResponse,
    RegionsResponse,
    SearchRequest,
    SetAsideReasonResponse,
    SetAsideResponse,
    StatusResponse,
    TrailWaterResponse,
    TripDetailResponse,
    WaterSourceResponse,
)
from graph.client import GraphClient
from graph.queries import trail_detail as trail_detail_query
from graph.queries import trails_detail as trails_detail_query
from graph.queries import water_sources_near
from ingestion.checks.facet_diff import LEVELS, ingest_stats_path, sorted_by_abs_delta
from ingestion.elevation import (
    DEFAULT_NOISE_THRESHOLD_M,
    compute_gain_loss_grade,
    haversine_m,
)
from ingestion.route import assemble_route, wkt_to_geojson
from orchestration.adapters import registry
from orchestration.config import Settings
from orchestration.engine import Feed, FeedCard, build_runtime, feed_card
from orchestration.logsafe import scrub_episode, setup_logging
from orchestration.providers.registry import resolve
from orchestration.regions import list_regions

logger = logging.getLogger(__name__)

_VERSION = "0.0.0"

# The integer data-shape stamp this API understands (graph/schema.cypher's
# Meta.schema_format). Bump only alongside a schema.cypher change that breaks how
# this API reads the graph; an old API deployment then self-reports incompatible
# via the warm-up gate below instead of misreading the new shape.
EXPECTED_SCHEMA_FORMAT: int = 1


class SchemaFormatError(RuntimeError):
    """Raised when the graph's schema_format is confirmed newer than this API
    understands — surfaced through the warm-up disclose path (never a crash)."""


# Module-level singletons populated at startup
_settings: Settings | None = None
_graph_client: GraphClient | None = None
_feed_warmer: FeedWarmer | None = None


class _WarmupState:
    """Warm-up status shared between the warm-up thread and /health (one per boot)."""

    def __init__(self) -> None:
        self.ok = threading.Event()  # set once a round over the /plan stack succeeded
        self.stop = threading.Event()  # set at shutdown so the thread exits promptly
        self.error: str | None = None  # last failed round's cause, disclosed by /health
        self.probe_keys: list[str] = []  # /health's probes_available, set on success


_warmup = _WarmupState()  # replaced by _start_warmup at lifespan startup

# Pause between failed warm-up rounds: long enough not to hammer a struggling
# dependency, short enough that /health flips to 200 promptly once it recovers.
_WARMUP_RETRY_PAUSE_S = 2.0


def _verify_schema_format(graph_client: GraphClient) -> None:
    """Refuse ONLY on a confirmed graph schema_format newer than this API supports.

    A read failure (unreachable graph, blip) is not a confirmed incompatibility, so
    it is swallowed-and-logged here rather than raised — the caller's own graph
    connectivity check already covers a genuinely-down graph (Rule #1: degrade,
    don't crash). A missing schema_format (legacy graph, pre-this-epic) also
    proceeds: absence isn't a confirmed newer format.
    """
    try:
        session = graph_client.scoped_session("schema-check")
        rows = session.run(("MATCH (m:Meta {id: 'schema'}) RETURN m.schema_format AS sf", {}))
    except Exception as exc:
        logger.warning("schema_format probe failed (%s); proceeding unverified", exc)
        return
    graph_format = rows[0].get("sf") if rows else None
    if isinstance(graph_format, int) and graph_format > EXPECTED_SCHEMA_FORMAT:
        raise SchemaFormatError(
            f"graph schema_format {graph_format} is newer than this API supports "
            f"({EXPECTED_SCHEMA_FORMAT}); deploy the matching API version"
        )


def _warm_plan_path(state: _WarmupState, settings: Settings, graph_client: GraphClient) -> None:
    """One round over /plan's dependency stack; raises on whatever is down.

    Everything /plan builds lazily per-request is forced eager here, so the failure
    a cold instance would serve as its first /plan's 500 surfaces in /health instead
    (Render then never cuts traffic over to it). No step spends money: the graph
    check is the driver's own connectivity probe, provider warm-up constructs SDK
    clients without requesting a completion, and the adapter registry only
    instantiates adapters — live probes still run JIT per request (rule #3).
    """
    deadline = time.monotonic() + settings.warmup_deadline_s
    # Graph: driver pool + TLS + auth. Retried while the round's budget lasts — Aura
    # can be slow to admit the first connection right after a deploy — then raised,
    # so a genuinely-down graph is reported (503 with a cause) rather than hung on.
    while True:
        try:
            graph_client.verify_connectivity()
            break
        except Exception:
            if state.stop.is_set() or time.monotonic() >= deadline:
                raise
            state.stop.wait(min(1.0, max(0.1, deadline - time.monotonic())))
    # Schema-format compatibility gate (Epic 024): refuse only a confirmed newer
    # graph shape. Raises SchemaFormatError, which _warmup_loop records into
    # state.error the same as any other warm-up failure.
    _verify_schema_format(graph_client)
    # Providers: the same three resolutions build_runtime performs per-request.
    # warm() forces SDK-client construction (import + key validation) but never a
    # completion — warm-up must not spend tokens; the first paid call stays /plan's.
    for role, private in (("extract", False), ("curate", False), ("curate", True)):
        resolve(role, settings, touches_private_overlay=private).provider.warm()
    # Live-adapter stack: instantiate the full registry, so an unknown adapter name
    # or bad adapter config fails here, not mid-fan-out on the first request.
    state.probe_keys = [k.value for k in registry.probes_for(settings.live_region, settings)]


def _warmup_loop(state: _WarmupState, settings: Settings, graph_client: GraphClient) -> None:
    """Retry warm-up rounds until one succeeds (then /health flips to 200) or
    shutdown. Retrying forever is deliberate: a dependency that was down at boot and
    recovers later should make the instance healthy without a redeploy — /health
    keeps disclosing the latest failure in the meantime."""
    while not state.stop.is_set():
        try:
            _warm_plan_path(state, settings, graph_client)
        except Exception as exc:
            state.error = f"{type(exc).__name__}: {exc}"
            logger.warning("warm-up round failed (%s); retrying", state.error)
            state.stop.wait(_WARMUP_RETRY_PAUSE_S)
            continue
        state.error = None
        state.ok.set()
        logger.info("warm-up complete; /health now reports ready")
        return


def _start_warmup(settings: Settings, graph_client: GraphClient) -> None:
    """Spawn the warm-up thread. Off-thread so the port binds immediately and a slow
    dependency delays readiness (/health 503) rather than boot. Hermetic tests stub
    this and install a pre-warmed `_warmup` instead (tests/conftest.py)."""
    global _warmup
    state = _WarmupState()
    _warmup = state
    threading.Thread(
        target=_warmup_loop,
        args=(state, settings, graph_client),
        daemon=True,
        name="plan-warmup",
    ).start()


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    global _settings, _graph_client, _feed_warmer
    # Coherent process logging (Phase B): without this, the API process has no
    # logging config at all and INFO lines (the /plan cost metrics, warm-up
    # completion) never reach the deploy's log stream — only WARNING+ escapes
    # via Python's last-resort handler. Level: ADVENTURE_LOG_LEVEL, default INFO.
    setup_logging()
    _settings = Settings.from_env()
    _graph_client = GraphClient(_settings.neo4j_uri, _settings.neo4j_user, _settings.neo4j_password)
    _start_warmup(_settings, _graph_client)
    # Default-frame feed warmer (Epic 039 B5): parks behind the warm-up readiness
    # gate, then keeps the anonymous feed cache primed for each region's default
    # frame on a cadence. Never blocks startup (daemon thread); 0-interval or a
    # disabled feed cache makes start() a logged no-op.
    _feed_warmer = FeedWarmer(
        _settings,
        _graph_client,
        ready=_warmup.ok,
        interval_s=_settings.feed_warm_interval_s,
    )
    _feed_warmer.start()
    yield
    _warmup.stop.set()
    if _feed_warmer is not None:
        _feed_warmer.stop()
    if _graph_client:
        _graph_client.close()


app = FastAPI(
    title="Adventure Planner",
    version=_VERSION,
    description="Personal, agentic, self-verifying hiking/backpacking trip planner.",
    lifespan=lifespan,
)

# Per-IP rate limiting (Phase B): the limiter lives on app.state so slowapi's decorators
# and exception handler can reach it; RateLimitExceeded → a clean JSON 429.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)


def _install_cors(application: FastAPI, settings: Settings) -> None:
    """Default-deny CORS for the hosted API edge (deploy contract).

    The browser blocks every cross-origin call from the Vercel frontend unless its
    exact origin is allow-listed here. Origins come from ADVENTURE_CORS_ALLOW_ORIGINS
    via Settings; an empty list means no origin is allowed (never a wildcard), so a
    misconfigured deploy fails closed instead of exposing the API to any site. Read
    once at import — middleware is fixed for the process; per-request config is not a
    thing in Starlette's stack.
    """
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_allow_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# Wire CORS at import (before the app serves a request). Settings.from_env() is a pure
# env read; lifespan re-reads it into `_settings` for the request path.
_install_cors(app, Settings.from_env())


def _authorize_viewer(viewer_id: str, dev_secret: str | None) -> None:
    """Edge auth guard (Epic 014 S3 / Rule #5): a viewer_id is honored only from an
    authenticated caller. Until the Stage-8 auth system exists, the open anonymous
    world is the only unauthenticated path; any other identity must present the
    configured shared dev secret (X-Dev-Viewer-Secret).

    Fails **closed**: if the dev secret is absent from config, every non-anonymous
    request is rejected regardless of any header (a misconfigured deploy must not
    silently accept a forged identity). Raises HTTP 403 on rejection.
    """
    if viewer_id == "anonymous":
        return
    configured = _settings.dev_viewer_secret if _settings else None
    # Compare as bytes: secrets.compare_digest raises TypeError on non-ASCII str, so a
    # non-ASCII header would otherwise 500 instead of a clean 403 (still fail-closed,
    # but bytes keeps it a deliberate 403 and stays constant-time).
    if (
        not configured
        or not dev_secret
        or not secrets.compare_digest(dev_secret.encode("utf-8"), configured.encode("utf-8"))
    ):
        raise HTTPException(status_code=403, detail="viewer_id requires authentication")


def _condition_fields(card: FeedCard) -> dict[str, Any]:
    """The condition-bearing wire fields of one card — shared verbatim by the full
    feed card and the Epic 040 phase-2 patch (`ConditionPatchResponse`), so the two
    responses can never render a condition differently (AC-2.1)."""
    return {
        "lines": [
            FeedLineResponse(
                text=line.text,
                body=line.body,
                source=line.source,
                age=line.age,
                confidence_level=line.presentation,  # "stated" | "hedged" | "flagged"
                sources=list(line.sources),
            )
            for line in card.lines
        ],
        "warnings": [
            CardWarningResponse(
                text=w.text,
                source=w.source,
                observed_at=w.observed_at.isoformat(),
                kind=w.kind,
            )
            for w in card.warnings
        ],
        "unavailable": [
            ConditionUnavailableResponse(text=u.text, source=u.source, kind=u.kind)
            for u in card.unavailable
        ],
        "conditions": [
            ConditionStatusResponse(
                kind=s.kind,
                state=s.state,
                source=s.source,
                checked_at=s.checked_at.isoformat() if s.checked_at else None,
                detail=s.detail,
            )
            for s in card.conditions
        ],
    }


def _card_response(card: FeedCard, maps: dict[str, Any]) -> FeedCardResponse:
    return FeedCardResponse(
        canonical_id=card.canonical_id,
        name=card.name,
        distance_mi=card.distance_mi,
        **_condition_fields(card),
        **maps,  # geometry / trailhead / geometry_confidence / summit / elevation_profile
    )


def _set_aside_response(trail: Any) -> SetAsideResponse:
    return SetAsideResponse(
        canonical_id=trail.canonical_id,
        name=trail.name,
        reasons=[
            SetAsideReasonResponse(text=r.text, source=r.source, kind=r.kind) for r in trail.reasons
        ],
    )


def _feed_response(
    feed: Feed, maps_by_cid: dict[str, dict[str, Any]], *, conditions_complete: bool = True
) -> FeedResponse:
    return FeedResponse(
        query=feed.query,
        cards=[_card_response(c, maps_by_cid.get(c.canonical_id, {})) for c in feed.cards],
        card_count=len(feed.cards),
        notices=list(feed.notices),
        set_aside=[_set_aside_response(t) for t in feed.set_aside],
        conditions_complete=conditions_complete,
    )


def _graph_stats() -> GraphStats | None:
    if _graph_client is None or _settings is None:
        return None
    try:
        session = _graph_client.scoped_session("health-check")
        # COUNT {} subqueries (Cypher 5 and Cypher 25) — the old size([(pattern)|x])
        # pattern-comprehension form is rejected by Aura's Cypher 25 (42I06: Invalid
        # input '|'), which silently left graph=null on every /health.
        rows = session.run(
            (
                "MATCH (m:Meta {id: 'schema'}) "
                "RETURN m.schema_version AS sv, "
                "       m.schema_format AS sf, "
                "       COUNT { (t:CanonicalTrail) } AS trails, "
                # Elevation-presence gauge (Epic 017 durability): trails carrying a
                # 3DEP-derived profile (total_gain_m is the always-written scalar). Makes
                # the "elevation lagged / went null" failure VISIBLE in /health + /status
                # instead of silent. MATCH…WHERE inside COUNT{} is valid Cypher 5 and 25.
                "       COUNT { MATCH (te:CanonicalTrail) "
                "               WHERE te.total_gain_m IS NOT NULL } AS with_elev, "
                # Corroboration-presence gauge (CDP-01 / Epic 026a): trails joined by
                # SAME_AS to ≥2 distinct upstream SourceRecord.source values — the same
                # independent-origin definition as trail_source_corroboration() in
                # graph/queries.py. A full COUNT{} subquery (WITH…WHERE…RETURN) is valid
                # Cypher 5 and 25, same as the pattern-only COUNT{} forms above.
                "       COUNT { MATCH (tc:CanonicalTrail)<-[:SAME_AS]-(sc:SourceRecord) "
                "               WITH tc, count(DISTINCT sc.source) AS n "
                "               WHERE n >= 2 "
                "               RETURN tc } AS with_multi_source, "
                "       COUNT { (r:SourceRecord) } AS srs, "
                "       COUNT { (h:Trailhead) } AS ths, "
                "       COUNT { ()-[:SAME_AS]->() } AS edges",
                {},
            )
        )
        if not rows:
            return None
        r = rows[0]
        trails = int(r.get("trails") or 0)
        with_elev = int(r.get("with_elev") or 0)
        pct = round(with_elev / trails * 100, 1) if trails else None
        with_multi = int(r.get("with_multi_source") or 0)
        corroboration_pct = round(with_multi / trails * 100, 1) if trails else None
        return GraphStats(
            canonical_trails=trails,
            trails_with_elevation=with_elev,
            elevation_coverage_pct=pct,
            trails_multi_source=with_multi,
            corroboration_pct=corroboration_pct,
            source_records=int(r.get("srs") or 0),
            trailheads=int(r.get("ths") or 0),
            same_as_edges=int(r.get("edges") or 0),
            schema_version=r.get("sv"),
            schema_format=r.get("sf"),
        )
    except Exception:
        # Degrade-and-disclose (Rule #1): report graph=null to the caller, but log the
        # cause server-side — a swallowed exception here hid the Cypher-25 bug for hours.
        logger.exception("graph stats query failed; reporting graph=null")
        return None


def _ingest_diff_stats() -> IngestDiffResponse | None:
    """Read this host's region's `stats.json` (Epic 027), written best-effort by the
    ingestion pipeline via the SAME `ingest_stats_path` resolver (AC-4.1) — so writer
    and reader always agree on the path. Degrades to `None` on any absence/read/parse
    failure (Rule #1): a single small-JSON read, no graph query added to `/health`
    (AC-4.5)."""
    if _settings is None:
        return None
    try:
        path = ingest_stats_path(_settings.region)
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        buckets = sorted_by_abs_delta([IngestDiffBucket(**b) for b in data.get("buckets", [])])
        worst_breached_level = next(
            (level for level in LEVELS if any(b.breached_level == level for b in buckets)),
            None,
        )
        return IngestDiffResponse(
            region=data["region"],
            generated_at=data["generated_at"],
            prune_blocked=bool(data.get("prune_blocked", False)),
            worst_breached_level=worst_breached_level,
            top_deltas=buckets[:5],
        )
    except Exception:
        logger.exception("ingest-diff stats read failed; reporting ingest_diff=null")
        return None


def _iso_or_none(value: Any) -> str | None:
    """Render a graph temporal value as an ISO-8601 string. neo4j's DateTime carries
    iso_format(); anything else falls back to str(); None stays None (Rule #1)."""
    if value is None:
        return None
    iso = getattr(value, "iso_format", None)
    if callable(iso):
        return str(iso())
    return str(value)


def _graph_freshness() -> tuple[str | None, str | None]:
    """(meta_updated_at, last_ingest) for /status — one scoped read alongside
    _graph_stats(). last_ingest prefers the most recent SourceRecord.fetched_at (a real
    datetime) and falls back to the coarse ingest_version ("YYYY-MM") when fetched_at is
    absent. Degrades to (None, None) on any failure — never a 500 (Rule #1)."""
    if _graph_client is None or _settings is None:
        return None, None
    try:
        session = _graph_client.scoped_session("health-check")
        rows = session.run(
            (
                "MATCH (m:Meta {id: 'schema'}) "
                "OPTIONAL MATCH (r:SourceRecord) "
                "RETURN m.updated_at AS updated_at, "
                "       max(r.fetched_at) AS fetched_at, "
                "       max(r.ingest_version) AS ingest_version",
                {},
            )
        )
        if not rows:
            return None, None
        r = rows[0]
        last_ingest = _iso_or_none(r.get("fetched_at")) or _iso_or_none(r.get("ingest_version"))
        return _iso_or_none(r.get("updated_at")), last_ingest
    except Exception:
        logger.exception("graph freshness query failed; reporting nulls")
        return None, None


@app.get("/health", response_model=HealthResponse)
@limiter.limit(health_limit)
def health(request: Request) -> HealthResponse:
    if _settings is None:
        raise HTTPException(status_code=503, detail="Settings not loaded")
    if not _warmup.ok.is_set():
        # Render gates deploy cutover on this path (render.yaml healthCheckPath):
        # stay 503 until one warm-up round over /plan's whole dependency stack has
        # succeeded, so traffic never lands on an instance whose first /plan would
        # eat a cold init as a 500. A failing dependency is disclosed, not hidden
        # (Rule #1) — the previous instance keeps serving while this one reports.
        detail = (
            f"warming up: {_warmup.error}"
            if _warmup.error
            else "warming up: /plan dependency stack not yet verified"
        )
        raise HTTPException(status_code=503, detail=detail)
    return HealthResponse(
        status="ok",
        version=_VERSION,
        region=_settings.region,
        probes_available=_warmup.probe_keys,
        graph=_graph_stats(),
        ingest_diff=_ingest_diff_stats(),
    )


@app.get("/status", response_model=StatusResponse)
@limiter.limit(health_limit)
def status(request: Request) -> StatusResponse:
    """Current deployed state for cross-surface grounding (agent operating model):
    what commit is running (Render env), which corpus/live region it serves, and how
    fresh the graph is. World/Meta reads only, through the scoped session (Rule #4);
    every graph-derived field degrades to null when the graph is unreachable, mirroring
    /health's graph=null (Rule #1)."""
    if _settings is None:
        raise HTTPException(status_code=503, detail="Settings not loaded")
    corpus = _graph_stats()
    meta_updated_at, last_ingest = _graph_freshness()
    return StatusResponse(
        deploy_sha=os.environ.get("RENDER_GIT_COMMIT"),
        deploy_branch=os.environ.get("RENDER_GIT_BRANCH"),
        region=_settings.region,
        live_region=_settings.live_region,
        schema_version=corpus.schema_version if corpus else None,
        meta_updated_at=meta_updated_at,
        last_ingest=last_ingest,
        corpus=corpus,
    )


@app.get("/regions", response_model=RegionsResponse)
@limiter.limit(health_limit)
def regions(request: Request) -> RegionsResponse:
    """Every region's picker-facing config (Phase 2: config-driven origins) — a plain
    read of `regions/*.geojson`, independent of the graph and of which region this
    process was last started with (`ADVENTURE_REGION`). Adding a region's origins is
    now a config edit (regions/*.geojson) rather than a frontend deploy."""
    return RegionsResponse(
        regions=[
            RegionResponse(
                region_id=r.region_id,
                label=r.label,
                origins=[
                    OriginResponse(key=o.key, label=o.label, lat=o.lat, lon=o.lon)
                    for o in r.origins
                ],
            )
            for r in list_regions()
        ]
    )


@app.post("/plan", response_model=FeedResponse)
@limiter.limit(plan_limit)
def plan(
    request: Request,  # required by slowapi for per-IP keying (also gives us the edge)
    body: PlanRequest,
    x_dev_viewer_secret: str | None = Header(default=None),
) -> FeedResponse:
    if _settings is None or _graph_client is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    _authorize_viewer(body.viewer_id, x_dev_viewer_secret)
    # Observability (Phase B): time the fan-out and snapshot the live-probe cache so we can
    # see latency + how much third-party quota the call spent. Never logs viewer_id in the
    # clear (Rule #5).
    started = time.perf_counter()
    try:
        runtime = build_runtime(_settings, _graph_client, body.viewer_id)

        cache_before = cache_size(runtime.cache)
        stats_before = probe_stats_snapshot(runtime.cache)
        # Two-phase render (Epic 040): phase:"cards" runs the graph-only phase-1
        # path unless the server kill switch is off (D6) or the anonymous key is
        # already warm (D7) — either way the response self-describes completeness
        # via `conditions_complete` so the client knows whether to follow up on
        # POST /plan/conditions. `phase` absent stays byte-identical to today.
        if body.phase == "cards" and _settings.two_phase_enabled:
            from orchestration.two_phase import plan_cards

            feed, conditions_complete = plan_cards(
                body.query,
                (body.lat, body.lon),
                runtime,
                k=body.k,
                viewer_id=body.viewer_id,
            )
        else:
            from orchestration.engine import plan as engine_plan

            conditions_complete = True
            feed = engine_plan(
                body.query,
                (body.lat, body.lon),
                runtime,
                k=body.k,
                viewer_id=body.viewer_id,  # AC-5: forward viewer for context assembly
            )
        # Engine-layer anonymous plan cache (Epic 039 S2): the hit disposition is
        # request-local on Runtime (set by plan()), never a before/after delta on
        # the shared FeedCacheStats counter — under threadpool concurrency a delta
        # attributes another request's hit to this one and zeroes real spend.
        feed_cache_hit = getattr(runtime, "feed_cache_hit", False)
        # Attach per-card maps/terrain fields (Epic 016 S1 / Epic 017 S4). World data
        # → a plain scoped read; degrades to map-free cards on any failure (Rule #1).
        session = _graph_client.scoped_session(body.viewer_id)
        maps_by_cid = _fetch_maps_by_canonical(session, [c.canonical_id for c in feed.cards])
        response = _feed_response(feed, maps_by_cid, conditions_complete=conditions_complete)
        cache_after = cache_size(runtime.cache)
        stats_after = probe_stats_snapshot(runtime.cache)
    except HTTPException:
        raise
    except Exception as exc:
        # A transient graph/provider blip self-heals upstream (managed-tx + provider retry);
        # only a genuinely unrecoverable failure reaches here. Log the real cause with its
        # exception CLASS and a short correlation id (extends the #53 observability line) so
        # the residual 500 is one grep away in Render logs, and hand the same id back in a
        # header for a user report to reference. Never log viewer_id in the clear (Rule #5).
        # The body stays a generic typed 500 the frontend's classify() maps to kind:"server".
        correlation_id = secrets.token_hex(4)
        logger.exception(
            "plan failed cid=%s error_class=%s query=%r viewer=%s",
            correlation_id,
            type(exc).__name__,
            body.query,
            scrub_viewer(body.viewer_id),
        )
        raise HTTPException(
            status_code=500,
            detail="Internal error",
            headers={"X-Correlation-Id": correlation_id},
        ) from exc
    # Emit metrics AFTER the response is built and OUTSIDE the 500-mapping try: the fan-out
    # already succeeded and its cost is already spent, so a metrics bug must never discard a
    # good response and bill the user for a 500 (degrade gracefully at the surface).
    try:
        # A feed-cache hit ran no intent-parse/taste-rank LLM call and no live probe —
        # est_tokens must be 0, NOT estimated from the (still rendered) cached card
        # text, or the log fabricates spend that was never spent (Rule #1).
        if feed_cache_hit:
            est_tokens = 0
        else:
            line_texts = [line.text for card in feed.cards for line in card.lines]
            est_tokens = estimate_tokens(body.query, *line_texts)
        PlanMetrics(
            viewer_tag=scrub_viewer(body.viewer_id),
            latency_ms=(time.perf_counter() - started) * 1000,
            card_count=len(feed.cards),
            cache_entries_before=cache_before,
            cache_entries_after=cache_after,
            est_tokens=est_tokens,
            probe_stats_before=stats_before,
            probe_stats_after=stats_after,
            feed_cache_hit=feed_cache_hit,
        ).emit()
    except Exception:
        logger.exception("plan observability emit failed (response already sent)")
    return response


@app.post("/plan/conditions", response_model=PlanConditionsResponse)
@limiter.limit(plan_limit)
def plan_conditions(
    request: Request,  # required by slowapi for per-IP keying
    body: PlanConditionsRequest,
    x_dev_viewer_secret: str | None = Header(default=None),
) -> PlanConditionsResponse:
    """The Epic 040 phase-2 patch call: the verified live overlay for exactly the
    canonical_ids a phase-1 `/plan` (phase:"cards") returned. Shares `/plan`'s
    rate-limit class, auth posture (anonymous-allowed; a non-anonymous viewer is
    gated exactly like `/plan` — AC-2.4), probe registry, TTL cache, and worker
    bound (shared engine code path, never a re-implementation — AC-2.3). This
    call never ranks: zero LLM spend by construction."""
    if _settings is None or _graph_client is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    _authorize_viewer(body.viewer_id, x_dev_viewer_secret)
    started = time.perf_counter()
    try:
        runtime = build_runtime(_settings, _graph_client, body.viewer_id)
        from orchestration.two_phase import plan_conditions as engine_plan_conditions

        cache_before = cache_size(runtime.cache)
        stats_before = probe_stats_snapshot(runtime.cache)
        patch = engine_plan_conditions(
            body.query,
            (body.lat, body.lon),
            runtime,
            body.canonical_ids,
            k=body.k,
            viewer_id=body.viewer_id,
        )
        response = PlanConditionsResponse(
            patches=[
                ConditionPatchResponse(canonical_id=c.canonical_id, **_condition_fields(c))
                for c in patch.cards
            ],
            set_aside=[_set_aside_response(t) for t in patch.set_aside],
            unknown=list(patch.unknown),
        )
        cache_after = cache_size(runtime.cache)
        stats_after = probe_stats_snapshot(runtime.cache)
    except HTTPException:
        raise
    except Exception as exc:
        correlation_id = secrets.token_hex(4)
        logger.exception(
            "plan/conditions failed cid=%s error_class=%s query=%r viewer=%s",
            correlation_id,
            type(exc).__name__,
            body.query,
            scrub_viewer(body.viewer_id),
        )
        raise HTTPException(
            status_code=500,
            detail="Internal error",
            headers={"X-Correlation-Id": correlation_id},
        ) from exc
    # Metrics AFTER the response is built and OUTSIDE the 500-mapping try (same
    # discipline as /plan): the probe spend is already spent — a metrics bug must
    # never turn a good patch into a 500.
    try:
        PlanMetrics(
            viewer_tag=scrub_viewer(body.viewer_id),
            latency_ms=(time.perf_counter() - started) * 1000,
            card_count=len(patch.cards),
            cache_entries_before=cache_before,
            cache_entries_after=cache_after,
            # This call NEVER runs an LLM (AC-2.3: the rank happened in phase 1) —
            # est_tokens is honestly 0, not an estimate fabricated from card text.
            est_tokens=0,
            probe_stats_before=stats_before,
            probe_stats_after=stats_after,
            feed_cache_hit=patch.from_cache,
        ).emit()
    except Exception:
        logger.exception("plan/conditions observability emit failed (response already sent)")
    return response


@app.post("/search", response_model=FeedResponse)
@limiter.limit(plan_limit)
def search(
    request: Request,  # required by slowapi for per-IP keying (also gives us the edge)
    body: SearchRequest,
) -> FeedResponse:
    """Trail-name search (Epic 038 / B001 Problem A — the Omnibox backend). `query` is
    trail-name text ("Old Rag", "Rivanna"); there is no lat/lon. Name-matched trails
    flow through the SAME verify -> present pipeline as `/plan` (`search_trails` ->
    `_plan_from_candidates`, the shared tail `plan_from_origin` uses) so cards carry
    sourced+timestamped conditions and confidence (rule #1) — never a raw graph dump.
    No match -> an honest empty `FeedResponse` (never an error). Anonymous-only by
    contract (no viewer_id in the request; a name search has no personal-overlay
    concept), same rate-limit class as `/plan`."""
    if _settings is None or _graph_client is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    started = time.perf_counter()
    try:
        runtime = build_runtime(_settings, _graph_client, "anonymous")
        from orchestration.engine import search_trails

        cache_before = cache_size(runtime.cache)
        stats_before = probe_stats_snapshot(runtime.cache)
        batch = search_trails(
            body.query,
            runtime.session,
            runtime.probes,
            k=body.k,
            cache=runtime.cache,
            probe_max_workers=runtime.probe_max_workers,
        )
        feed = Feed(
            query=body.query,
            cards=[feed_card(p) for p in batch.trails],
            notices=batch.notices,
            set_aside=batch.set_aside,
        )
        session = _graph_client.scoped_session("anonymous")
        maps_by_cid = _fetch_maps_by_canonical(session, [c.canonical_id for c in feed.cards])
        response = _feed_response(feed, maps_by_cid, conditions_complete=True)
        cache_after = cache_size(runtime.cache)
        stats_after = probe_stats_snapshot(runtime.cache)
    except HTTPException:
        raise
    except Exception as exc:
        correlation_id = secrets.token_hex(4)
        logger.exception(
            "search failed cid=%s error_class=%s query=%r",
            correlation_id,
            type(exc).__name__,
            body.query,
        )
        raise HTTPException(
            status_code=500,
            detail="Internal error",
            headers={"X-Correlation-Id": correlation_id},
        ) from exc
    try:
        line_texts = [line.text for card in feed.cards for line in card.lines]
        est_tokens = estimate_tokens(body.query, *line_texts)
        PlanMetrics(
            viewer_tag=scrub_viewer("anonymous"),
            latency_ms=(time.perf_counter() - started) * 1000,
            card_count=len(feed.cards),
            cache_entries_before=cache_before,
            cache_entries_after=cache_after,
            est_tokens=est_tokens,
            probe_stats_before=stats_before,
            probe_stats_after=stats_after,
            feed_cache_hit=False,
        ).emit()
    except Exception:
        logger.exception("search observability emit failed (response already sent)")
    return response


def _point_latlon(point: Any) -> tuple[float, float] | None:
    """Extract `(lat, lon)` from a graph point — a neo4j WGS84 Point (`.latitude`/
    `.longitude`), a dict, or `None`. Returns `None` when there's no usable point."""
    if point is None:
        return None
    lat = getattr(point, "latitude", None)
    lon = getattr(point, "longitude", None)
    if lat is not None and lon is not None:
        return float(lat), float(lon)
    if isinstance(point, dict):
        lat = point.get("latitude", point.get("lat"))
        lon = point.get("longitude", point.get("lon"))
        if lat is not None and lon is not None:
            return float(lat), float(lon)
    return None


def _geometry_and_confidence(
    row: dict[str, Any],
) -> tuple[GeoJsonGeometry | None, str | None]:
    """The route as GeoJSON + its confidence tier. Geometry is the precomputed
    `route_geom_wkt` when it parses, else assembled on the fly from the trail's
    `Segment.geom_wkt`s (fallback for pre-precompute data — e.g. the seed — or a
    corrupt stored route). Confidence is derived from assembly quality (Rule #2 /
    D5): a clean single `LineString` → `stated`; a gappy `MultiLineString` → `hedged`
    (the client draws non-`stated` as a dashed "approximate" route). `(None, None)`
    when no line — never a fabricated route (Rule #1)."""
    geo = wkt_to_geojson(row.get("route_geom_wkt"))
    if geo is None:  # absent or unparseable → fall back to assembling the segments
        geo = wkt_to_geojson(assemble_route(row.get("segment_wkts") or []))
    if geo is None:
        return None, None
    confidence = "stated" if geo["type"] == "LineString" else "hedged"
    return GeoJsonGeometry(**geo), confidence


def _trailhead(row: dict[str, Any]) -> GeoPoint | None:
    """The start marker: the accessing trailhead's surveyed point, or — when the trail
    has no tagged `:Trailhead` — a point derived from the trail's own geometry as a
    fallback (D7: coverage isn't gated on trailhead tagging). `None` when neither
    exists.

    Barrier islands and urban corpora under-tag trailheads, so most real trails reach
    the feed only via the geometry fallback; that point is a derived *approximate*
    access point (the trail's stored centroid), not a surveyed trailhead, so it is
    disclosed as `derived=True` rather than posing as one (Rule #1 / source-or-silence).
    A surveyed trailhead wins when present and is `derived=False` — regions that DO tag
    trailheads (e.g. Shenandoah) are unchanged."""
    surveyed = _point_latlon(row.get("trailhead_point"))
    if surveyed is not None:
        return GeoPoint(lat=surveyed[0], lon=surveyed[1], derived=False)
    derived = _point_latlon(row.get("trail_point"))
    if derived is not None:
        return GeoPoint(lat=derived[0], lon=derived[1], derived=True)
    return None


# Grade-based speed factor, ported from Valhalla (github.com/valhalla/valhalla),
# `src/sif/pedestriancost.cc`, `kGradeBasedSpeedFactor` (~lines 201-216). Valhalla
# is MIT-licensed: Copyright (c) 2018 Valhalla contributors, Copyright (c)
# 2015-2017 Mapillary AB / Mapzen. Ported here
# as data (not called over the network — see Epic 032 scope fence) because our
# 10 m 3DEP profile is finer than the deployed service's tiles and a live
# pedestrian call there would collapse to the flat grade bucket. The factor is a
# time multiplier (higher = slower); it derives from DIN 33466 on ascent and a
# modified Tobler function on descent (fastest a bit below flat, at -3%).
_GRADE_BREAKPOINTS_PCT: tuple[float, ...] = (
    -10.0,
    -8.0,
    -6.5,
    -5.0,
    -3.0,
    -1.5,
    0.0,
    1.5,
    3.0,
    5.0,
    6.5,
    8.0,
    10.0,
    11.5,
    13.0,
    15.0,
)
_GRADE_TIME_FACTORS: tuple[float, ...] = (
    1.33,
    1.22,
    1.08,
    0.97,
    0.88,
    0.92,
    1.00,
    1.10,
    1.20,
    1.33,
    1.43,
    1.57,
    1.83,
    2.03,
    2.23,
    2.50,
)

# Flat-ground pace (km/h) the grade factor multiplies against — a level route
# (factor 1.00 at 0%) yields exactly this speed. A computed ESTIMATE, never a
# stated fact (Rule #1/#7) — `estimated_duration_min` names it so the client can
# disclose it as such rather than presenting it like a verified duration.
_ETA_FLAT_PACE_KMH = 5.0

# Minimum ground-length per graded segment (m), comfortably above
# `DEFAULT_NOISE_THRESHOLD_M` (3 m): consecutive samples are accumulated until
# their run clears this before a single grade is computed for it, so DEM jitter
# between adjacent 10 m samples can't manufacture a spurious wall or dip (mirrors
# `ingestion.elevation._max_grade_pct`'s windowing).
_ETA_MIN_SEGMENT_M = 30.0


def _grade_time_factor(grade_pct: float) -> float:
    """Time multiplier for a grade (%) via piecewise-linear interpolation between
    `_GRADE_BREAKPOINTS_PCT`/`_GRADE_TIME_FACTORS` — our 10 m 3DEP resolves finer
    than Valhalla's 16 buckets, so we interpolate rather than quantize. Grades
    outside [-10%, +15%] linearly extrapolate from the nearest endpoint pair
    rather than clamp: clamping would make a steep descent read as fast as a
    gentle one, which is wrong (a real descent keeps getting slower)."""
    breakpoints = _GRADE_BREAKPOINTS_PCT
    factors = _GRADE_TIME_FACTORS
    if grade_pct <= breakpoints[0]:
        slope = (factors[1] - factors[0]) / (breakpoints[1] - breakpoints[0])
        return factors[0] + slope * (grade_pct - breakpoints[0])
    if grade_pct >= breakpoints[-1]:
        slope = (factors[-1] - factors[-2]) / (breakpoints[-1] - breakpoints[-2])
        return factors[-1] + slope * (grade_pct - breakpoints[-1])
    for i in range(len(breakpoints) - 1):
        if breakpoints[i] <= grade_pct <= breakpoints[i + 1]:
            t = (grade_pct - breakpoints[i]) / (breakpoints[i + 1] - breakpoints[i])
            return factors[i] + t * (factors[i + 1] - factors[i])
    return factors[-1]  # unreachable — the two guards above cover the full range


def _estimated_duration_min(distances_m: list[float], elevations_m: list[float]) -> float:
    """Grade-aware duration ESTIMATE: a per-segment integral of `_ETA_FLAT_PACE_KMH`
    scaled by `_grade_time_factor`, over ground segments coarsened to at least
    `_ETA_MIN_SEGMENT_M` (see module comment). `distances_m` is cumulative
    horizontal ground distance (`ingestion/elevation.py`), so `Δelev/Δhoriz-dist`
    is already planimetric rise/run — no slope-distance correction needed."""
    n = len(distances_m)
    if n < 2 or distances_m[-1] - distances_m[0] <= 0:
        return 0.0
    total_min = 0.0
    start_idx = 0
    i = 1
    while i < n:
        while i < n - 1 and distances_m[i] - distances_m[start_idx] < _ETA_MIN_SEGMENT_M:
            i += 1
        run = distances_m[i] - distances_m[start_idx]
        if run > 0:
            grade_pct = (elevations_m[i] - elevations_m[start_idx]) / run * 100.0
            factor = _grade_time_factor(grade_pct)
            total_min += (run / 1000.0) / _ETA_FLAT_PACE_KMH * 60.0 * factor
        start_idx = i
        i += 1
    return total_min


def _elevation_profile(row: dict[str, Any]) -> ElevationProfile | None:
    """Reassemble the stored parallel sample arrays into `WireElevationProfile`.
    `None` when no profile is stored (no DEM coverage) — not faked (D3). Provenance
    is read straight from the stored `elev_source`, never defaulted: a profile
    missing its source is treated as absent rather than mislabeled (Rule #1). The
    loader always writes the arrays and `elev_source` together, so a present profile
    carries real provenance.

    `total_gain_m`/`total_loss_m`/`max_grade_pct` are derived fresh from the sample
    arrays here — via the same hysteresis accumulator ingestion uses
    (`ingestion.elevation.compute_gain_loss_grade`) — rather than trusted from a
    second stored scalar that could drift from the samples. Only a move exceeding
    `DEFAULT_NOISE_THRESHOLD_M` (3 m) since the last counted point is credited as
    real gain/loss, so sub-threshold DEM jitter doesn't inflate "total ascent"."""
    distances = row.get("profile_distances_m")
    elevations = row.get("profile_elevations_m")
    source = row.get("elev_source")
    if not distances or not elevations or len(distances) != len(elevations) or not source:
        return None
    distances_f = [float(d) for d in distances]
    elevations_f = [float(e) for e in elevations]
    samples = [
        ElevationSample(distance_m=d, elevation_m=e) for d, e in zip(distances_f, elevations_f)
    ]
    gain, loss, max_grade = compute_gain_loss_grade(
        distances_f, elevations_f, noise_threshold_m=DEFAULT_NOISE_THRESHOLD_M
    )
    return ElevationProfile(
        samples=samples,
        total_gain_m=gain,
        total_loss_m=loss,
        max_grade_pct=max_grade,
        source=source,
        resolution_m=float(row.get("elev_resolution_m") or 0.0),
        estimated_duration_min=_estimated_duration_min(distances_f, elevations_f),
    )


def _maps_fields(row: dict[str, Any]) -> dict[str, Any]:
    """The shared maps/terrain fields (Epic 016 S1 / Epic 017 S4) for one trail row,
    spread onto both the feed card and the detail response so the shape is identical.
    `summit` is `None` until the graph carries a high-point concept (source-or-silence,
    Rule #1)."""
    geometry, confidence = _geometry_and_confidence(row)
    return {
        "geometry": geometry,
        "trailhead": _trailhead(row),
        "geometry_confidence": confidence,
        "summit": None,
        "elevation_profile": _elevation_profile(row),
    }


def _fetch_maps_by_canonical(session: Any, canonical_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Batch-read the maps fields for a feed's cards (one round trip). Degrades to an
    empty map on any read error — the cards then render map-free rather than 500."""
    if not canonical_ids:
        return {}
    try:
        rows = session.run(trails_detail_query(canonical_ids))
    except Exception:
        # Maps degrade to absent (Rule #1: map-free cards, never a 500) — but disclose.
        logger.exception("maps batch read failed; cards render map-free")
        return {}
    return {r["canonical_id"]: _maps_fields(r) for r in rows if r.get("canonical_id")}


# ── Water overlay (Epic 041): the read surface over Epic 035's :WaterSource ──
#
# `water_sources_near` measures from ONE point, so "near the route" must be
# earned here: fetch coarsely around the trail, then compute each source's
# minimum great-circle distance to the route vertices. The coarse radius doubles
# as the CDP-02 coverage probe — an empty coarse read means the region was never
# water-ingested, which is SILENCE (null), never an answered-empty claim.

# The user-facing "near" threshold (~650 ft) — echoed on the wire as `radius_m`
# so the client renders the number actually applied, not a hardcoded twin.
WATER_NEAR_RADIUS_M = 200.0
# Region-coverage probe scale: comfortably beyond any day-hike route span, and
# small enough that another region's overlay (regions sit far apart) can't
# masquerade as local coverage.
WATER_COVERAGE_RADIUS_M = 30_000.0
# The whole corpus holds ~hundreds of water nodes; this cap keeps the coarse
# read bounded without ever truncating a real region's overlay.
WATER_COARSE_LIMIT = 500
# Detail shows the nearest few, not a ledger (the UX-review discipline).
WATER_MAX_SOURCES = 12


def _water_sources(session: Any, row: dict[str, Any]) -> TrailWaterResponse | None:
    """The water answer for one trail (Epic 041), or `None` for honest silence.

    Three-way outcome (CDP-02): sources within `WATER_NEAR_RADIUS_M` → an
    answer; corpus coverage but nothing near → an answered-empty
    (`none_nearby`); no coverage at all, no anchor, or a failed read → `None`
    (rendered as no row — never a fabricated "no water" claim, Rule #1).
    Distances are honest to their basis: minimum distance to the route
    vertices when a route is drawable (`basis="route"`), else the graph's own
    point distance from the trail's start (`basis="start"`). Degrades to
    silence on any error — water is enrichment on the detail payload, never a
    dependency (the `_fetch_maps_by_canonical` posture)."""
    try:
        vertices = _route_coords_for_export(row)  # ordered (lon, lat) or None
        basis: Literal["route", "start"]
        if vertices:
            mid_lon, mid_lat = vertices[len(vertices) // 2]
            anchor_lat, anchor_lon = mid_lat, mid_lon
            basis = "route"
        else:
            start = _trailhead(row)
            if start is None:
                return None  # nothing honest to anchor a proximity claim to
            anchor_lat, anchor_lon = start.lat, start.lon
            basis = "start"
        rows = session.run(
            water_sources_near(
                anchor_lat, anchor_lon, WATER_COVERAGE_RADIUS_M, limit=WATER_COARSE_LIMIT
            )
        )
        if not rows:
            return None  # region never water-ingested → silence, not answered-empty
        near: list[tuple[float, float, float, dict[str, Any]]] = []
        for r in rows:
            latlon = _point_latlon(r.get("point"))
            if latlon is None:
                continue  # unusable node → skipped, never raised on
            w_lat, w_lon = latlon
            if basis == "route" and vertices:
                dist = min(haversine_m((lon, lat), (w_lon, w_lat)) for lon, lat in vertices)
            else:
                stored = r.get("distance_m")
                dist = (
                    float(stored)
                    if stored is not None
                    else haversine_m((anchor_lon, anchor_lat), (w_lon, w_lat))
                )
            if dist <= WATER_NEAR_RADIUS_M:
                near.append((dist, w_lat, w_lon, r))
        near.sort(key=lambda item: item[0])
        sources = [
            WaterSourceResponse(
                water_id=str(r.get("water_id") or ""),
                water_type=str(r.get("water_type") or ""),
                name=r.get("name"),
                lat=w_lat,
                lon=w_lon,
                distance_m=round(dist, 1),
                seasonal=r.get("seasonal"),
                source=str(r.get("source") or ""),
            )
            for dist, w_lat, w_lon, r in near[:WATER_MAX_SOURCES]
        ]
        corpus_source = ", ".join(sorted({str(r.get("source")) for r in rows if r.get("source")}))
        return TrailWaterResponse(
            state="sources" if sources else "none_nearby",
            basis=basis,
            radius_m=WATER_NEAR_RADIUS_M,
            source=corpus_source,
            sources=sources,
        )
    except Exception:
        logger.exception("water overlay read failed; detail renders water-free")
        return None


def _trip_detail_response(
    canonical_id: str, row: dict[str, Any], water: TrailWaterResponse | None = None
) -> TripDetailResponse:
    return TripDetailResponse(
        canonical_id=canonical_id,
        name=row.get("name") or canonical_id,
        water_sources=water,
        **_maps_fields(row),
    )


@app.get("/trail/{canonical_id}", response_model=TripDetailResponse)
@limiter.limit(detail_limit)
def trail_detail(
    request: Request,  # required by slowapi for per-IP keying
    canonical_id: str = Path(pattern=CANONICAL_ID_PATTERN),
    viewer_id: str = Query(default="anonymous", pattern=VIEWER_ID_PATTERN),
    x_dev_viewer_secret: str | None = Header(default=None),
) -> TripDetailResponse:
    """Trip/detail: the assembled route geometry + trailhead + elevation profile for
    one trail (Epic 016 S1 + Epic 017 S4). World data → anonymous-browsable; a
    non-anonymous viewer is still auth-gated (Rule #5). 404 when the trail is
    unknown; honest `null`s when geometry/elevation are absent (Rule #1)."""
    if _graph_client is None or _settings is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    _authorize_viewer(viewer_id, x_dev_viewer_secret)
    try:
        session = _graph_client.scoped_session(viewer_id)
        rows = session.run(trail_detail_query(canonical_id))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("trail detail failed for canonical_id=%r", canonical_id)
        raise HTTPException(status_code=500, detail="Internal error") from exc
    if not rows:
        raise HTTPException(status_code=404, detail="Trail not found")
    # The water answer (Epic 041) — enrichment on the detail payload: it
    # degrades to null (silence) inside `_water_sources`, never a 500.
    return _trip_detail_response(canonical_id, rows[0], _water_sources(session, rows[0]))


def _route_coords_for_export(row: dict[str, Any]) -> list[tuple[float, float]] | None:
    """The route's `(lon, lat)` vertex list for GPX export, reusing
    `_geometry_and_confidence`'s resolution (prefer `route_geom_wkt`, else
    assemble the segments) rather than re-deriving it, so the two endpoints can
    never disagree about which route a trail has. Flattened to one ordered list:
    a `MultiLineString`'s parts are concatenated in part order since the minimal
    core emits a single `<trkseg>`. `None` when the trail carries no parseable
    geometry at all."""
    geometry, _confidence = _geometry_and_confidence(row)
    if geometry is None:
        return None
    if geometry.type == "LineString":
        coords = geometry.coordinates
    else:  # MultiLineString: flatten parts in order
        coords = [pt for part in geometry.coordinates for pt in part]
    return [(float(lon), float(lat)) for lon, lat in coords]


def _safe_filename_slug(canonical_id: str) -> str:
    """ASCII stem for `Content-Disposition`'s filename — no path separators,
    quotes, or control chars, so a canonical_id can never inject header syntax."""
    return re.sub(r"[^A-Za-z0-9_-]", "-", canonical_id)


@app.get("/trail/{canonical_id}/export.gpx")
@limiter.limit(detail_limit)
def trail_export_gpx(
    request: Request,  # required by slowapi for per-IP keying
    canonical_id: str = Path(pattern=CANONICAL_ID_PATTERN),
    viewer_id: str = Query(default="anonymous", pattern=VIEWER_ID_PATTERN),
    x_dev_viewer_secret: str | None = Header(default=None),
) -> Response:
    """GPX 1.1 download of a trail's WORLD/corpus route (Epic 028 / CoMaps §D4).

    Reads through the same world-only `trail_detail` projection as `GET
    /trail/{id}` — never a viewer's personal episode/recorded geometry (Rule #5:
    share the derived conclusion, never the raw substrate). Because it's shared
    world data, it needs no auth and is anonymous-friendly, mirroring the sibling
    endpoint's posture exactly. 404 for an unknown trail; 422 for a known trail
    whose route can't be assembled (never a 200 with an empty/fabricated track —
    Rule #1). The `<ele>` gate (D4.3) is applied inside `build_gpx`: most current
    trails have no vertex-aligned elevation profile, so an empty `<ele>` on a real
    trail is the expected, honest outcome, not a defect.
    """
    if _graph_client is None or _settings is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    _authorize_viewer(viewer_id, x_dev_viewer_secret)
    try:
        session = _graph_client.scoped_session(viewer_id)
        rows = session.run(trail_detail_query(canonical_id))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("gpx export failed for canonical_id=%r", canonical_id)
        raise HTTPException(status_code=500, detail="Internal error") from exc
    if not rows:
        raise HTTPException(status_code=404, detail="Trail not found")
    row = rows[0]
    coords = _route_coords_for_export(row)
    if coords is None:
        raise HTTPException(status_code=422, detail="Trail has no exportable route geometry")
    trailhead_latlon = _point_latlon(row.get("trailhead_point"))
    trailhead = (trailhead_latlon[1], trailhead_latlon[0]) if trailhead_latlon else None
    xml = build_gpx(
        row.get("name") or canonical_id,
        coords,
        elevations=row.get("profile_elevations_m"),
        elev_source=row.get("elev_source"),
        trailhead=trailhead,
    )
    safe_slug = _safe_filename_slug(canonical_id)
    return Response(
        content=xml,
        media_type="application/gpx+xml",
        headers={"Content-Disposition": f'attachment; filename="{safe_slug}.gpx"'},
    )


def _drain_queue_bg(queue, graph_client) -> None:
    """Drain the belief update queue after the HTTP response is sent.

    Called via FastAPI BackgroundTasks so the caller receives their response
    immediately; belief updates happen asynchronously (AC-4.3 / S6 §4.1 queue
    discipline: never block the request path). Drains through the scoped-write
    seam (Epic 011): `scoped_session` is the per-owner factory each task's writes
    are scoped through (rule #4).

    By the time this runs the response is already sent, so a raised exception has
    nowhere to surface except the log — an unguarded failure here silently drops
    the user's belief update (AM2). No durable dead-letter queue yet (out of
    scope); this only stops the loss from being silent. Never logs a raw
    viewer_id (rule #5): the correlation id is the only identifier recorded.
    """
    try:
        queue.drain(graph_client.scoped_session)
    except Exception as exc:
        correlation_id = secrets.token_hex(4)
        logger.exception(
            "belief queue drain failed cid=%s error_class=%s", correlation_id, type(exc).__name__
        )


@app.post("/episode/{episode_id}/outcome", response_model=OutcomeResponse)
@limiter.limit(outcome_limit)
def record_outcome(
    request: Request,  # required by slowapi for per-IP keying
    body: OutcomeBody,
    background_tasks: BackgroundTasks,
    # Episode ids share viewer_id's alphabet (they embed the owner id) — validate the
    # path param before it reaches a scoped query or a log line (2026-07-12 review).
    episode_id: str = Path(pattern=EPISODE_ID_PATTERN),
    # Phase 1: query param; Stage 8 replaces with auth header.
    viewer_id: str = Query(default="anonymous", pattern=VIEWER_ID_PATTERN),
    x_dev_viewer_secret: str | None = Header(default=None),
) -> OutcomeResponse:
    """Record a post-hike outcome (rating + optional reflection).

    Idempotent: re-posting updates the existing Outcome, does not create a second.
    Returns 404 if the episode does not belong to the viewer (Rule #4).
    """
    if _graph_client is None or _settings is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    _authorize_viewer(viewer_id, x_dev_viewer_secret)
    try:
        from orchestration.belief_update import BeliefUpdateQueue
        from orchestration.outcome import OutcomeRequest, write_outcome

        req = OutcomeRequest(
            overall=body.overall,
            delta_question=body.delta_question,
            delta_answer=body.delta_answer,
            skipped=body.skipped,
        )
        belief_queue = BeliefUpdateQueue()
        scoped = _graph_client.scoped_session(viewer_id)
        result = write_outcome(episode_id, viewer_id, req, scoped, belief_queue=belief_queue)
        if result is None:
            raise HTTPException(status_code=404, detail="Episode not found")
        # AC-4.3: drain AFTER response is sent, not before (BackgroundTasks)
        background_tasks.add_task(_drain_queue_bg, belief_queue, _graph_client)
        return OutcomeResponse(
            outcome_id=result.outcome_id,
            episode_id=result.episode_id,
            skipped=result.skipped,
            overall=result.overall,
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("record outcome failed for episode_id=%s", scrub_episode(episode_id))
        raise HTTPException(status_code=500, detail="Internal error") from exc


@app.exception_handler(Exception)
async def generic_exception_handler(request: Any, exc: Exception) -> JSONResponse:
    # Last-resort handler for anything not caught in a route — disclose server-side
    # only. The raw exception text can carry internals (paths, query fragments,
    # library internals) that must never reach a client (rule #10).
    logger.exception("unhandled exception")
    return JSONResponse(status_code=500, content={"detail": "Internal error"})
