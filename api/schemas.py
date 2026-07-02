"""API request/response schemas (Pydantic models)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# Shape of a viewer identity (AH4): the anonymous default, or an alphanumeric/underscore/
# hyphen/colon token (":" separates the household-member prefix, e.g. "mem:josh"),
# length-bounded so a malformed value 422s before it ever reaches Cypher (access control
# at the query/data layer, rule #4) or a log line (rule #5).
VIEWER_ID_PATTERN = r"^[A-Za-z0-9_:-]{1,64}$"


class PlanRequest(BaseModel):
    query: str = Field(
        ..., description="Free-text request, e.g. 'something mellow with good views'"
    )
    lat: float = Field(..., ge=-90, le=90, description="Origin latitude (WGS84)")
    lon: float = Field(..., ge=-180, le=180, description="Origin longitude (WGS84)")
    k: int = Field(default=10, ge=1, le=50, description="Max results")
    viewer_id: str = Field(
        default="anonymous",
        pattern=VIEWER_ID_PATTERN,
        description="Viewer identity for graph scoping",
    )


class FeedLineResponse(BaseModel):
    text: str
    source: str
    confidence_level: str  # "stated" | "hedged" | "flagged"  (presentation vocabulary)


class CardWarningResponse(BaseModel):
    """One prominent, source-stamped hazard warning a card wears (decision of
    2026-07-01): a VERIFIED hazard shows on the trail's card, never hides it.
    Mirrors `FeedLineResponse`'s source-carrying shape; `observed_at` is the ISO-8601
    timestamp the hazard fact was fetched. Mirrors `frontend/src/data/api.ts`."""

    text: str
    source: str
    observed_at: str  # ISO-8601 fetch timestamp of the hazard fact
    kind: str  # the condition kind, e.g. "weather" | "air" | "fire"


# ── Maps & terrain wire DTOs — the Lane A↔B contract ──────────────────────────
#
# These are a literal mirror of `frontend/src/data/api.ts` (the published source of
# truth): `WireGeometry` / `WirePoint` / `WireElevationSample` / `WireElevationProfile`,
# plus the maps fields on `FeedCardResponse`. Field names ARE the wire contract — keep
# them snake_case and verbatim. `null`/absent everywhere means *not available*, never a
# fabricated value (Rule #1). `tests/test_maps_contract.py` asserts this match.

ConfidenceLevel = Literal["stated", "hedged", "flagged"]


class GeoJsonGeometry(BaseModel):
    """`WireGeometry`: the assembled route as a GeoJSON geometry (WGS84), coordinate
    order `(lon, lat)` per the spec. `LineString` when the trail's segments join into
    one continuous line; `MultiLineString` when they don't join cleanly (Epic 016
    AC-1.1)."""

    type: Literal["LineString", "MultiLineString"]
    # LineString -> [[lon, lat], ...]; MultiLineString -> [[[lon, lat], ...], ...].
    coordinates: list[Any]


class GeoPoint(BaseModel):
    """`WirePoint`: a WGS84 point `{lat, lon}` — used for the trailhead start marker
    and the summit/high-point."""

    lat: float
    lon: float


class ElevationSample(BaseModel):
    """`WireElevationSample`: one ordered point on the climb profile. `distance_m` is
    the cumulative along-route distance from the start; samples run start → end."""

    distance_m: float
    elevation_m: float


class ElevationProfile(BaseModel):
    """`WireElevationProfile`: the precomputed climb profile sampled along the route
    from USGS 3DEP (Epic 017). The whole field is `null` when a trail has no DEM
    coverage or no geometry — never an interpolated or faked curve (Rule #1 / D3)."""

    samples: list[ElevationSample]  # ordered start → end
    total_gain_m: float
    total_loss_m: float
    max_grade_pct: float
    source: str  # provenance, e.g. "usgs-3dep"
    resolution_m: float  # sampling spacing along the route


class FeedCardResponse(BaseModel):
    canonical_id: str
    name: str
    distance_mi: float | None
    lines: list[FeedLineResponse]
    warnings: list[CardWarningResponse]
    # Maps & terrain (Epic 016 S1 / Epic 017 S4). All optional/nullable: a card with no
    # mapped route omits/nulls them and the client degrades honestly (Rule #1).
    geometry: GeoJsonGeometry | None = None
    trailhead: GeoPoint | None = None
    # Geometry's confidence tier (Rule #2); non-`stated` draws the dashed "approximate"
    # route (D5). Derived from assembly quality, never hardcoded.
    geometry_confidence: ConfidenceLevel | None = None
    summit: GeoPoint | None = None  # high point if known, else null (source-or-silence)
    elevation_profile: ElevationProfile | None = None


class SetAsideReasonResponse(BaseModel):
    """One source-stamped cause a trail was set aside by a hard live guardrail (Epic
    018 S5). `text` is the ready-to-show disclosure ("cause (source)"); `source`/`kind`
    keep the pieces structured. Mirrors `frontend/src/data/api.ts`."""

    text: str
    source: str
    kind: str  # the condition kind, e.g. "weather" | "air"


class SetAsideResponse(BaseModel):
    """A trail a hard live guardrail ruled out — an unverifiable required condition or
    a hard threshold — disclosed with its cause + source (Epic 018 S5 AC-5.2), never
    dropped without a trace. A verified hazard is NOT set aside; it stays a card with a
    `warnings` entry (decision of 2026-07-01). A safety gate, not a ranking signal
    (Rule #2). Mirrors `frontend/src/data/api.ts`."""

    canonical_id: str
    name: str
    reasons: list[SetAsideReasonResponse]


class FeedResponse(BaseModel):
    query: str
    cards: list[FeedCardResponse]
    card_count: int
    notices: list[str] = []  # feed-level disclosures (e.g. drive times unavailable)
    # Trails a hard live guardrail set aside, disclosed with cause + source (Epic 018 S5).
    set_aside: list[SetAsideResponse] = []


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


class StatusResponse(BaseModel):
    """`GET /status`: current deployed state for cross-surface grounding (the
    agent-operating-model real-time source). Anything unknowable from this host is
    honestly `null` — never guessed (Rule #1): deploy fields are `null` off Render,
    graph-derived fields are `null` when the graph is unreachable."""

    deploy_sha: str | None  # RENDER_GIT_COMMIT; null off Render
    deploy_branch: str | None  # RENDER_GIT_BRANCH; null off Render
    region: str  # corpus region (e.g. "shenandoah-gwj")
    live_region: str  # live-probe registry region (e.g. "US")
    schema_version: str | None  # (:Meta {id:'schema'}).schema_version
    meta_updated_at: str | None  # Meta.updated_at (last schema apply), ISO-8601
    # Most recent SourceRecord.fetched_at (ISO-8601), falling back to the coarse
    # ingest_version ("YYYY-MM") when no fetched_at is stored.
    last_ingest: str | None
    corpus: GraphStats | None  # same shape as /health's graph; None if unreachable


class TripDetailResponse(BaseModel):
    """The trip/detail response (`GET /trail/{canonical_id}`). The same maps fields the
    feed card carries, served per-trail — every geometry/elevation field honestly
    `null` when absent (Rule #1). Snake_case to match `frontend/src/data/api.ts`."""

    canonical_id: str
    name: str
    geometry: GeoJsonGeometry | None = None  # null = route not mapped (trailhead only)
    trailhead: GeoPoint | None = None
    geometry_confidence: ConfidenceLevel | None = None
    summit: GeoPoint | None = None
    elevation_profile: ElevationProfile | None = None  # null = no coverage
