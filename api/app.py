"""Adventure Planner FastAPI application.

Exposes engine.plan() over HTTP. Startup wires the graph client and live probes
from settings; the Runtime is built per-request so viewer_id can vary.

Run dev server: uvicorn api.app:app --reload --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from api.schemas import (
    FeedCardResponse,
    FeedLineResponse,
    FeedResponse,
    HealthResponse,
    PlanRequest,
)
from graph.client import GraphClient
from orchestration.config import Settings
from orchestration.engine import Feed, FeedCard, build_runtime
from orchestration.verifier import build_probes

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
    _probe_keys = list(build_probes(_settings).keys())
    yield
    if _graph_client:
        _graph_client.close()


app = FastAPI(
    title="Adventure Planner",
    version=_VERSION,
    description="Personal, agentic, self-verifying hiking/backpacking trip planner.",
    lifespan=lifespan,
)


def _card_response(card: FeedCard) -> FeedCardResponse:
    return FeedCardResponse(
        canonical_id=card.canonical_id,
        name=card.name,
        distance_mi=card.distance_mi,
        lines=[
            FeedLineResponse(
                text=line.text,
                source=line.source,
                confidence_level=line.confidence_level,
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
    )


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    if _settings is None:
        raise HTTPException(status_code=503, detail="Settings not loaded")
    return HealthResponse(
        status="ok",
        version=_VERSION,
        region=_settings.region,
        probes_available=_probe_keys,
    )


@app.post("/plan", response_model=FeedResponse)
def plan(request: PlanRequest) -> FeedResponse:
    if _settings is None or _graph_client is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    try:
        runtime = build_runtime(_settings, _graph_client, request.viewer_id)
        from orchestration.engine import plan as engine_plan

        feed = engine_plan(request.query, (request.lat, request.lon), runtime, k=request.k)
        return _feed_response(feed)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.exception_handler(Exception)
async def generic_exception_handler(request: Any, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": str(exc)})
