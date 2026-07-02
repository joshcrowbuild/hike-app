"""Adventure Planner FastAPI application.

Exposes engine.plan() over HTTP. Startup wires the graph client and live probes
from settings; the Runtime is built per-request so viewer_id can vary.

Run dev server: uvicorn api.app:app --reload --port 8000
"""

from __future__ import annotations

import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

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
    ElevationProfile,
    ElevationSample,
    FeedCardResponse,
    FeedLineResponse,
    FeedResponse,
    GeoJsonGeometry,
    GeoPoint,
    GraphStats,
    HealthResponse,
    OutcomeBody,
    OutcomeResponse,
    PlanRequest,
    SetAsideReasonResponse,
    SetAsideResponse,
    StatusResponse,
    TripDetailResponse,
)
from graph.client import GraphClient
from graph.queries import trail_detail as trail_detail_query
from graph.queries import trails_detail as trails_detail_query
from ingestion.route import assemble_route, wkt_to_geojson
from orchestration.adapters import registry
from orchestration.config import Settings
from orchestration.engine import Feed, FeedCard, build_runtime

logger = logging.getLogger(__name__)

_VERSION = "0.0.0"

# Module-level singletons populated at startup
_settings: Settings | None = None
_graph_client: GraphClient | None = None
_probe_keys: list[str] = []


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    global _settings, _graph_client, _probe_keys
    _settings = Settings.from_env()
    _graph_client = GraphClient(_settings.neo4j_uri, _settings.neo4j_user, _settings.neo4j_password)
    # Best-effort: warm the connection pool and surface a dead/misconfigured graph at boot
    # rather than on a user's first /plan. Never fatal — a transient blip at startup must not
    # take the service down; the lazy driver + managed-transaction retry recover on first use.
    try:
        _graph_client.verify_connectivity()
    except Exception:
        logger.warning("graph connectivity check failed at startup; will connect lazily")
    _probe_keys = [k.value for k in registry.probes_for(_settings.live_region, _settings)]
    yield
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


