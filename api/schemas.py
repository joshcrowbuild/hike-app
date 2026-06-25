"""API request/response schemas (Pydantic models)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PlanRequest(BaseModel):
    query: str = Field(
        ..., description="Free-text request, e.g. 'something mellow with good views'"
    )
    lat: float = Field(..., ge=-90, le=90, description="Origin latitude (WGS84)")
    lon: float = Field(..., ge=-180, le=180, description="Origin longitude (WGS84)")
    k: int = Field(default=10, ge=1, le=50, description="Max results")
    viewer_id: str = Field(default="anonymous", description="Viewer identity for graph scoping")


class FeedLineResponse(BaseModel):
    text: str
    source: str
    confidence_level: str  # "stated" | "hedged" | "flagged"  (presentation vocabulary)


class FeedCardResponse(BaseModel):
    canonical_id: str
    name: str
    distance_mi: float | None
    lines: list[FeedLineResponse]
    warnings: list[str]


class FeedResponse(BaseModel):
    query: str
    cards: list[FeedCardResponse]
    card_count: int
    notices: list[str] = []  # feed-level disclosures (e.g. drive times unavailable)


class GraphStats(BaseModel):
    canonical_trails: int
    source_records: int
    trailheads: int
    same_as_edges: int
    schema_version: str | None


class OutcomeBody(BaseModel):
    overall: int | None = Field(
        default=None,
        description="1 (😞) | 2 (😐) | 3 (🙂); null when skipped",
    )
    delta_question: str | None = None
    delta_answer: str | None = Field(default=None, description="User's free-text reflect-back")
    skipped: bool = False


class OutcomeResponse(BaseModel):
    outcome_id: str
    episode_id: str
    skipped: bool
    overall: int | None


class HealthResponse(BaseModel):
    status: str
    version: str
    region: str
    probes_available: list[str]
    graph: GraphStats | None = None  # None if Neo4j unreachable
