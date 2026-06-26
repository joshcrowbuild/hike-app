"""Adventure Planner FastAPI application.

Exposes engine.plan() over HTTP. Startup wires the graph client and live probes
from settings; the Runtime is built per-request so viewer_id can vary.

Run dev server: uvicorn api.app:app --reload --port 8000
"""

from __future__ import annotations

import secrets
from contextlib import asynccontextmanager
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

from api.schemas import (
    FeedCardResponse,
    FeedLineResponse,
    FeedResponse,
    GraphStats,
    HealthResponse,
    OutcomeBody,
    OutcomeResponse,
    PlanRequest,
)
from graph.client import GraphClient
from orchestration.adapters import registry
from orchestration.config import Settings
from orchestration.engine import Feed, FeedCard, build_runtime

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


def _card_response(card: FeedCard) -> FeedCardResponse:
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
    )


def _feed_response(feed: Feed) -> FeedResponse:
    return FeedResponse(
        query=feed.query,
        cards=[_card_response(c) for c in feed.cards],
        card_count=len(feed.cards),
        notices=list(feed.notices),
    )


def _graph_stats() -> GraphStats | None:
    if _graph_client is None or _settings is None:
        return None
    try:
        session = _graph_client.scoped_session("health-check")
        rows = session.run(
            (
                "MATCH (m:Meta {id: 'schema'}) "
                "RETURN m.schema_version AS sv, "
                "       size([(t:CanonicalTrail) | t]) AS trails, "
                "       size([(r:SourceRecord) | r]) AS srs, "
                "       size([(h:Trailhead) | h]) AS ths, "
                "       size([()-[:SAME_AS]->() | 1]) AS edges",
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
        return None


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    if _settings is None:
        raise HTTPException(status_code=503, detail="Settings not loaded")
    return HealthResponse(
        status="ok",
        version=_VERSION,
        region=_settings.region,
        probes_available=_probe_keys,
        graph=_graph_stats(),
    )


@app.post("/plan", response_model=FeedResponse)
def plan(
    request: PlanRequest,
    x_dev_viewer_secret: str | None = Header(default=None),
) -> FeedResponse:
    if _settings is None or _graph_client is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    _authorize_viewer(request.viewer_id, x_dev_viewer_secret)
    try:
        runtime = build_runtime(_settings, _graph_client, request.viewer_id)
        from orchestration.engine import plan as engine_plan

        feed = engine_plan(
            request.query,
            (request.lat, request.lon),
            runtime,
            k=request.k,
            viewer_id=request.viewer_id,  # AC-5: forward viewer for context assembly
        )
        return _feed_response(feed)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal error") from exc


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
def record_outcome(
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
        raise HTTPException(status_code=500, detail="Internal error") from exc


@app.exception_handler(Exception)
async def generic_exception_handler(request: Any, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": str(exc)})