def _card_response(card: FeedCard, maps: dict[str, Any]) -> FeedCardResponse:
    return FeedCardResponse(
        canonical_id=card.canonical_id,
        name=card.name,
        distance_mi=card.distance_mi,
        lines=[
            FeedLineResponse(
                text=line.text,
                source=line.source,
                confidence_level=line.presentation,  # "stated" | "hedged" | "flagged"
            )
            for line in card.lines
        ],
        warnings=list(card.warnings),
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


def _feed_response(feed: Feed, maps_by_cid: dict[str, dict[str, Any]]) -> FeedResponse:
    return FeedResponse(
        query=feed.query,
        cards=[_card_response(c, maps_by_cid.get(c.canonical_id, {})) for c in feed.cards],
        card_count=len(feed.cards),
        notices=list(feed.notices),
        set_aside=[_set_aside_response(t) for t in feed.set_aside],
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
                "       COUNT { (t:CanonicalTrail) } AS trails, "
                "       COUNT { (r:SourceRecord) } AS srs, "
                "       COUNT { (h:Trailhead) } AS ths, "
                "       COUNT { ()-[:SAME_AS]->() } AS edges",
                {},
            )
        )
        if not rows:
            return None
        r = rows[0]
        return GraphStats(
            canonical_trails=int(r.get("trails") or 0),
            source_records=int(r.get("srs") or 0),
            trailheads=int(r.get("ths") or 0),
            same_as_edges=int(r.get("edges") or 0),
            schema_version=r.get("sv"),
        )
    except Exception:
        # Degrade-and-disclose (Rule #1): report graph=null to the caller, but log the
        # cause server-side — a swallowed exception here hid the Cypher-25 bug for hours.
        logger.exception("graph stats query failed; reporting graph=null")
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
    return HealthResponse(
        status="ok",
        version=_VERSION,
        region=_settings.region,
        probes_available=_probe_keys,
        graph=_graph_stats(),
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
    cache_before = 0
    stats_before = probe_stats_snapshot(None)  # zeroed until the runtime cache exists
    try:
        runtime = build_runtime(_settings, _graph_client, body.viewer_id)
        from orchestration.engine import plan as engine_plan

        cache_before = cache_size(runtime.cache)
        stats_before = probe_stats_snapshot(runtime.cache)
        feed = engine_plan(
            body.query,
            (body.lat, body.lon),
            runtime,
            k=body.k,
            viewer_id=body.viewer_id,  # AC-5: forward viewer for context assembly
        )
        # Attach per-card maps/terrain fields (Epic 016 S1 / Epic 017 S4). World data
        # → a plain scoped read; degrades to map-free cards on any failure (Rule #1).
        session = _graph_client.scoped_session(body.viewer_id)
        maps_by_cid = _fetch_maps_by_canonical(session, [c.canonical_id for c in feed.cards])
        response = _feed_response(feed, maps_by_cid)
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
        line_texts = [line.text for card in feed.cards for line in card.lines]
        PlanMetrics(
            viewer_tag=scrub_viewer(body.viewer_id),
            latency_ms=(time.perf_counter() - started) * 1000,
            card_count=len(feed.cards),
            cache_entries_before=cache_before,
            cache_entries_after=cache_after,
            est_tokens=estimate_tokens(body.query, *line_texts),
            probe_stats_before=stats_before,
            probe_stats_after=stats_after,
        ).emit()
    except Exception:
        logger.exception("plan observability emit failed (response already sent)")
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
    """The start marker: the accessing trailhead's point, or the trail's own point as
    a fallback. `None` when neither exists."""
    latlon = _point_latlon(row.get("trailhead_point")) or _point_latlon(row.get("trail_point"))
    return GeoPoint(lat=latlon[0], lon=latlon[1]) if latlon else None


def _elevation_profile(row: dict[str, Any]) -> ElevationProfile | None:
    """Reassemble the stored parallel arrays + scalars into `WireElevationProfile`.
    `None` when no profile is stored (no DEM coverage) — not faked (D3). Provenance
    is read straight from the stored `elev_source`, never defaulted: a profile
    missing its source is treated as absent rather than mislabeled (Rule #1). The
    loader always writes the arrays and `elev_source` together, so a present profile
    carries real provenance."""
    distances = row.get("profile_distances_m")
    elevations = row.get("profile_elevations_m")
    source = row.get("elev_source")
    if not distances or not elevations or len(distances) != len(elevations) or not source:
        return None
    samples = [
        ElevationSample(distance_m=float(d), elevation_m=float(e))
        for d, e in zip(distances, elevations)
    ]
    return ElevationProfile(
        samples=samples,
        total_gain_m=float(row.get("total_gain_m") or 0.0),
        total_loss_m=float(row.get("total_loss_m") or 0.0),
        max_grade_pct=float(row.get("max_grade_pct") or 0.0),
        source=source,
        resolution_m=float(row.get("elev_resolution_m") or 0.0),
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


def _trip_detail_response(canonical_id: str, row: dict[str, Any]) -> TripDetailResponse:
    return TripDetailResponse(
        canonical_id=canonical_id,
        name=row.get("name") or canonical_id,
        **_maps_fields(row),
    )


@app.get("/trail/{canonical_id}", response_model=TripDetailResponse)
@limiter.limit(detail_limit)
def trail_detail(
    request: Request,  # required by slowapi for per-IP keying
    canonical_id: str,
    viewer_id: str = "anonymous",
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
    return _trip_detail_response(canonical_id, rows[0])


def _drain_queue_bg(queue, graph_client) -> None:
    """Drain the belief update queue after the HTTP response is sent.

    Called via FastAPI BackgroundTasks so the caller receives their response
    immediately; belief updates happen asynchronously (AC-4.3 / S6 §4.1 queue
    discipline: never block the request path). Drains through the scoped-write
    seam (Epic 011): `scoped_session` is the per-owner factory each task's writes
    are scoped through (rule #4).
    """
    queue.drain(graph_client.scoped_session)


@app.post("/episode/{episode_id}/outcome", response_model=OutcomeResponse)
@limiter.limit(outcome_limit)
def record_outcome(
    request: Request,  # required by slowapi for per-IP keying
    episode_id: str,
    body: OutcomeBody,
    background_tasks: BackgroundTasks,
    viewer_id: str = "anonymous",  # Phase 1: query param; Stage 8 replaces with auth header
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
        logger.exception("record outcome failed for episode_id=%r", episode_id)
        raise HTTPException(status_code=500, detail="Internal error") from exc


@app.exception_handler(Exception)
async def generic_exception_handler(request: Any, exc: Exception) -> JSONResponse:
    # Last-resort handler for anything not caught in a route — disclose server-side.
    logger.exception("unhandled exception")
    return JSONResponse(status_code=500, content={"detail": str(exc)})
