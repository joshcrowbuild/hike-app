"""API request/response schemas (Pydantic models)."""

from __future__ import annotations

from typing import Any, Literal

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


# ── Trip-detail contract — the frozen Lane A↔B coupling (Epic 016 S1 + Epic 017) ──
#
# This is the SINGLE integration shape the maps/elevation feature is built around:
# Lane A (this backend) produces it for real trails; Lane B mirrors it as the
# frontend trip type + mock, so both lanes build concurrently and meet here. The
# two halves — assembled `geometry` (Epic 016 S1) and `elevationProfile` (Epic 017
# S0) — are the only cross-lane types. Field names are the wire contract; keep them
# verbatim. `null` everywhere means *not available*, never fabricated (Rule #1).


class GeoJsonGeometry(BaseModel):
    """The assembled route as a GeoJSON geometry (WGS84). Coordinate order is
    `(lon, lat)` per the GeoJSON spec. `LineString` when the trail's segments join
    into one continuous line; `MultiLineString` when they don't join cleanly —
    each element a connected run (Epic 016 AC-1.1)."""

    type: Literal["LineString", "MultiLineString"]
    # LineString -> [[lon, lat], ...]; MultiLineString -> [[[lon, lat], ...], ...].
    coordinates: list[Any]


class TrailheadPoint(BaseModel):
    """The start marker (Epic 016 S1): `Trailhead.point`, or the `CanonicalTrail`
    representative point as a fallback. Drives the "trailhead only" state when a
    route is unmapped (D5)."""

    lat: float
    lon: float


class ElevationSample(BaseModel):
    """One ordered point on the climb profile (Epic 017 S0). `distanceMeters` is the
    cumulative along-route distance from the start; samples run start → end."""

    distanceMeters: float
    elevationMeters: float


class ElevationProfile(BaseModel):
    """The precomputed climb profile sampled along the route from USGS 3DEP (Epic
    017). `null` (the whole field) when a trail has no DEM coverage or no geometry —
    never an interpolated or faked curve (Rule #1 / D3)."""

    samples: list[ElevationSample]  # ordered start → end
    totalGainMeters: float
    totalLossMeters: float
    maxGradePercent: float
    source: str  # provenance, e.g. "usgs-3dep"
    resolutionMeters: float  # sampling spacing along the route


class TripDetailResponse(BaseModel):
    """The trip/detail response (`GET /trail/{canonical_id}`). Carries the spatial
    truth a single recommendation needs — where it is, the shape of the day — with
    every geometry/elevation field honestly `null` when absent (Rule #1)."""

    canonical_id: str
    name: str
    geometry: GeoJsonGeometry | None = None  # null = route not mapped (trailhead only)
    trailhead: TrailheadPoint | None = None
    elevationProfile: ElevationProfile | None = None  # null = no coverage
